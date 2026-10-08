# Reviewer walkthrough and requirement map

Start with the README's one-command demo. A request remains on the left, retrieved facts and tool traces appear in the centre, and the recommendation plus human handoff appear on the right.

| Assignment requirement / weight | Implementation | Evidence to inspect |
|---|---|---|
| Product + workflow — 15% | Request, evidence and action panels | README walkthrough; `tests/test_ui.py` |
| End-to-end product — 20% | One-command app + vendor API; starter adapter; review record | `run_local.py`, `src/solution.py`, pipeline tests |
| Agent + tool design — 20% | Single agent; analyst/reviewer; 7 typed tools | `docs/architecture.md`, `src/agents/`, `src/tools/` |
| Reliability + human controls — 15% | Code policy floor, verified facts, bounded loops, schema validation, explicit fallback | `tests/test_reliability.py`, `tests/test_guardrails.py`, `src/audit.py` |
| Evaluation + comparison — 20% | Same cases, raw/final scores, failures retained, traceable run metadata | `evals/README.md`; **real results pending** |
| Engineering + communication — 10% | Locked dependencies, isolated tests, CI, assumptions and limitations | `uv.lock`, `.github/workflows/ci.yml`, README |
| Decision memo, ≤500 words | Criteria documented; evidence-backed conclusion still pending | `docs/architecture_decision.md` |
| Public GitHub URL | Repository prepared locally; publication still pending | Owner will create the remote and push; local commits do not need GitHub login |

## Inspect the difficult cases

- **REQ-1006:** business text attempts to bypass policy. The missing cost/data fields still force clarification.
- **REQ-1007:** inspect both vendor sources and the reference date. The engine surfaces the disagreement instead of silently selecting the favourable source.
- **REQ-1009:** the vendor API deliberately returns 503. A safe recommendation must still be available, with the unavailable check explicit.
- **REQ-1005:** inspect the budget shortfall and all three specialist reviews.
- **REQ-1008:** a thin reason for another company-wide task tracker. This is the current case where model judgement over overlap is assessed most directly.

The evidence table is code-authored. Model assessment is labelled and can be inspected separately. Expanding the tool trace shows what each role actually retrieved, including cached calls. A review records the decision's run ID and request fingerprint; it does not send an email, route a ticket or approve a purchase.

## Before submission

1. Run the real provider on both architectures with the same cases and configuration; preserve failures.
2. Review the raw drafts and publish the complete comparison artifacts.
3. Replace the provisional memo with the evidence-backed decision; keep it under 500 words.
4. Update the README results and submission checklist.
5. Owner creates a public GitHub repository and pushes the local history, then verifies its URL from a signed-out browser.
