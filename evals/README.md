# Evaluation

Two runners, one case set, both architectures.

| Script | What it does |
|---|---|
| `run_public_evals.py` | The starter harness, unchanged in behaviour: six public cases, schema check, minimum expectations, latency. Writes `evals/results_<arch>.csv`. |
| `run_evals.py` | The full comparison: 18 cases (6 public + 4 further starter requests + 8 synthetic hidden-style cases), stricter checks, raw-draft vs final scoring, grounding, telemetry, cost. Writes `evals/results/`. |

```bash
uv run python run_local.py --no-ui              # terminal 1: vendor-risk mock API
uv run python evals/run_evals.py --repeats 3    # terminal 2: both architectures, all cases
uv run python evals/run_public_evals.py --architecture single
uv run python evals/run_public_evals.py --architecture staged
```

`--provider mock` runs the whole harness on the scripted stand-in model (no key, no network). Its output goes to `evals/results/mock/`, is git-ignored, and is never used as a reported result; it exists to prove the harness and the deterministic layer work.

## What is checked per case

| Check | Source of truth |
|---|---|
| `next_action_correct` | `expectations.next_action_any` in `cases.json` |
| `approvals_correct` | exact set match against the policy's minimum approvals (canonical names) |
| `flags_correct` | `risk_flags_must_contain` / `risk_flags_must_not_contain` |
| `missing_info_correct` | min / max count of missing-information items |
| `human_review_correct` | always `true` by policy section 11 |
| `policy_followed` | approvals, flags and missing information all correct |
| `all_correct` | every check above plus the next action |
| `public_min_checks_passed` | the starter's own `evaluate()` for the six public cases |
| `raw_*` | the same checks applied to the model's draft **before** the guardrail |
| `draft_grounding_rate` | share of draft evidence items whose `source` is a tool that actually ran in that request |
| `agent_tool_coverage` | share of the seven tools the agent itself invoked |
| `guardrail_corrections` | number of changes the deterministic layer had to make to the draft |

Latency is end-to-end per request (tool calls, model calls, policy engine, guardrail). LLM and tool calls come from the run telemetry in the output contract. Cost is indicative, from list prices per million tokens.

## Cases

`public_cases.json` is the starter file, untouched. `cases.json` holds the public six with stricter expectations plus:

- EXT-07..10: the remaining starter requests (AI + customer PII, expired/conflicting vendor, existing tool covers the need, clean low-value service).
- SYN-11..18: synthetic requests passed straight to the adapter, covering the CFO tier, both threshold boundaries, a department with no budget line, injection inside the product name, a vendor unknown to every source, employee PII with a requester who has no manager, and a simulated vendor-risk outage on an otherwise approved vendor.

Hidden cases use the same adapter; nothing here is keyed on a request ID.
