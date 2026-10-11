# Replay under the current policy layer

Experiment `openai-comparison-20261008` · policy v2026.09 · 36 saved trials · no model or tool calls.

The model drafts are the originals, so raw-draft scores are unchanged. Only the policy engine and guardrail were rerun.

| Architecture | Raw draft passed | Final passed, as run | Final passed, replayed |
|---|---:|---:|---:|
| single | 18/18 | 18/18 | 18/18 |
| staged | 14/18 | 17/18 | 18/18 |

## Trials whose final result changed

- **SYN-17** staged r1: fail → pass (final action `route_for_reviews`)

## Trials still failing after replay

None.
