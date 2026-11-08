# Complication Task 4: Organizing Emails by Matter

Suggest which client matter an incoming email belongs to, so lawyers don't have to sort their inbox by hand.
Everything here runs on **synthetic data**, so no real client emails are involved.

## How it works

A 3-stage pipeline. Each stage hands its probability distribution to the next as a prior, and the
pipeline stops as soon as one stage is confident (≥ 0.8 by default):

1. **Metadata** (`metadata_model.py`) - P(matter | sender, recipients, thread, new-sender signal).
   Naive Bayes over who is on the email and which thread it continues.
2. **Semantic** (`semantic_model.py`) - MiniLM embeddings + FAISS nearest-neighbour search against each
   matter's intake description and previously filed emails, plus exact matching on matter numbers / case IDs.
3. **LLM** (`llm_model.py`) - a local open-weight model (Qwen3.5-4B via MLX) reads the top 3 candidate
   matters (intake info + recently filed emails), the earlier stages' probabilities and the email, then
   picks one.

Anything still unconfident is left for the lawyer, with the top 3 suggestions.

**No leakage:** emails are replayed in time order. A prediction only sees emails filed *before* it and
matters already opened. `test_leakage.py` checks this.

## Results so far (held-out `incoming` emails, 1,031 total)

| Pipeline | Top-1 accuracy | Top-3 |
|---|---|---|
| Metadata only | 82.8% | 95.3% |
| Metadata + semantic | 91.4% | 99.4% |
| + LLM | in progress | |

With metadata + semantic, 66% of emails are auto-assigned by metadata (98.7% accurate) and 13% by
semantic search (91.5% accurate); 21% are left for review.

## Getting started

```bash
pip install -r requirements.txt        # mlx-lm (LLM stage) needs Apple Silicon

python generate_data.py                # regenerate data/ (already committed; deterministic)
python evaluate.py                     # metadata stage only
python evaluate.py --semantic          # metadata + semantic
python evaluate.py --semantic --llm --limit 2   # + LLM on 2 workspaces (~40s per LLM call on an M2)
python test_leakage.py                 # leakage checks
python tune.py                         # tune semantic settings on the history split
```

Per-email predictions (with probabilities and reasons) are written to `outputs/`.
Run `python evaluate.py --help` to see all options (thresholds, kNN vs SVD-subspace, LLM model, prior mode...).

## Repo layout

| File | What it is |
|---|---|
| `generate_data.py`, `templates.py` | Synthetic data generator (50 workspaces, ~2,500 labeled emails) |
| `SCHEMA.md` | Data schema, scenarios, and how difficulty labels are defined |
| `context.py` | What the app knows at a point in time (email view without labels, matters, history) |
| `pipeline.py` | Stage interface + time-ordered replay |
| `metadata_model.py`, `semantic_model.py`, `llm_model.py` | The three stages |
| `evaluate.py`, `tune.py`, `test_leakage.py` | Evaluation, tuning, leakage tests |

## Known gaps / ideas

- Emails covering several matters: we pick one, but the right ones are usually in the top 3.
- A reply that changes topic mid-thread gets confidently filed under the old matter.
- Generic emails ("Quick call?") have too little text for semantic search to help.
- The synthetic emails are template-based, so the next step is a harder, more varied test set.
