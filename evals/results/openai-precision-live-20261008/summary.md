# Evaluation results

Generated 2026-10-08 06:04 UTC · provider `openai` · model `gpt-6-astra` · effort `medium` · 2 cases × 1 repeat(s) per architecture · reference date 2026-09-30

## Architecture comparison

| Metric | single | staged |
|---|---:|---:|
| End-to-end success (real draft + no model error + correct decision) | 100.0% | 100.0% |
| Model stages succeeded | 100.0% | 100.0% |
| Final policy checks pass (includes deterministic fallback) | 100.0% | 100.0% |
| Correct next action | 100.0% | 100.0% |
| Policy + deterministic rules followed | 100.0% | 100.0% |
| Human review flagged correctly | 100.0% | 100.0% |
| Starter public minimum checks (6 cases) | n/a | n/a |
| Model draft fully correct *before* guardrail | 100.0% | 100.0% |
| Model draft next action correct *before* guardrail | 100.0% | 100.0% |
| Model draft policy-complete *before* guardrail | 100.0% | 100.0% |
| Draft evidence exactly supported by facts available before final guardrail | 1.000 | 1.000 |
| Agent tool coverage (of 7 tools) | 1.000 | 1.000 |
| Guardrail corrections per case | 0 | 1 |
| Avg latency | 25072.5 ms | 38390.5 ms |
| p95 latency | 27527 ms | 38605.1 ms |
| Avg LLM calls | 4 | 5 |
| Avg time waiting for rate limits (included in latency) | 0 ms | 0 ms |
| Rate-limit retries | 0 | 0 |
| Avg tool calls | 8 | 8 |
| Avg input tokens | 11411 | 14877.5 |
| Avg output tokens | 821.5 | 1484.5 |
| Avg indicative cost per case | $0.1552 | $0.2230 |

Result kind: **model_experiment**. Complete: **True**. Seed: 42. Transport: inprocess.

Draft grounding uses exact copied facts; paraphrases count as unsupported. Rationale prose requires human review. LLM calls count logical attempts, including failures; Rate-limit retries are counted separately. Cost is unavailable unless explicit prices were supplied.

## Per-case outcomes

| Case | Title | single: final | staged: final | single: draft | staged: draft | single: ms | staged: ms |
|---|---|---|---|---|---|---|---|
| SYN-12 | Exactly $1,000 stays in the Manager tier | pass | pass | pass | pass | 22618 | 38176 |
| SYN-13 | $10,000.01 crosses into the Finance tier and exceeds the department budget | pass | pass | pass | pass | 27527 | 38605 |

## Final-decision failures

None.

## Model-draft failures corrected by the guardrail

None.

## Guardrail corrections (detail)

- **SYN-13** (staged, repeat 1): discarded 2 model missing-information item(s) on a complete request
- **SYN-12** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
