# Precision follow-up

**4/4 final and raw checks passed:** SYN-12 ($1,000 threshold) and SYN-13 ($10,000.01 threshold), each through the single and staged architectures. Both selected evidence sets have exact support. The manifest and summary source fingerprints match the final agent code.

The main comparison exposed whole-dollar rounding in budget and legal evidence sentences. The update changes exactly three formatting expressions in `src/rules.py` from zero to two decimal places. Approval logic, arithmetic, prompts, case labels and action constraints are unchanged.

Three regression checks first reproduced the defect, including a $1,000.01 request against a $1,000 budget whose one-cent shortfall appeared as “by $0.” All 112 tests pass after the correction. The live SYN-13 decisions now retain both the **$10,000.01 cost** and **$3,000.01 shortfall** in their budget evidence.

These results verify the precision change only. They are not pooled into the [original architecture comparison](../openai-comparison-20261008/summary.md), whose 36 trials and source fingerprint remain unchanged.

To reproduce with the current source and your shell's `OPENAI_API_KEY`:

```bash
uv run python evals/run_evals.py --provider openai \
  --case-id SYN-12 --case-id SYN-13 --repeats 1
```

The command creates a new result directory, retaining prior evidence. Model outputs and latency can vary between runs.
