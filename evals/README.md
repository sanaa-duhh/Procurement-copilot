# Reproducing the comparison

The full runner evaluates **both architectures on the same 18 labelled cases**. It never sends expected answers to the model. The starter's six public cases and runner remain available separately. Start with the [saved experiment index](results/README.md), [complete comparison](results/openai-comparison-20261008/summary.md) and [case analysis](results/openai-comparison-20261008/case_analysis.md).

## Commands

```bash
uv run python evals/run_evals.py --provider mock
uv run python evals/run_evals.py --provider openai --case-id EXT-10
uv run python evals/run_evals.py --provider openai --repeats 1
```

The default vendor transport exercises the actual FastAPI handlers in-process. For an independently running HTTP service, start `uv run python run_local.py --no-ui` and add `--vendor-transport http`. The model still makes real tool calls in both modes; only the vendor service transport changes.

The live provider is OpenAI (`gpt-6-astra`, medium effort). `OPENAI_API_KEY` is read from the shell or ignored `.env`; there is no alternate-provider fallback. Strict function schemas and strict structured outputs are sent through the Responses API, then validated locally.

## What counts as success

| Metric | Meaning |
|---|---|
| `all_correct` | Final next action, exact approvals, required/forbidden flags, missing-field count and human-review flag match the labelled case |
| `model_success` | A schema-valid model draft exists and neither model stage reported an error |
| `end_to_end_success` | Final policy checks pass **and** model stages succeeded; fallback does not count |
| `raw_*` | Same policy/action checks before reconciliation; mandatory human review is imposed by the code contract |
| `draft_grounding_rate` | Exact `(source, finding, reference)` matches to policy-tool facts exposed before the final guardrail |
| `final_grounding_rate` | Exact matches between the final evidence panel and deterministic findings |
| `agent_tool_coverage` | Share of seven tools explicitly invoked by the agent; nested policy lookups remain distinct in the trace |
| `guardrail_corrections` | Logged field corrections, excluding routine templating of final instructions |
| `llm_calls` | Logical provider calls attempted, including failures; bounded rate-limit retries are recorded in separate columns |
| `tool_calls` | Executed tools, including nested lookups; cached returns are excluded |

Evidence support is deliberately conservative, **not semantic entailment**: paraphrases count as unsupported. Model rationale needs human review. The final guardrail's facts do not retroactively count as evidence that the model saw.

Final policy correctness can be 100% even when the model fails; always read it with end-to-end success and raw-draft quality. Exceptions remain in quality denominators. A scripted mock mirrors the engine and measures wiring, never architecture intelligence.

## Artifacts and experiment controls

Each invocation uses a new directory under `evals/results/live/` or the ignored `evals/results/mock/`. `--out PATH` sets a destination; existing trials cannot be overwritten.

- `manifest.json`: source/configuration identity required for safe resumption.
- `trials.jsonl`: flushed after every trial, including failures and the full decision/tool trace.
- `runs.csv`: one row per case, architecture and repeat; includes all columns even when the first trial fails.
- `decisions.jsonl`: final decision, raw draft and evidence trace for review.
- `summary.json`: metrics, provider/model/effort, Python version, seed, transport, source hash, Git commit and dirty status.
- `summary.md`: readable comparison, per-case outcomes and correction details.

Case order and architecture order within each pair are shuffled using `--seed` (default 42). Calls are sequential. Both architectures share one provider configuration; neither receives the other's conversation. The source hash covers code, cases, data and the lockfile.

By default a provider error stops a live experiment and produces an **incomplete** report with exit code 2. `--allow-degraded` continues but retains the failure. Exit code 1 means a completed experiment has failed cases; 0 means all end-to-end checks passed. Do not discard failed trials or turn a partial run into a complete comparison.

To continue unattempted trials after an interruption, repeat the original command with `--out THE_RUN_DIRECTORY --resume`. This requires identical source and settings; previous failures are retained and are not retried or excluded. A fresh retry experiment must use a new directory. OpenAI honours numeric Retry-After up to 60 seconds with at most two retries per call; wait time and retry counts are recorded separately from model quality.

Cost is `null` unless both `--input-price` and `--output-price` are supplied in USD per million tokens. This is an estimate from recorded usage, excludes cache discounts/retry overhead and is not a provider invoice. A free tier does not make unknown token pricing zero.

## Offline replay

`evals/replay.py` reruns the current policy engine and guardrail over a saved experiment's original drafts and rescores them. The tool cache is pre-filled from each trial's saved log, and the replay fails if any lookup misses it, so no tool or model is called. Raw-draft scores cannot change. Use it to measure what a policy-layer change does to final decisions while holding model behaviour fixed.

```bash
uv run python evals/replay.py evals/results/openai-repeats-20261011
```

It writes `replay.json` and `replay.md` beside the experiment. Replayed scores are reported next to the live ones, never in place of them.

## Case design and limits

`PUB-01..06` are the starter cases with stricter additional labels; `EXT-07..10` cover the remaining supplied requests. `SYN-11..18` cover CFO/threshold boundaries, absent budget, injection in a product name, an unknown vendor, employee PII and an injected vendor outage. `what_it_tests` explains each label.

Expected approvals are authored from policy, not generated from the engine at runtime. They are stricter than the starter minimum checks. The business-judgement coverage is still narrow: most cases are policy dominated and only EXT-09 insists on an existing-tool-first judgement. Before drawing broad conclusions, inspect rationales and add independently labelled gap/duplicate pairs. Repeated trials do not create more independent cases.

For the unchanged public runner, start the vendor API and run:

```bash
uv run python evals/run_public_evals.py --architecture single
uv run python evals/run_public_evals.py --architecture staged
```
