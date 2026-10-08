# Architecture decision — awaiting live evidence

**Status: not a final ship decision.** The real OpenAI comparison has not run yet. Passing tests and scripted model results establish a working pipeline, not which agent architecture performs better.

The provisional deployment candidate is the single agent. It has one responsibility boundary and avoids the analyst-to-reviewer handoff. Both candidates use the same deterministic policy engine, verified evidence panel, structured output validation and human approval boundary. That makes the additional reviewer useful only if it improves model judgement or reduces raw-draft mistakes enough to justify its extra call and tokens.

The experiment uses the same labelled cases, model and reasoning setting for both candidates. I will compare end-to-end success, pre-guardrail action/policy correctness, exact evidence support, corrections per request, latency and token use. Provider failures remain failures even when the deterministic fallback returns a safe answer. A rate-limited or partial experiment will be identified as incomplete.

I would ship the single agent if the comparison shows no material quality advantage for the staged variant. I would retain the staged variant if its reviewer consistently catches consequential mistakes—particularly an unsupported gap over an existing tool or an omitted review—that the single agent misses. Individual disagreements need inspection; aggregate accuracy alone can hide a serious error.

The current case set is small and largely policy dominated. Multiple repeats estimate consistency but do not increase the number of independent scenarios. The final memo will cite the saved run directory, give observed results, explain at least one representative failure or correction, and state the limits of the conclusion.

Neither candidate is ready for unattended procurement decisions. The local application records a human review; production use would additionally need authenticated reviewer roles, durable audit storage and integration with the organisation's approval workflow.
