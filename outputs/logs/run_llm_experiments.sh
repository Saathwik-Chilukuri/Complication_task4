#!/bin/zsh
# Full held-out run with priors in the prompt, then prior-mode ablations on 15 workspaces.
cd /Users/sudhakarchilukuri/complication4
F='Redirects|HF_TOKEN|Loading weights|resource_tracker|warnings.warn|Fetching'
python3 evaluate.py --semantic --llm --prior-mode in_prompt 2>&1 | grep -vE "$F" > outputs/logs/llm_in_prompt_full.txt
for mode in in_prompt bayes none; do
  python3 evaluate.py --semantic --llm --prior-mode $mode --limit 15 --out outputs/predictions_llm_${mode}_15.jsonl 2>&1 | grep -vE "$F" > outputs/logs/llm_${mode}_15.txt
done
echo done > outputs/logs/ALL_DONE
