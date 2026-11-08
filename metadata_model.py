"""Stage 1: P(M | X_meta) from who is on the email and which thread it belongs to.

Naive-Bayes style combination, written in posterior form:

    log P(M | x_1..x_k)  =  log P(M) + sum_i  w_i * log( P(M | x_i) / P(M) )  + const

Evidence x_i:
  * thread    - matters of earlier filed emails in the same thread
  * sender novelty - a sender never seen before (no history, no intake link): learned
                      from history how often such emails turned out to be "no matter"
  * each participant address (owner excluded), from:
      - intake links (the contact was attached to M when the matter was opened)
      - history (how often that address appeared on emails filed under M)
    falling back to the address's domain when the address itself is unknown.

P(M | x_i) is a smoothed estimate that shrinks toward the prior P(M) when there is
little data, so an unseen or uninformative participant contributes ~0.
Weights w_i < 1 soften the overcounting that comes from correlated participants.
Subject and body are NOT used here; they belong to the semantic stage.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from context import NONE, Context, EmailView, FiledEmail, Workspace
from pipeline import Posterior, Stage

FREE_MAIL = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"}


@dataclass
class MetaConfig:
    alpha: float = 1.0          # Laplace smoothing for the class prior
    intake_weight: float = 3.0  # pseudo-count for "contact linked to matter at intake"
    gamma: float = 1.0          # shrinkage of P(M | x) toward P(M)
    thread_eps: float = 0.3     # shrinkage for thread evidence (small = trust the thread)
    w_thread: float = 1.0
    w_from: float = 1.0
    w_recipient: float = 0.6
    w_domain: float = 0.5       # extra discount when only the domain is known
    w_novel: float = 1.0        # weight of the "never-seen sender" evidence


class MetadataStage(Stage):
    name = "metadata"

    def __init__(self, cfg: MetaConfig | None = None):
        self.cfg = cfg or MetaConfig()

    # ---------------------------------------------------------------- online state
    def reset(self, workspace: Workspace):
        self.ws = workspace
        self.class_counts = Counter()
        self.addr = defaultdict(Counter)     # address -> matter counts from filed emails
        self.domain = defaultdict(Counter)   # external domain -> matter counts
        self.thread = defaultdict(Counter)   # thread_id -> matter counts
        self.novel = Counter()               # for never-seen senders: "none" vs "matter" outcomes

    def _known(self, address, ctx):
        return address in self.addr or any(address == e for m in ctx.open_matters for e, _ in m.contacts)

    def observe(self, filed: FiledEmail, ctx: Context):
        labels = filed.matter_ids or (NONE,)
        e = filed.email
        if e.sender.email != self.ws.owner_email and not self._known(e.sender.email, ctx):
            self.novel["none" if not filed.matter_ids else "matter"] += 1
        self.class_counts.update(labels)
        self.thread[e.thread_id].update(labels)
        for _, p in e.participants():
            if p.email == self.ws.owner_email:
                continue
            self.addr[p.email].update(labels)
            if self._external(p.domain):
                self.domain[p.domain].update(labels)

    def _external(self, domain):
        return domain != self.ws.firm_domain and domain not in FREE_MAIL

    # ---------------------------------------------------------------- prediction
    def _prior(self, cands):
        a = self.cfg.alpha
        total = sum(self.class_counts[c] for c in cands) + a * len(cands)
        return {c: (self.class_counts[c] + a) / total for c in cands}

    def _intake(self, ctx):
        """Intake links for matters open at ctx.now only."""
        addr, dom = defaultdict(Counter), defaultdict(Counter)
        for m in ctx.open_matters:
            for email, _role in m.contacts:
                addr[email][m.matter_id] += self.cfg.intake_weight
                d = email.split("@", 1)[1]
                if self._external(d):
                    dom[d][m.matter_id] += self.cfg.intake_weight
        return addr, dom

    @staticmethod
    def _llr(counts, prior, shrink):
        """log( P(M|x) / P(M) ) with P(M|x) = (n_M + shrink*P(M)) / (N + shrink)."""
        n = sum(counts.get(c, 0) for c in prior)
        return {c: math.log((counts.get(c, 0) + shrink * prior[c]) / (n + shrink) / prior[c]) for c in prior}

    def predict(self, email: EmailView, ctx: Context, prior: Posterior | None = None) -> Posterior:
        cfg = self.cfg
        cands = ctx.candidates
        P = self._prior(cands) if prior is None else {c: prior.probs[c] for c in cands}
        score = {c: math.log(P[c]) for c in cands}
        evidence = []

        def add(counts, weight, shrink, what):
            counts = {c: v for c, v in counts.items() if c in P}
            if not counts:
                return False
            for c, v in self._llr(counts, P, shrink).items():
                score[c] += weight * v
            top = max(counts, key=counts.get)
            evidence.append(f"{what} -> {top} ({counts[top]:g}/{sum(counts.values()):g})")
            return True

        add(self.thread.get(email.thread_id, {}), cfg.w_thread, cfg.thread_eps, f"thread {email.thread_id}")

        if email.sender.email != self.ws.owner_email and not self._known(email.sender.email, ctx):
            n_none, n_all = self.novel["none"], sum(self.novel.values())
            q = (n_none + cfg.gamma * P[NONE]) / (n_all + cfg.gamma)     # P(none | new sender)
            score[NONE] += cfg.w_novel * math.log(q / P[NONE])
            for c in cands:
                if c != NONE:
                    score[c] += cfg.w_novel * math.log((1 - q) / (1 - P[NONE]))
            evidence.append(f"new sender: {n_none}/{n_all} past new-sender emails were no-matter")

        intake_addr, intake_dom = self._intake(ctx)
        for role, p in email.participants():
            if p.email == self.ws.owner_email:
                continue
            w = cfg.w_from if role == "from" else cfg.w_recipient
            counts = self.addr.get(p.email, Counter()) + intake_addr.get(p.email, Counter())
            if add(counts, w, cfg.gamma, f"{role} {p.email}"):
                continue
            if self._external(p.domain):
                counts = self.domain.get(p.domain, Counter()) + intake_dom.get(p.domain, Counter())
                add(counts, w * cfg.w_domain, cfg.gamma, f"{role} domain {p.domain}")

        mx = max(score.values())
        z = sum(math.exp(s - mx) for s in score.values())
        return Posterior({c: math.exp(s - mx) / z for c, s in score.items()}, evidence or ["no metadata evidence"])
