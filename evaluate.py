"""Replay every instance through the pipeline and report accuracy.

    python evaluate.py                         # metadata only
    python evaluate.py --semantic              # metadata, then semantic when unconfident
    python evaluate.py --semantic --method subspace --tau 0.05 --split history
    python evaluate.py --semantic --llm        # + local LLM on what's still unresolved
    python evaluate.py --semantic --llm --prior-mode bayes --limit 10
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from context import NONE, Workspace
from metadata_model import MetadataStage
from pipeline import Pipeline, truth_of


def run_all(paths, pipeline):
    rows = []
    for path in paths:
        ws, records = Workspace.load(path)
        by_id = {r["email_id"]: r for r in records}
        for d in pipeline.run(ws, records):
            r = by_id[d.email_id]
            truth, truth_set = truth_of(r), set(r["label"]["matter_ids"]) or {NONE}
            meta = d.trace["metadata"]
            rows.append(dict(
                instance_id=ws.instance_id, email_id=d.email_id, split=r["split"],
                scenario=r["label"]["scenario"], difficulty=r["label"]["difficulty"], truth=truth,
                pred=d.prediction, confidence=round(d.posterior.confidence, 4), decided_by=d.decided_by,
                correct=d.prediction == truth, correct_any=d.prediction in truth_set,
                in_top3=truth in [k for k, _ in d.posterior.ranked(3)],
                meta_pred=meta.top, meta_conf=round(meta.confidence, 4), meta_correct=meta.top == truth,
                meta_in_top3=truth in [k for k, _ in meta.ranked(3)],
                **{f"{name}_correct": post.top == truth for name, post in d.trace.items()},
                **{f"{name}_in_top3": truth in [k for k, _ in post.ranked(3)] for name, post in d.trace.items()},
                llm_ran="llm" in d.trace and d.trace["llm"] is not d.trace.get("semantic"),
                top3=[(k, round(v, 4)) for k, v in d.posterior.ranked(3)], evidence=d.posterior.evidence))
    return rows


def pct(x):
    return f"{100 * x:5.1f}%"


def mean(rs, k="correct"):
    return sum(r[k] for r in rs) / len(rs) if rs else float("nan")


def compare(rows, before, after, title):
    """Before/after accuracy for one stage on the emails it was asked about."""
    print(f"\n{title} ({len(rows)}):")
    for k in ("correct", "in_top3"):
        lbl = "top-1" if k == "correct" else "top-3"
        print(f"  {lbl}  {before} {pct(mean(rows, f'{before}_{k}'))}  ->  +{after} {pct(mean(rows, f'{after}_{k}'))}")
    by = defaultdict(list)
    for r in rows:
        by[r["scenario"]].append(r)
    print(f"\n  {'scenario':<24}  n   {before[:4]} top-1  +{after[:4]} top-1  +{after[:4]} top-3  auto-assigned  acc_auto")
    for s, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        auto = [r for r in rs if r["decided_by"] == after]
        print(f"  {s:<24} {len(rs):4d}    {pct(mean(rs, f'{before}_correct'))}      {pct(mean(rs, f'{after}_correct'))}"
              f"       {pct(mean(rs, f'{after}_in_top3'))}       {pct(len(auto) / len(rs))}      {pct(mean(auto))}")


def summarize(rows, semantic, llm=False):
    n = len(rows)
    print(f"emails: {n}   final top-1 accuracy: {pct(mean(rows))}   (top-3: {pct(mean(rows, 'in_top3'))})\n")

    print("decided by        share   accuracy")
    groups = defaultdict(list)
    for r in rows:
        groups[r["decided_by"]].append(r)
    for g in ("metadata", "semantic", "llm", "needs_review"):
        if g in groups:
            print(f"  {g:<14} {pct(len(groups[g]) / n)}   {pct(mean(groups[g]))}")

    if semantic:
        compare([r for r in rows if r["decided_by"] != "metadata"], "metadata", "semantic",
                "emails metadata was unsure about")
    if llm:
        compare([r for r in rows if r["llm_ran"]], "semantic", "llm",
                "emails both earlier stages were unsure about (sent to the LLM)")

    print("\ncalibration of final confidence:  bin   n   accuracy")
    for lo, hi in [(0, .5), (.5, .7), (.7, .8), (.8, .9), (.9, .95), (.95, .99), (.99, 1.01)]:
        b = [r for r in rows if lo <= r["confidence"] < hi]
        if b:
            print(f"                     [{lo:.2f}, {min(hi, 1):.2f})  {len(b):5d}   {pct(mean(b))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--threshold", type=float, default=0.8, help="metadata stage confidence threshold")
    ap.add_argument("--sem-threshold", type=float, default=0.8, help="semantic stage confidence threshold")
    ap.add_argument("--split", choices=["incoming", "history", "all"], default="incoming")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--semantic", action="store_true")
    ap.add_argument("--method", choices=["knn", "subspace"], default="knn")
    ap.add_argument("--tau", type=float, default=0.12)
    ap.add_argument("--w-id", type=float, default=3.0, help="key-term boost; 0 = pure embeddings")
    ap.add_argument("--none-floor", type=float, default=0.4, help="similarity floor for 'no matter'")
    ap.add_argument("--llm", action="store_true", help="add the local LLM as stage 3 (needs --semantic)")
    ap.add_argument("--llm-model", default="mlx-community/Qwen3.5-4B-MLX-4bit")
    ap.add_argument("--llm-k", type=int, default=3, help="candidate matters shown to the LLM")
    ap.add_argument("--llm-history", type=int, default=15, help="filed emails per matter in the prompt (0 = all)")
    ap.add_argument("--prior-mode", choices=["in_prompt", "bayes", "none"], default="in_prompt")
    ap.add_argument("--llm-threshold", type=float, default=0.8)
    ap.add_argument("--out")
    args = ap.parse_args()

    paths = sorted(Path(args.data, "instances").glob("*.json"))[:args.limit]
    stages, thr = [MetadataStage()], [args.threshold]
    if args.semantic:
        from semantic_model import Embedder, SemanticStage, SemConfig, matter_text, new_text
        emb = Embedder()
        for p in paths:      # batch-encode up front (pure function of text, no labels involved)
            ws, recs = Workspace.load(p)
            from context import EmailView
            emb.warm([new_text(EmailView.from_record(r)) for r in recs] + [matter_text(m) for m in ws.matters])
        stages.append(SemanticStage(emb, SemConfig(method=args.method, tau=args.tau, w_id=args.w_id, none_floor=args.none_floor)))
        thr.append(args.sem_threshold)

    if args.llm:
        assert args.semantic, "--llm needs --semantic"
        from llm_model import LLMConfig, LLMStage
        only = None
        if args.split != "all":   # only spend LLM calls on the emails we will score
            only = {r["email_id"] for p in paths for r in Workspace.load(p)[1] if r["split"] == args.split}
        cfg = LLMConfig(model=args.llm_model, top_k=args.llm_k, max_history=args.llm_history,
                        prior_mode=args.prior_mode)
        stages.append(LLMStage(cfg, only_ids=only))
        thr.append(args.llm_threshold)

    rows = run_all(paths, Pipeline(stages, thr))
    name = "metadata" if not args.semantic else f"semantic_{args.method}"
    if args.llm:
        name += f"_llm_{args.prior_mode}"
    out = args.out or f"outputs/predictions_{name}.jsonl"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    if args.split != "all":
        rows = [r for r in rows if r["split"] == args.split]
    print(f"split={args.split}  stages={[s.name for s in stages]}"
          + (f"  method={args.method} tau={args.tau} w_id={args.w_id} none_floor={args.none_floor}" if args.semantic else "")
          + (f"\nllm={args.llm_model} k={args.llm_k} history={args.llm_history} prior_mode={args.prior_mode}" if args.llm else "")
          + "\n")
    summarize(rows, args.semantic, args.llm)
    print(f"\nper-email predictions -> {out}")


if __name__ == "__main__":
    main()
