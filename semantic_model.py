"""Stage 2: P(M | X_sem, X_meta), which refines the metadata posterior using the email text.

    log P(M | sem, meta) = log P(M | meta) + s_M / tau + w_id * [key term of M appears] + const

s_M is how close the email is to matter M in embedding space. Each matter's
"memory" is a set of vectors:
  * its intake text (name, description, counterparty, key terms), known when it opened
  * every email already filed under it (added in observe(), i.e. after prediction)
"No matter" gets a few generic anchor texts plus any emails filed as no-matter.

Two ways to turn that memory into s_M:
  knn      - mean cosine similarity of the email to the matter's top-m nearest items (FAISS)
  subspace - norm of the email's projection onto the span of the matter's top-r
             SVD directions (the "basis projection" idea)

Key-term matching (matter number, case no., codename...) is exact string matching on
the new text. Embeddings are bad at telling "83972-001" from "83972-002".
"""

from __future__ import annotations

import os
import re

# faiss and torch each ship their own OpenMP on macOS; running both multi-threaded segfaults.
os.environ.setdefault("OMP_NUM_THREADS", "1")
from dataclasses import dataclass

import faiss
import numpy as np

from context import NONE, Context, EmailView, FiledEmail, Matter, Workspace
from pipeline import Posterior, Stage

QUOTE = re.compile(r"\n\nOn [^\n]+ wrote:\n")

# Generic descriptions of mail that belongs to no matter. Hand-written prior knowledge,
# playing the role that intake text plays for real matters.
NONE_ANCHORS = [
    "Firm-wide announcement, newsletter or office update for all staff.",
    "Continuing legal education, training, or compliance reminder.",
    "IT, facilities or system maintenance notice.",
    "Industry newsletter, market roundup, event invitation or marketing email.",
    "Recruiter outreach, personal or social message unrelated to any client.",
]


GREETING = re.compile(r"^[^\n]{0,40},\s*\n")
SIGNOFF = re.compile(r"\n\s*(best|thanks|regards|best regards|thank you|cheers|sincerely),?\s*\n", re.I)


def new_text(e: EmailView) -> str:
    """Subject + this message's own text: quoted history, greeting and signature removed.
    Greetings/signatures/disclaimers are shared by unrelated emails and swamp the similarity."""
    body = QUOTE.split(e.body)[0]
    body = GREETING.sub("", body, count=1)
    body = SIGNOFF.split(body)[0]
    return f"{e.subject}\n{body.strip()}"


def matter_text(m: Matter) -> str:
    return (f"{m.name}. {m.description} Practice area: {m.practice_area}. "
            f"Counterparty: {m.counterparty}. Key terms: {', '.join(m.key_terms)}.")


class Embedder:
    """Sentence-transformer with an in-memory cache. Encoding is a fixed pretrained function,
    so pre-warming the cache with future texts does not leak labels."""

    def __init__(self, model="sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model, device="cpu")
        self.dim = self.model.get_embedding_dimension()
        self.cache: dict[str, np.ndarray] = {}

    def warm(self, texts):
        todo = list({t for t in texts if t not in self.cache})
        if todo:
            vecs = self.model.encode(todo, batch_size=64, normalize_embeddings=True, convert_to_numpy=True)
            self.cache.update(zip(todo, vecs.astype("float32")))

    def __call__(self, text: str) -> np.ndarray:
        self.warm([text])
        return self.cache[text]


@dataclass
class SemConfig:
    method: str = "knn"       # "knn" or "subspace"
    tau: float = 0.12         # temperature (tuned on history split): lower = trust text more relative to the prior
    top_m: int = 3            # knn: average of the m most similar items per matter
    k: int = 200              # knn: neighbours retrieved from FAISS
    rank: int = 3             # subspace: SVD basis size per matter
    w_id: float = 3.0         # log-boost per matter whose key term appears (0 disables)
    none_floor: float = 0.4   # (tuned on history) "no matter" similarity is at least this: if no matter is more
                              # similar than the floor, no-matter wins (reject option)


class SemanticStage(Stage):
    name = "semantic"

    def __init__(self, embedder: Embedder, cfg: SemConfig | None = None):
        self.emb, self.cfg = embedder, cfg or SemConfig()

    # ---------------------------------------------------------------- memory
    def reset(self, ws: Workspace):
        self.ws = ws
        self.index = faiss.IndexFlatIP(self.emb.dim)
        self.labels: list[str] = []          # label of each row in the index
        self.vecs: dict[str, list] = {}      # label -> list of vectors (for subspace)
        self._basis = {}
        self._key_res = {m.matter_id: [re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)") for t in m.key_terms]
                         for m in ws.matters}
        # Intake text exists from opening day; candidates filtering keeps unopened matters out.
        for m in ws.matters:
            self._add(self.emb(matter_text(m)), m.matter_id)
        for a in NONE_ANCHORS:
            self._add(self.emb(a), NONE)

    def _add(self, v, label):
        self.index.add(v[None, :])
        self.labels.append(label)
        self.vecs.setdefault(label, []).append(v)
        self._basis.pop(label, None)

    def observe(self, filed: FiledEmail, ctx: Context):
        v = self.emb(new_text(filed.email))
        for label in filed.matter_ids or (NONE,):
            self._add(v, label)

    # ---------------------------------------------------------------- scoring
    def _knn_scores(self, q, cands):
        k = min(self.cfg.k, self.index.ntotal)
        sims, idx = self.index.search(q[None, :], k)
        per = {}
        for s, i in zip(sims[0], idx[0]):
            lab = self.labels[i]
            if lab in cands and len(per.setdefault(lab, [])) < self.cfg.top_m:
                per[lab].append(float(s))
        floor = float(sims[0][-1])           # anything not retrieved is at most this similar
        return {c: (np.mean(per[c]) if c in per else floor) for c in cands}

    def _subspace_scores(self, q, cands):
        out = {}
        for c in cands:
            if c not in self._basis:
                X = np.stack(self.vecs[c])
                _, _, vt = np.linalg.svd(X, full_matrices=False)
                self._basis[c] = vt[: self.cfg.rank]
            out[c] = float(np.linalg.norm(self._basis[c] @ q))
        return out

    def predict(self, email: EmailView, ctx: Context, prior: Posterior | None) -> Posterior:
        cands = ctx.candidates
        P = prior.probs if prior else {c: 1 / len(cands) for c in cands}
        text = new_text(email)
        q = self.emb(text)
        sims = (self._knn_scores if self.cfg.method == "knn" else self._subspace_scores)(q, set(cands))
        sims[NONE] = max(sims[NONE], self.cfg.none_floor)

        score = {c: np.log(max(P[c], 1e-12)) + sims[c] / self.cfg.tau for c in cands}
        evidence = list(prior.evidence) if prior else []
        if self.cfg.w_id:
            for c in cands:
                if c != NONE and any(r.search(text) for r in self._key_res[c]):
                    score[c] += self.cfg.w_id
                    evidence.append(f"key term of {c} in text")
        best = max(sims, key=sims.get)
        evidence.append(f"semantic ({self.cfg.method}): closest {best} sim={sims[best]:.2f}")

        mx = max(score.values())
        z = sum(np.exp(s - mx) for s in score.values())
        return Posterior({c: float(np.exp(s - mx) / z) for c, s in score.items()}, evidence)
