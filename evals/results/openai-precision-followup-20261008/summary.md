# Evaluation results

Generated 2026-10-08 05:59 UTC · provider `openai` · model `gpt-6-astra` · effort `medium` · 2 cases × 1 repeat(s) per architecture · reference date 2026-09-30

## Architecture comparison

| Metric | single | staged |
|---|---:|---:|
| End-to-end success (real draft + no model error + correct decision) | n/a | 0.0% |
| Model stages succeeded | n/a | 0.0% |
| Final policy checks pass (includes deterministic fallback) | n/a | 100.0% |
| Correct next action | n/a | 100.0% |
| Policy + deterministic rules followed | n/a | 100.0% |
| Human review flagged correctly | n/a | 100.0% |
| Starter public minimum checks (6 cases) | n/a | n/a |
| Model draft fully correct *before* guardrail | n/a | 0.0% |
| Model draft next action correct *before* guardrail | n/a | 0.0% |
| Model draft policy-complete *before* guardrail | n/a | 0.0% |
| Draft evidence exactly supported by facts available before final guardrail | n/a | 0.000 |
| Agent tool coverage (of 7 tools) | n/a | 0.000 |
| Guardrail corrections per case | n/a | 1 |
| Avg latency | n/a | 10528.1 ms |
| p95 latency | n/a | 10528.1 ms |
| Avg LLM calls | n/a | 2 |
| Avg time waiting for rate limits (included in latency) | n/a | 0 ms |
| Rate-limit retries | 0 | 0 |
| Avg tool calls | n/a | 6 |
| Avg input tokens | n/a | 0 |
| Avg output tokens | n/a | 0 |
| Avg indicative cost per case | n/a | $0.0000 |

Result kind: **model_experiment**. Complete: **False**. Seed: 42. Transport: inprocess.

Draft grounding uses exact copied facts; paraphrases count as unsupported. Rationale prose requires human review. LLM calls count logical attempts, including failures; Rate-limit retries are counted separately. Cost is unavailable unless explicit prices were supplied.

## Per-case outcomes

| Case | Title | single: final | staged: final | single: draft | staged: draft | single: ms | staged: ms |
|---|---|---|---|---|---|---|---|
| SYN-13 | $10,000.01 crosses into the Finance tier and exceeds the department budget | – | pass | – | fail | – | 10528 |

## Final-decision failures

None.

## Model-draft failures corrected by the guardrail

- **SYN-13** (staged, repeat 1): no draft

## Guardrail corrections (detail)

- **SYN-13** (staged, repeat 1): model produced no usable draft; deterministic findings only
