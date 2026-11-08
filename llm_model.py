"""Stage 3: a small local LLM reads the candidate matters and picks one.

Runs only on emails the metadata and semantic stages left unresolved. The prompt holds:
  * the top-k candidate matters by the current posterior, listed in a NEUTRAL order
    (by matter id, not by probability) so the model's bias toward option A does not
    secretly re-apply the prior, plus a "none of these" option
  * each candidate's whole matter as known at that moment: intake record, linked contacts,
    and a one-line digest of every email already filed under it (ctx.filed_under ->
    strictly before this email, so no leakage)
  * the prior from earlier stages (prior_mode="in_prompt"; see below)
  * the email itself

The answer is read from the next-token probabilities of the option letters (no
generation, no thinking), giving a full distribution instead of a single guess.

prior_mode:
  in_prompt - priors shown in the prompt; the LLM's distribution is the posterior
  bayes     - priors hidden; posterior = prior x LLM likelihood (avoids double counting)
  none      - priors hidden and ignored; the LLM's distribution alone (ablation)

Default model: Qwen3.5-4B (Apache-2.0), 4-bit MLX build, about 3 GB of memory.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from context import NONE, Context, EmailView
from pipeline import Posterior, Stage
from semantic_model import new_text

SYSTEM = ("You work at a law firm and file each incoming email under the client matter it "
          "belongs to. Read the candidate matters and the email, then reply with only the "
          "letter of the best option.")
LETTERS = "ABCDEFGHIJ"


@dataclass
class LLMConfig:
    model: str = "mlx-community/Qwen3.5-4B-MLX-4bit"
    top_k: int = 3              # candidate matters shown (by current posterior); "none" is always added
    max_history: int = 15       # most recent filed emails per matter in the prompt (0 = all)
    digest_chars: int = 140     # snippet length per filed email
    body_chars: int = 1500      # email body truncation
    prior_mode: str = "in_prompt"
    prefill_step: int = 512


class LLMStage(Stage):
    name = "llm"

    def __init__(self, cfg: LLMConfig | None = None, only_ids: set[str] | None = None,
                 cache_dir="outputs/llm_cache"):
        self.cfg = cfg or LLMConfig()
        self.only_ids = only_ids          # restrict LLM calls (e.g. to the eval split) to save time
        self._model = None
        key = hashlib.sha1(json.dumps(asdict(self.cfg), sort_keys=True).encode()).hexdigest()[:10]
        self.cache_path = Path(cache_dir) / f"{key}.jsonl"
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache = {}
        if self.cache_path.exists():
            for line in self.cache_path.read_text().splitlines():
                row = json.loads(line)
                self.cache[row["email_id"]] = row
        self.calls, self.seconds, self.tokens = 0, 0.0, 0

    # ---------------------------------------------------------------- model
    def _load(self):
        if self._model is None:
            from mlx_lm import load
            self._model, self._tok = load(self.cfg.model)
            self._letter_ids = []
            for L in LETTERS:
                ids = self._tok.encode(L, add_special_tokens=False)
                assert len(ids) == 1, f"letter {L} is not a single token"
                self._letter_ids.append(ids[0])

    def _score(self, prompt: str, n: int) -> tuple[list[float], int]:
        import mlx.core as mx
        from mlx_lm.models.cache import make_prompt_cache
        self._load()
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        text = self._tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False,
                                             enable_thinking=False)
        ids = self._tok.encode(text, add_special_tokens=False)
        cache = make_prompt_cache(self._model)
        step = self.cfg.prefill_step
        for i in range(0, len(ids), step):
            logits = self._model(mx.array(ids[i:i + step])[None], cache=cache)
            mx.eval(logits)
        last = logits[0, -1].astype(mx.float32)
        sel = mx.softmax(last[mx.array(self._letter_ids[:n])])
        return [float(x) for x in sel.tolist()], len(ids)

    # ---------------------------------------------------------------- prompt
    def _who(self, address):
        c = self.ws.address_book.get(address)
        return f"{c['name']} ({c['title']}, {c['organization']})" if c else f"{address} (not in address book)"

    def build_prompt(self, email: EmailView, ctx: Context, options: list[str], prior: dict) -> str:
        cfg, by_id = self.cfg, {m.matter_id: m for m in ctx.open_matters}
        parts = [f"Mailbox owner: {self._who(self.ws.owner_email)}\n", "## Candidate matters"]
        for L, opt in zip(LETTERS, options):
            if opt == NONE:
                parts.append(f"\n### Option {L}: No matter\nFirm administration, newsletters, marketing, "
                             f"recruiting, personal messages, or anything not tied to a client matter.")
                continue
            m = by_id[opt]
            filed = sorted(ctx.filed_under(opt), key=lambda f: f.email.timestamp)
            shown = filed[-cfg.max_history:] if cfg.max_history else filed
            contacts = "; ".join(f"{self._who(e)} - {role.replace('_', ' ')}" for e, role in m.contacts)
            parts.append(
                f"\n### Option {L}: {m.name} (matter {m.matter_number})\n"
                f"Client: {m.client} | Practice: {m.practice_area} | Counterparty: {m.counterparty}"
                f" | Opposing counsel: {m.opposing_counsel_firm or 'n/a'}\n"
                f"Description: {m.description}\nKey terms: {', '.join(m.key_terms)}\n"
                f"Contacts: {contacts}\n"
                f"Emails filed so far ({len(filed)}{f', last {len(shown)} shown' if len(shown) < len(filed) else ''}):")
            for f in shown:
                e = f.email
                snippet = re.sub(r"\s+", " ", new_text(e).split("\n", 1)[-1])[:cfg.digest_chars]
                parts.append(f"- {e.timestamp:%Y-%m-%d} | {e.sender.name} | {e.subject} | {snippet}")
            if not filed:
                parts.append("- (none yet)")

        if cfg.prior_mode == "in_prompt":
            z = sum(prior[o] for o in options)
            est = ", ".join(f"{L} {100 * prior[o] / z:.0f}%" for L, o in zip(LETTERS, options))
            parts.append(f"\n## Estimate from sender, thread and text-similarity signals (can be wrong)\n{est}")

        to = ", ".join(self._who(p.email) for p in email.to)
        cc = ", ".join(self._who(p.email) for p in email.cc) or "-"
        parts.append(
            f"\n## Email to file\nDate: {email.timestamp:%Y-%m-%d %H:%M}\nFrom: {self._who(email.sender.email)}\n"
            f"To: {to}\nCc: {cc}\nSubject: {email.subject}\n"
            f"Attachments: {', '.join(email.attachments) or '-'}\n\n{email.body[:cfg.body_chars]}\n"
            f"\nWhich option does this email belong to? Answer with a single letter "
            f"({', '.join(LETTERS[:len(options)])}).")
        return "\n".join(parts)

    # ---------------------------------------------------------------- stage API
    def reset(self, workspace):
        self.ws = workspace

    def predict(self, email: EmailView, ctx: Context, prior: Posterior | None) -> Posterior:
        if self.only_ids is not None and email.email_id not in self.only_ids:
            return prior                              # skipped: pass through unchanged
        P = prior.probs
        ranked = [c for c in sorted(P, key=P.get, reverse=True) if c != NONE][: self.cfg.top_k]
        options = sorted(ranked) + [NONE]             # neutral order; "none" always last

        hit = self.cache.get(email.email_id)
        if hit and hit["options"] == options:
            llm = hit["probs"]
        else:
            t = time.time()
            llm, ntok = self._score(self.build_prompt(email, ctx, options, P), len(options))
            dt = time.time() - t
            self.calls += 1
            self.seconds += dt
            self.tokens += ntok
            with open(self.cache_path, "a") as f:
                f.write(json.dumps(dict(email_id=email.email_id, options=options, probs=llm,
                                        prompt_tokens=ntok, seconds=round(dt, 2))) + "\n")
            print(f"[llm] call {self.calls}: {ntok} tokens, {dt:.1f}s "
                  f"(avg {self.seconds / self.calls:.1f}s)", file=sys.stderr, flush=True)

        if self.cfg.prior_mode == "bayes":
            raw = [P[o] * p for o, p in zip(options, llm)]
        else:
            raw = list(llm)
        z = sum(raw) or 1.0
        mass_in = sum(P[o] for o in options)          # probability mass of the options shown
        probs = {c: P[c] for c in P}                  # matters not shown keep their prior
        for o, r in zip(options, raw):
            probs[o] = mass_in * r / z
        best = max(zip(options, llm), key=lambda x: x[1])
        evidence = prior.evidence + [f"llm ({self.cfg.prior_mode}): picked {best[0]} p={best[1]:.2f}"]
        return Posterior(probs, evidence)
