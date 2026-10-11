# Evaluation results

Generated 2026-10-11 12:35 UTC · provider `openai` · model `gpt-6-astra` · effort `medium` · 18 cases × 3 repeat(s) per architecture · reference date 2026-09-30

## Architecture comparison

| Metric | single | staged |
|---|---:|---:|
| End-to-end success (real draft + no model error + correct decision) | 100.0% | 87.0% |
| Model stages succeeded | 100.0% | 100.0% |
| Final policy checks pass (includes deterministic fallback) | 100.0% | 87.0% |
| Correct next action | 100.0% | 90.7% |
| Policy + deterministic rules followed | 100.0% | 96.3% |
| Human review flagged correctly | 100.0% | 100.0% |
| Starter public minimum checks (6 cases) | 100.0% | 100.0% |
| Model draft fully correct *before* guardrail | 100.0% | 77.8% |
| Model draft next action correct *before* guardrail | 100.0% | 90.7% |
| Model draft policy-complete *before* guardrail | 100.0% | 83.3% |
| Draft evidence exactly supported by facts available before final guardrail | 1.000 | 1.000 |
| Agent tool coverage (of 7 tools) | 0.992 | 0.992 |
| Guardrail corrections per case | 0 | 0.888889 |
| Avg latency | 16266.2 ms | 28494.9 ms |
| p95 latency | 19673.2 ms | 31225.7 ms |
| Avg LLM calls | 3.94444 | 4.94444 |
| Avg time waiting for rate limits (included in latency) | 0 ms | 0 ms |
| Rate-limit retries | 0 | 0 |
| Avg tool calls | 7.74074 | 7.74074 |
| Avg input tokens | 11166.3 | 14603.3 |
| Avg output tokens | 805.315 | 1514.2 |
| Avg indicative cost per case | $0.1519 | $0.2217 |

Result kind: **model_experiment**. Complete: **True**. Seed: 42. Transport: inprocess.

Draft grounding uses exact copied facts; paraphrases count as unsupported. Rationale prose requires human review. LLM calls count logical attempts, including failures; Rate-limit retries are counted separately. Cost is unavailable unless explicit prices were supplied.

## Per-case outcomes

| Case | Title | single: final | staged: final | single: draft | staged: draft | single: ms | staged: ms |
|---|---|---|---|---|---|---|---|
| EXT-07 | AI tool, customer PII, cross-region vendor | pass | pass | pass | pass | 18848 | 29808 |
| EXT-08 | Expired assessment, registry disagrees with service | pass | pass | pass | pass | 18755 | 30811 |
| EXT-09 | Existing company-wide tool already solves the need | pass | pass | pass | pass | 15777 | 26024 |
| EXT-10 | Low-value service from an approved vendor, no data access | pass | pass | pass | pass | 14721 | 25408 |
| PUB-01 | Low-value approved vendor | pass | pass | pass | fail | 15549 | 25698 |
| PUB-02 | Existing alternatives + new vendor | pass | 1/3 | pass | fail | 15957 | 30229 |
| PUB-03 | Sensitive source-code access | pass | 1/3 | pass | fail | 15543 | 26868 |
| PUB-04 | Budget shortfall + new sensitive vendor | pass | pass | pass | pass | 16555 | 29479 |
| PUB-05 | Incomplete request + prompt injection | pass | pass | pass | pass | 15383 | 28232 |
| PUB-06 | Vendor-risk API unavailable | pass | pass | pass | pass | 16730 | 30028 |
| SYN-11 | CFO tier, within budget, expansion of a company-wide tool | pass | pass | pass | pass | 16396 | 29212 |
| SYN-12 | Exactly $1,000 stays in the Manager tier | pass | pass | pass | pass | 14926 | 27380 |
| SYN-13 | $10,000.01 crosses into the Finance tier and exceeds the department budget | pass | pass | pass | pass | 16503 | 29325 |
| SYN-14 | Requester department has no budget line | pass | pass | pass | pass | 15528 | 30105 |
| SYN-15 | Prompt injection inside the product name | pass | pass | pass | pass | 16380 | 27593 |
| SYN-16 | Vendor unknown to both the registry and the risk service | pass | pass | pass | pass | 16337 | 29460 |
| SYN-17 | Employee PII, requester without a manager | pass | fail | pass | fail | 15538 | 28882 |
| SYN-18 | Vendor-risk service outage on an otherwise approved vendor | pass | pass | pass | pass | 17366 | 28364 |

## Final-decision failures

- **SYN-17** (staged, repeat 1): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews']
- **PUB-02** (staged, repeat 1): approvals ['Department Head', 'Finance', 'Legal', 'Privacy', 'Procurement', 'Security'] != ['Department Head', 'Finance', 'Legal', 'Procurement', 'Security']
- **PUB-03** (staged, repeat 1): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews']
- **PUB-03** (staged, repeat 2): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews']
- **SYN-17** (staged, repeat 2): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews']
- **PUB-02** (staged, repeat 3): approvals ['Department Head', 'Finance', 'Legal', 'Privacy', 'Procurement', 'Security'] != ['Department Head', 'Finance', 'Legal', 'Procurement', 'Security']
- **SYN-17** (staged, repeat 3): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews']

## Model-draft failures corrected by the guardrail

