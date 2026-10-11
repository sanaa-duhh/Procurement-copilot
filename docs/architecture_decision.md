# Architecture decision

**Ship the single agent for a supervised internal pilot.** It pairs model judgement with code-owned policy and verified evidence. A human stays responsible for every approval and exception.

## Evidence

Both architectures ran the same 18 labelled cases three times: 108 live trials with OpenAI `gpt-6-astra` at medium reasoning, with the same tools, guardrail and contract, and paired order shuffled with seed 42 ([summary](../evals/results/openai-repeats-20261011/summary.md), [case analysis](../evals/results/openai-repeats-20261011/case_analysis.md)).

| Metric | Single agent | Staged / 2-agent |
|---|---:|---:|
| Raw draft passed, before guardrail | **54/54** | 42/54 |
| Final checks passed, as run | **54/54** | 47/54 |
| Final checks, replayed under the current policy layer | **54/54** | 52/54 |
| Mean latency | **16.3 s** | 28.5 s |
| Mean model / tool calls | 3.94 / 7.74 | 4.94 / 7.74 |
| Indicative cost per request | **$0.152** | $0.222 |

The [first experiment](../evals/results/openai-comparison-20261008/summary.md), one repeat on the earlier source, agreed: 18/18 against 17/18. Neither run had provider errors.

## Trade-offs

The staged reviewer's failures share one cause. When a request overlaps an existing tool, it wants spare capacity verified first, even when specialist reviews are required: SYN-17 in all three repeats, PUB-03 in two. On PUB-02 it twice added an unneeded Privacy review. No failure dropped a required control.

The review order was also a gap in the policy layer: the engine allowed both orders. It is now an explicit rule in `config/policy.toml`, and specialist reviews start first. [Replaying](../evals/results/openai-repeats-20261011/replay.md) the saved drafts through the updated guardrail, with no model calls, lifts staged's final score to 52/54.

That fix narrows the final gap, but it does not change the decision. The guardrail now protects both designs equally. What separates them is the model's own output before correction: 54/54 against 42/54. Staged needs an extra model call, about 35% more tokens, and 12 more seconds per request to produce worse drafts.

## Risks and limitations

- **Labels.** The 18 cases are developer-labelled, and most test rules the code enforces. Three repeats show consistency, not a larger sample.
- **Review order.** Putting specialist reviews first is a policy choice. It should be confirmed with Procurement; the setting is one line in the config.
- **Judgement coverage.** Overlap judgement, where the model matters most, needs independently labelled duplicate-versus-gap cases.
- **Production.** Rollout needs authenticated reviewers, durable audit storage, real approval routing, and measurement over HTTP under concurrency.

## Why this is the right MVP

Policy that must never be wrong is enforced in code, so either design is safe. What remains is the quality of the recommendation itself. On that, the simpler design matched the labels every time, while the extra role departed from them repeatably. The single agent is the stronger and simpler answer; keep the staged design for experiments on harder judgement cases.
