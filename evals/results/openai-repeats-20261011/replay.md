# Replay under the current policy layer

Experiment `openai-repeats-20261011` · policy v2026.09 · 108 saved trials · no model or tool calls.

The model drafts are the originals, so raw-draft scores are unchanged. Only the policy engine and guardrail were rerun.

| Architecture | Raw draft passed | Final passed, as run | Final passed, replayed |
|---|---:|---:|---:|
| single | 54/54 | 54/54 | 54/54 |
| staged | 42/54 | 47/54 | 52/54 |

## Trials whose final result changed

- **SYN-17** staged r1: fail → pass (final action `route_for_reviews`)
- **PUB-03** staged r1: fail → pass (final action `route_for_reviews`)
- **PUB-03** staged r2: fail → pass (final action `route_for_reviews`)
- **SYN-17** staged r2: fail → pass (final action `route_for_reviews`)
- **SYN-17** staged r3: fail → pass (final action `route_for_reviews`)

## Trials still failing after replay

- **PUB-02** staged r1: approvals ['Department Head', 'Finance', 'Legal', 'Privacy', 'Procurement', 'Security'] != ['Department Head', 'Finance', 'Legal', 'Procurement', 'Security']
- **PUB-02** staged r3: approvals ['Department Head', 'Finance', 'Legal', 'Privacy', 'Procurement', 'Security'] != ['Department Head', 'Finance', 'Legal', 'Procurement', 'Security']
