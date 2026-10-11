# Architecture decision

**Ship the single agent for a supervised internal pilot.** It pairs model judgement with code-owned policy checks and verified evidence. A human stays responsible for every approval and exception.

## Evidence

Both architectures ran the same 18 labelled cases three times on the current source: 108 live trials with OpenAI `gpt-6-astra` at medium reasoning. They shared the same tools, guardrail and output contract, with paired order shuffled with seed 42 ([summary](../evals/results/openai-repeats-20261011/summary.md), [case analysis](../evals/results/openai-repeats-20261011/case_analysis.md)).

| Metric | Single agent | Staged / 2-agent |
|---|---:|---:|
| Final checks passed | **54/54** | 47/54 |
| Raw draft passed, before guardrail | **54/54** | 42/54 |
| Human review and evidence support | 100% | 100% |
| Mean latency | **16.3 s** | 28.5 s |
| Mean model / tool calls | 3.94 / 7.74 | 4.94 / 7.74 |
| Indicative cost per request | **$0.152** | $0.222 |

The [first experiment](../evals/results/openai-comparison-20261008/summary.md), one repeat on the earlier source, pointed the same way: 18/18 against 17/18. Neither run had provider errors or rate-limit retries.

## Trade-offs

The single agent passed every trial and never needed a guardrail correction. It was 43% faster and 31% cheaper.

The staged reviewer's seven failures share one cause. When a request overlaps an existing tool, it wants spare capacity verified before anything else, even when specialist reviews are required. It did this on SYN-17 in all three repeats and on PUB-03 in two. On PUB-02 it twice added an unneeded Privacy review. No failure dropped a required control, and each rationale is defensible. The behaviour is systematic, not random.

The second role therefore adds a sceptical voice, not measured quality. It does so at the price of an extra model call, about 35% more tokens, and a 12-second wait per request.

## Risks and limitations

- **Labels.** The 18 cases are developer-labelled, and most test rules the code already enforces. Three repeats show consistency, not a larger sample.
- **Sequencing.** Whether "check existing capacity" should come before specialist reviews is a procurement decision. The labels put reviews first, and the staged reviewer disagrees. Procurement owners should settle this before it is treated as settled policy.
- **Judgement coverage.** Overlap judgement, where the model matters most, needs more independently labelled duplicate-versus-gap cases.
- **Production.** Rollout needs authenticated reviewers, durable audit storage, real approval routing, and measurements over HTTP under concurrency.

## Why this is the right MVP

The policy that must never be wrong is enforced in code, so either architecture is safe. What remains is the quality of the model's own recommendation. On that, the simpler design matched the labels every time while the extra role departed from them repeatably. A second agent would add latency, cost and another prompt to maintain, without a measured benefit. The single agent is the stronger and simpler answer. Keep the staged design available for experiments on harder judgement cases.
