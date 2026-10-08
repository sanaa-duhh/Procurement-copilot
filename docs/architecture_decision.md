# Architecture decision

**Ship the single agent for a supervised internal pilot.** It combines model judgement with code-owned policy checks and verified evidence; a human remains responsible for approvals and exceptions.

The [complete comparison](../evals/results/openai-comparison-20261008/summary.md) ran 18 cases once per architecture using OpenAI `gpt-6-astra`, medium reasoning, the same tools and guardrail, and paired order shuffled with seed 42. Real model calls used the actual vendor API handlers in-process. Source fingerprints and full traces are retained; incomplete integration pilots are excluded.

The single agent passed **18/18 final and raw-draft checks**. Staged passed **17/18 final checks and 14/18 raw-draft checks**. Both preserved the required approval sets and human-review boundary, had no provider failures, and achieved 100% exact support for selected evidence. Exact copying does not validate free-form rationale or independently prove the underlying facts.

Single averaged **22.5 seconds and 3.94 model calls**, compared with **34.8 seconds and 4.94 calls** for staged: 35% lower observed latency. Indicative token cost was **$0.152 versus $0.222 per request**, using explicit input/output price assumptions. No rate-limit retries contributed to latency.

The sole staged final failure, **SYN-17**, is a sequencing disagreement: it checks the existing DocSpace licence before routing the employee-PII use case for review. It retains Security and Privacy approvals, but the label requires reviews first. This is not evidence of an omitted privacy control. Accepting both sequences would make that case a tie; the latency/cost argument would still favour single. Labels were not relaxed after observing results.

Staged needed 14 field corrections across 18 requests; single needed none. These mainly concern useful follow-up questions placed in the required-intake field, not fabricated evidence. The UI now exposes retained questions separately for human consideration. The staged reviewer also noticed rounded budget prose on **SYN-13**. A subsequent fix preserves cents; separate threshold trials and regression tests verify it without rewriting the original comparison.

The second role produced useful observations, but this experiment does not establish a quality gain that justifies its extra call and tokens. Keep staged available for further experiments, not as the default deployment.

The evidence is limited: one trial per architecture, a small developer-authored and mostly policy-driven case set, no independent judgement labels, and local vendor transport. Next, test independently labelled duplicate-versus-gap cases, resolve review sequencing with procurement stakeholders, and measure repeatability and HTTP/concurrency behaviour. Production rollout also requires authenticated reviewer roles, durable audit storage and real approval-system integration.
