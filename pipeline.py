"""Staged matter classifier: each stage refines the previous stage's posterior.

    P(M | X_meta)                 <- MetadataStage
    P(M | X_sem, X_meta)          <- SemanticStage (next step), which takes the metadata
                                     posterior as its prior

If a stage's top probability clears its threshold, the pipeline stops there and
suggests that matter. Otherwise the email moves to the next stage. Whatever is
still unconfident after the last stage is flagged for the lawyer to pick.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from itertools import groupby

from context import NONE, Context, EmailView, FiledEmail, Workspace


@dataclass
class Posterior:
    probs: dict[str, float]                          # candidate -> probability (sums to 1)
    evidence: list[str] = field(default_factory=list)  # human-readable reasons

    @property
    def top(self) -> str:
        return max(self.probs, key=self.probs.get)

    @property
    def confidence(self) -> float:
        return self.probs[self.top]

    def ranked(self, k=3):
        return sorted(self.probs.items(), key=lambda kv: -kv[1])[:k]


class Stage(ABC):
    name = "stage"

    def reset(self, workspace: Workspace) -> None:
        """Called once per instance before any email is seen."""

    @abstractmethod
    def predict(self, email: EmailView, ctx: Context, prior: Posterior | None) -> Posterior:
        """Return a posterior over ctx.candidates. `prior` is the previous stage's output (None for the first stage)."""

    def observe(self, filed: FiledEmail, ctx: Context) -> None:
        """Called after an email is filed with its confirmed label. Update online state here."""


@dataclass
class Decision:
    email_id: str
    posterior: Posterior
    decided_by: str            # name of the stage that was confident, or "needs_review"
    trace: dict[str, Posterior]

    @property
    def prediction(self):
        return self.posterior.top

    @property
    def accepted(self):
        return self.decided_by != "needs_review"


class Pipeline:
    def __init__(self, stages: list[Stage], thresholds: list[float]):
        assert len(stages) == len(thresholds)
        self.stages, self.thresholds = stages, thresholds

    def classify(self, email: EmailView, ctx: Context) -> Decision:
        post, trace = None, {}
        for stage, thr in zip(self.stages, self.thresholds):
            post = stage.predict(email, ctx, post)
            trace[stage.name] = post
            if post.confidence >= thr:
                return Decision(email.email_id, post, stage.name, trace)
        return Decision(email.email_id, post, "needs_review", trace)

    def run(self, workspace: Workspace, records: list[dict]) -> list[Decision]:
        """Replay one instance's mailbox in time order.

        Emails with the same timestamp are all predicted before any of them is filed.
        Each email's label is read only after its prediction, when it goes into history
        (simulating the lawyer confirming or correcting every suggestion).
        """
        for s in self.stages:
            s.reset(workspace)
        history: list[FiledEmail] = []
        decisions = []
        records = sorted(records, key=lambda r: r["timestamp"])
        for _, group in groupby(records, key=lambda r: r["timestamp"]):
            group = list(group)
            views = [EmailView.from_record(r) for r in group]
            ctx = Context(workspace, history, views[0].timestamp)
            decisions += [self.classify(v, ctx) for v in views]
            for r, v in zip(group, views):     # lawyer confirms -> label becomes known
                filed = FiledEmail(v, tuple(r["label"]["matter_ids"]))
                history.append(filed)
                for s in self.stages:
                    s.observe(filed, ctx)
        return decisions


def truth_of(record) -> str:
    return record["label"]["primary_matter_id"] or NONE
