"""Grid-search the semantic stage on the `history` split only (keeps `incoming` held out).

    python tune.py
"""

import itertools
from pathlib import Path

from context import EmailView, Workspace
from evaluate import mean, pct, run_all
from metadata_model import MetadataStage
from pipeline import Pipeline
from semantic_model import Embedder, SemanticStage, SemConfig, matter_text, new_text


def main():
    paths = sorted(Path("data/instances").glob("*.json"))
    emb = Embedder()
    for p in paths:
        ws, recs = Workspace.load(p)
        emb.warm([new_text(EmailView.from_record(r)) for r in recs] + [matter_text(m) for m in ws.matters])

    print("method    tau   floor   top-1   deferred top-1   sem auto-assigned   sem acc_auto")
    results = []
    for method, tau, floor in itertools.product(["knn", "subspace"], [0.08, 0.12, 0.2], [0.0, 0.3, 0.35, 0.4, 0.45]):
        cfg = SemConfig(method=method, tau=tau, none_floor=floor)
        pipe = Pipeline([MetadataStage(), SemanticStage(emb, cfg)], [0.8, 0.8])
        rows = [r for r in run_all(paths, pipe) if r["split"] == "history"]
        deferred = [r for r in rows if r["decided_by"] != "metadata"]
        auto = [r for r in rows if r["decided_by"] == "semantic"]
        results.append((mean(deferred), method, tau, floor))
        print(f"{method:<9} {tau:4.2f}  {floor:4.2f}    {pct(mean(rows))}   {pct(mean(deferred))}"
              f"          {pct(len(auto) / len(deferred))}            {pct(mean(auto))}")
    best = max(results)
    print(f"\nbest on history (deferred top-1): method={best[1]} tau={best[2]} none_floor={best[3]}")


if __name__ == "__main__":
    main()
