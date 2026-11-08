"""Leakage checks: a prediction must not change if anything in the future changes.

    python test_leakage.py
"""

import copy
import math
import random
from pathlib import Path

from context import NONE, EmailView, Workspace
from metadata_model import MetadataStage
from pipeline import Pipeline
from semantic_model import Embedder, SemanticStage

INSTANCES = sorted(Path("data/instances").glob("*.json"))[:5]
EMB = Embedder()


def run(ws, records):
    """Full pipeline; threshold 1.01 forces every email through the semantic stage too."""
    pipe = Pipeline([MetadataStage(), SemanticStage(EMB)], [1.01, 1.01])
    return {d.email_id: d.posterior.probs for d in pipe.run(ws, records)}


def same(p, q):
    return p.keys() == q.keys() and all(math.isclose(p[k], q[k], abs_tol=1e-12) for k in p)


def test_future_removed_or_scrambled():
    rng = random.Random(0)
    for path in INSTANCES:
        ws, records = Workspace.load(path)
        records = sorted(records, key=lambda r: r["timestamp"])
        full = run(ws, records)
        for k in rng.sample(range(len(records)), 8):
            t = records[k]["timestamp"]
            # 1) delete every email at or after t except the one being predicted
            past = [r for r in records if r["timestamp"] < t] + [records[k]]
            assert same(run(ws, past)[records[k]["email_id"]], full[records[k]["email_id"]]), path

            # 2) scramble labels of the target and all future emails
            scrambled = copy.deepcopy(records)
            mids = [m.matter_id for m in ws.matters]
            for r in scrambled:
                if r["timestamp"] >= t:
                    r["label"]["matter_ids"] = [rng.choice(mids)]
                    r["label"]["primary_matter_id"] = r["label"]["matter_ids"][0]
            assert same(run(ws, scrambled)[records[k]["email_id"]], full[records[k]["email_id"]]), path


def test_stage_never_sees_labels():
    assert "label" not in EmailView.__dataclass_fields__
    seen = []

    class Spy(MetadataStage):
        def predict(self, email, ctx, prior=None):
            assert isinstance(email, EmailView)
            assert all(f.email.timestamp < email.timestamp for f in ctx.history)
            assert all(m.opened_on <= email.timestamp.date() for m in ctx.open_matters)
            seen.append(email.email_id)
            return super().predict(email, ctx, prior)

    ws, records = Workspace.load(INSTANCES[0])
    Pipeline([Spy(), SemanticStage(EMB)], [0.8, 0.8]).run(ws, records)
    assert len(seen) == len(records)


def test_unopened_matters_excluded():
    ws, records = Workspace.load(INSTANCES[0])
    first = min(records, key=lambda r: r["timestamp"])
    probs = run(ws, [first])[first["email_id"]]
    day = first["timestamp"][:10]
    assert set(probs) == {m.matter_id for m in ws.matters if str(m.opened_on) <= day} | {NONE}


def test_llm_prompt_has_no_future():
    """The LLM prompt for an email must be identical with or without any future emails."""
    from llm_model import LLMStage

    class PromptOnly(LLMStage):
        def predict(self, email, ctx, prior):
            P = prior.probs
            top = [c for c in sorted(P, key=P.get, reverse=True) if c != NONE][:3]
            self.prompts[email.email_id] = self.build_prompt(email, ctx, sorted(top) + [NONE], P)
            return prior

    def prompts(ws, records):
        stage = PromptOnly(cache_dir="outputs/llm_cache_test")
        stage.prompts = {}
        Pipeline([MetadataStage(), SemanticStage(EMB), stage], [1.01, 1.01, 1.01]).run(ws, records)
        return stage.prompts

    rng = random.Random(1)
    for path in INSTANCES[:3]:
        ws, records = Workspace.load(path)
        records = sorted(records, key=lambda r: r["timestamp"])
        full = prompts(ws, records)
        for k in rng.sample(range(len(records)), 6):
            t = records[k]["timestamp"]
            past = [r for r in records if r["timestamp"] < t] + [records[k]]
            assert prompts(ws, past)[records[k]["email_id"]] == full[records[k]["email_id"]], path


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
