# Reviewer walkthrough and requirement map

Start with the README's one-command demo. **Review a request** leads from intake to a full-width decision and next step. Evidence, human review and run details sit in tabs underneath. **Compare architectures** exposes the saved experiment, its individual cases and the decision memo without model calls.

| Assignment requirement / weight | Implementation | Evidence to inspect |
|---|---|---|
| Product + workflow — 15% | Request, evidence and action panels | README walkthrough; `tests/test_ui.py` |
| End-to-end product — 20% | One-command app + vendor API; starter adapter; review record | `run_local.py`, `src/solution.py`, pipeline tests |
| Agent + tool design — 20% | Single agent; analyst/reviewer; 7 typed tools | `docs/architecture.md`, `src/agents/`, `src/tools/` |
| Reliability + human controls — 15% | Code policy floor, verified facts, bounded loops, schema validation, explicit fallback | `tests/test_reliability.py`, `tests/test_guardrails.py`, `src/audit.py` |
| Evaluation + comparison — 20% | Same cases, raw/final scores, failures retained, traceable run metadata | [Complete OpenAI comparison](../evals/results/openai-comparison-20261008/summary.md), [case analysis](../evals/results/openai-comparison-20261008/case_analysis.md) |
| Engineering + communication — 10% | Locked dependencies, isolated tests, CI, assumptions and limitations | `uv.lock`, `.github/workflows/ci.yml`, README |
| Decision memo, ≤500 words | 392-word memo: single agent, supported by measured quality, latency and cost | `docs/architecture_decision.md` |
| Public GitHub URL | Repository prepared locally; publication still pending | Owner will create the remote and push; local commits do not need GitHub login |

## Inspect the difficult cases

- **REQ-1006:** business text attempts to bypass policy. The missing cost/data fields still force clarification.
- **REQ-1007:** inspect both vendor sources and the reference date. The engine surfaces the disagreement instead of silently selecting the favourable source.
- **REQ-1009:** the vendor API deliberately returns 503. A safe recommendation must still be available, with the unavailable check explicit.
- **REQ-1005:** inspect the budget shortfall and all three specialist reviews.
- **REQ-1008:** a thin reason for another company-wide task tracker. This is the current case where model judgement over overlap is assessed most directly.

The evidence panel is code-authored. The Evidence tab displays full findings and source references without clipping them. Model assessment is labelled and can be inspected separately. Expanding the tool trace shows what each role actually retrieved, including cached calls. A review records the decision's run ID and request fingerprint; it does not send an email, route a ticket or approve a purchase.

## Verification and submission

The local suite passes 116 tests. The complete live comparison records 18/18 single-agent and 17/18 staged final checks, with raw drafts and all failures preserved. Both pass the six original public cases. The memo recommends the single agent; the case analysis explains the staged sequencing disagreement and the difference between missing intake fields and reviewer questions.

The main experiment measures source `0de3dc7`. The only subsequent agent-code change is three money-formatting expressions in `src/rules.py`; calculations, prompts, actions and labels are unchanged. Separate threshold trials verify that precision fix. UI changes expose long findings and optional reviewer questions without changing the evaluated decision contract. The presentation lives in ui/, outside the evaluated agent-source fingerprint.

The owner creates a public GitHub repository and pushes the local history, verifies the URL from a signed-out browser, then submits it through the assignment form linked in `STUDENT_CHECKLIST.md`. GitHub CLI authentication is not required to maintain this local history.
