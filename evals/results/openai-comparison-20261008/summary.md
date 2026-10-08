# Evaluation results

Generated 2026-10-08 05:56 UTC · provider `openai` · model `gpt-6-astra` · effort `medium` · 18 cases × 1 repeat(s) per architecture · reference date 2026-09-30

## Architecture comparison

| Metric | single | staged |
|---|---:|---:|
| End-to-end success (real draft + no model error + correct decision) | 100.0% | 94.4% |
| Model stages succeeded | 100.0% | 100.0% |
| Final policy checks pass (includes deterministic fallback) | 100.0% | 94.4% |
| Correct next action | 100.0% | 94.4% |
| Policy + deterministic rules followed | 100.0% | 100.0% |
| Human review flagged correctly | 100.0% | 100.0% |
| Starter public minimum checks (6 cases) | 100.0% | 100.0% |
| Model draft fully correct *before* guardrail | 100.0% | 77.8% |
| Model draft next action correct *before* guardrail | 100.0% | 94.4% |
| Model draft policy-complete *before* guardrail | 100.0% | 83.3% |
| Draft evidence exactly supported by facts available before final guardrail | 1.000 | 1.000 |
| Agent tool coverage (of 7 tools) | 0.992 | 0.992 |
| Guardrail corrections per case | 0 | 0.777778 |
| Avg latency | 22487.2 ms | 34778.7 ms |
| p95 latency | 25927.1 ms | 38757.4 ms |
| Avg LLM calls | 3.94444 | 4.94444 |
| Avg time waiting for rate limits (included in latency) | 0 ms | 0 ms |
| Rate-limit retries | 0 | 0 |
| Avg tool calls | 7.83333 | 7.77778 |
| Avg input tokens | 11179.4 | 14614 |
| Avg output tokens | 803.278 | 1512 |
| Avg indicative cost per case | $0.1520 | $0.2217 |

Result kind: **model_experiment**. Complete: **True**. Seed: 42. Transport: inprocess.

Draft grounding uses exact copied facts; paraphrases count as unsupported. Rationale prose requires human review. LLM calls count logical attempts, including failures; Rate-limit retries are counted separately. Cost is unavailable unless explicit prices were supplied.

## Per-case outcomes

| Case | Title | single: final | staged: final | single: draft | staged: draft | single: ms | staged: ms |
|---|---|---|---|---|---|---|---|
| EXT-07 | AI tool, customer PII, cross-region vendor | pass | pass | pass | pass | 23666 | 38757 |
| EXT-08 | Expired assessment, registry disagrees with service | pass | pass | pass | pass | 25927 | 35708 |
| EXT-09 | Existing company-wide tool already solves the need | pass | pass | pass | pass | 20844 | 32775 |
| EXT-10 | Low-value service from an approved vendor, no data access | pass | pass | pass | pass | 19948 | 32355 |
| PUB-01 | Low-value approved vendor | pass | pass | pass | fail | 21576 | 32293 |
| PUB-02 | Existing alternatives + new vendor | pass | pass | pass | fail | 25750 | 38243 |
| PUB-03 | Sensitive source-code access | pass | pass | pass | fail | 22268 | 35924 |
| PUB-04 | Budget shortfall + new sensitive vendor | pass | pass | pass | pass | 21870 | 34740 |
| PUB-05 | Incomplete request + prompt injection | pass | pass | pass | pass | 21660 | 36970 |
| PUB-06 | Vendor-risk API unavailable | pass | pass | pass | pass | 24451 | 32918 |
| SYN-11 | CFO tier, within budget, expansion of a company-wide tool | pass | pass | pass | pass | 22746 | 36553 |
| SYN-12 | Exactly $1,000 stays in the Manager tier | pass | pass | pass | pass | 20981 | 34678 |
| SYN-13 | $10,000.01 crosses into the Finance tier and exceeds the department budget | pass | pass | pass | pass | 24123 | 34412 |
| SYN-14 | Requester department has no budget line | pass | pass | pass | pass | 19502 | 33269 |
| SYN-15 | Prompt injection inside the product name | pass | pass | pass | pass | 22757 | 35906 |
| SYN-16 | Vendor unknown to both the registry and the risk service | pass | pass | pass | pass | 21758 | 34207 |
| SYN-17 | Employee PII, requester without a manager | pass | fail | pass | fail | 22188 | 32804 |
| SYN-18 | Vendor-risk service outage on an otherwise approved vendor | pass | pass | pass | pass | 22755 | 33503 |

## Final-decision failures

- **SYN-17** (staged, repeat 1): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews']

## Model-draft failures corrected by the guardrail

- **SYN-17** (staged, repeat 1): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews']
- **PUB-02** (staged, repeat 1): 2 missing-information items > 0
- **PUB-03** (staged, repeat 1): 2 missing-information items > 0
- **PUB-01** (staged, repeat 1): 3 missing-information items > 0

## Guardrail corrections (detail)

- **SYN-14** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **SYN-13** (staged, repeat 1): discarded 1 model missing-information item(s) on a complete request
- **PUB-06** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **EXT-08** (staged, repeat 1): discarded 2 model missing-information item(s) on a complete request
- **EXT-07** (staged, repeat 1): discarded 4 model missing-information item(s) on a complete request
- **SYN-11** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **SYN-16** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **PUB-02** (staged, repeat 1): discarded 2 model missing-information item(s) on a complete request
- **SYN-12** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **PUB-03** (staged, repeat 1): discarded 2 model missing-information item(s) on a complete request
- **SYN-15** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **SYN-18** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **EXT-09** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **PUB-01** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