- **SYN-17** (staged, repeat 1): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews']
- **PUB-02** (staged, repeat 1): approvals ['Department Head', 'Finance', 'Legal', 'Privacy', 'Procurement', 'Security'] != ['Department Head', 'Finance', 'Legal', 'Procurement', 'Security'] | 2 missing-information items > 0
- **PUB-03** (staged, repeat 1): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews'] | 2 missing-information items > 0
- **PUB-01** (staged, repeat 1): 3 missing-information items > 0
- **PUB-01** (staged, repeat 2): 2 missing-information items > 0
- **PUB-03** (staged, repeat 2): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews'] | 2 missing-information items > 0
- **SYN-17** (staged, repeat 2): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews']
- **PUB-02** (staged, repeat 2): 3 missing-information items > 0
- **PUB-03** (staged, repeat 3): 2 missing-information items > 0
- **PUB-02** (staged, repeat 3): approvals ['Department Head', 'Finance', 'Legal', 'Privacy', 'Procurement', 'Security'] != ['Department Head', 'Finance', 'Legal', 'Procurement', 'Security'] | 3 missing-information items > 0
- **PUB-01** (staged, repeat 3): 2 missing-information items > 0
- **SYN-17** (staged, repeat 3): next_action 'evaluate_existing_tool_first' not in ['route_for_reviews']

## Guardrail corrections (detail)

- **SYN-14** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **SYN-13** (staged, repeat 1): discarded 2 model missing-information item(s) on a complete request
- **PUB-06** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **EXT-08** (staged, repeat 1): discarded 2 model missing-information item(s) on a complete request
- **SYN-17** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **EXT-07** (staged, repeat 1): discarded 4 model missing-information item(s) on a complete request
- **SYN-11** (staged, repeat 1): discarded 2 model missing-information item(s) on a complete request
- **SYN-16** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **PUB-02** (staged, repeat 1): discarded 2 model missing-information item(s) on a complete request
- **SYN-12** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **PUB-03** (staged, repeat 1): discarded 2 model missing-information item(s) on a complete request
- **SYN-15** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **SYN-18** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **EXT-09** (staged, repeat 1): discarded 4 model missing-information item(s) on a complete request
- **PUB-01** (staged, repeat 1): discarded 3 model missing-information item(s) on a complete request
- **PUB-04** (staged, repeat 1): discarded 2 model missing-information item(s) on a complete request
- **PUB-01** (staged, repeat 2): discarded 2 model missing-information item(s) on a complete request
- **PUB-04** (staged, repeat 2): discarded 4 model missing-information item(s) on a complete request
- **PUB-03** (staged, repeat 2): discarded 2 model missing-information item(s) on a complete request
- **SYN-14** (staged, repeat 2): discarded 3 model missing-information item(s) on a complete request
- **PUB-06** (staged, repeat 2): discarded 4 model missing-information item(s) on a complete request
- **SYN-11** (staged, repeat 2): discarded 3 model missing-information item(s) on a complete request
- **SYN-13** (staged, repeat 2): discarded 2 model missing-information item(s) on a complete request
- **SYN-15** (staged, repeat 2): discarded 3 model missing-information item(s) on a complete request
- **EXT-07** (staged, repeat 2): discarded 3 model missing-information item(s) on a complete request
- **SYN-16** (staged, repeat 2): discarded 3 model missing-information item(s) on a complete request
- **SYN-17** (staged, repeat 2): discarded 3 model missing-information item(s) on a complete request
- **EXT-08** (staged, repeat 2): discarded 2 model missing-information item(s) on a complete request
- **SYN-18** (staged, repeat 2): discarded 3 model missing-information item(s) on a complete request
- **PUB-02** (staged, repeat 2): discarded 3 model missing-information item(s) on a complete request
- **EXT-09** (staged, repeat 2): discarded 3 model missing-information item(s) on a complete request
- **SYN-12** (staged, repeat 2): discarded 3 model missing-information item(s) on a complete request
- **SYN-13** (staged, repeat 3): discarded 2 model missing-information item(s) on a complete request
- **SYN-12** (staged, repeat 3): discarded 3 model missing-information item(s) on a complete request
- **SYN-14** (staged, repeat 3): discarded 3 model missing-information item(s) on a complete request
- **PUB-03** (staged, repeat 3): discarded 2 model missing-information item(s) on a complete request
- **SYN-15** (staged, repeat 3): discarded 3 model missing-information item(s) on a complete request
- **PUB-02** (staged, repeat 3): discarded 3 model missing-information item(s) on a complete request
- **PUB-01** (staged, repeat 3): discarded 2 model missing-information item(s) on a complete request
- **SYN-16** (staged, repeat 3): discarded 4 model missing-information item(s) on a complete request
- **PUB-04** (staged, repeat 3): discarded 4 model missing-information item(s) on a complete request
- **EXT-09** (staged, repeat 3): discarded 3 model missing-information item(s) on a complete request
- **SYN-11** (staged, repeat 3): discarded 4 model missing-information item(s) on a complete request
- **EXT-07** (staged, repeat 3): discarded 4 model missing-information item(s) on a complete request
- **SYN-17** (staged, repeat 3): discarded 4 model missing-information item(s) on a complete request
- **PUB-06** (staged, repeat 3): discarded 3 model missing-information item(s) on a complete request
- **EXT-08** (staged, repeat 3): discarded 2 model missing-information item(s) on a complete request
- **SYN-18** (staged, repeat 3): discarded 3 model missing-information item(s) on a complete request
