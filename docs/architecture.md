# Architecture and workflow

## Workflow

```mermaid
flowchart LR
    R[Employee request] --> U[Understand need]
    U --> G[Gather evidence]
    subgraph tools [Tools]
        T1[get_requester_profile]
        T2[check_budget]
        T3[search_software_catalog]
        T4[get_vendor_registry_record]
        T5[get_vendor_risk_assessment]
        T6[get_purchase_history]
        T7[run_policy_checks]
    end
    G --> tools
    tools --> D[Deterministic policy engine]
    D --> M[Model draft: recommendation, rationale, next action]
    M --> GR[Guardrail: reconcile draft with engine]
    GR --> H[Human review and approval]
```

The policy engine runs twice: once if the agent calls `run_policy_checks` (so the model can read the binding minimums) and always once more in code after the agent finishes. Tool results are cached per run. The final pass reuses matching `(tool, arguments)` results; calls omitted by the model are still executed and counted.

## Architecture A: single agent

```mermaid
flowchart LR
    UI[UI / adapter] --> A[Procurement Agent]
    A --> T[(7 tools)]
    T --> A
    A --> J[Draft decision JSON]
    J --> GR[Guardrail]
    GR --> OUT[ProcurementDecision]
```

One model with all seven tools, at most eight tool iterations and a final turn with tools disabled. OpenAI Responses carries strict function schemas and a strict final-output schema; the final output is also validated locally. Call counts are measured, not assumed.

## Architecture B: staged, two roles

```mermaid
flowchart LR
    UI[UI / adapter] --> AN[Procurement Analyst]
    AN --> T[(7 tools)]
    T --> AN
    AN --> EP[Evidence pack JSON + raw tool outputs]
    EP --> RV[Policy and Risk Reviewer]
    RV --> J[Draft decision JSON]
    J --> GR[Guardrail]
    GR --> OUT[ProcurementDecision]
```

The analyst is the only role with tools and is told not to decide. It hands over a structured evidence pack (facts with sources, uncertainties, an overlap assessment, untrusted-text observations). The reviewer has no tools; it receives the request, the pack and the raw tool outputs, and writes the decision. The reviewer adds one logical model call to the analyst stage. OpenAI rate-limit retries are recorded separately.

Both architectures share the same tools, policy engine, guardrail, output contract and prompts for the ground rules, so the comparison isolates the orchestration choice.

## Division of responsibility

| Concern | Owner | Where |
|---|---|---|
| Required fields (policy §1) | Code | `src/rules.py` `check_required_fields` |
| Budget arithmetic and shortfall (§2) | Code | `src/tools/budget.py`, `rules.evaluate` |
| Catalog overlap detection (§3) | Code finds matches; model judges whether the gap is credible | `src/tools/catalog.py`, prompts |
| Approval thresholds (§4) | Code, `Decimal` boundaries | `rules.approval_tier` |
| Assessment freshness, 365 days from the policy reference date (§5) | Code | `rules.evaluate` |
| Registry vs. vendor-risk service conflict (§5) | Code surfaces; human resolves | `rules.evaluate` |
| Security / privacy / legal triggers (§5 to §7) | Code | `rules.evaluate` |
| Untrusted text / prompt injection (§9) | Code scan plus model instruction; either can raise the flag, neither can lower it | `rules.scan_untrusted_text`, `common.GROUND_RULES` |
| Tool failure handling (§10) | Code: outage is `vendor_risk_unavailable`; a missing record is "assessment not completed" | `src/tools/vendor.py`, `rules.evaluate` |
| Action selection, rationale and request summary | Model, within allowed actions; interpretation requires human verification | `src/agents/*` |
| Recommendation wording, next step and factual panel | Code, from the validated action and verified findings | `src/guardrails.py` |
| Final authority (§11) | Human; `human_review_required` is always true and the UI only records a human decision | `src/guardrails.py`, `app.py` |

## Guardrail rules

Applied to every model draft, in both architectures (`src/guardrails.py`):

1. `required_approvals` = canonicalised model approvals ∪ engine approvals. Unrecognised names are dropped and logged.
2. `risk_flags` = canonicalised model flags ∪ engine flags, minus flags the deterministic evidence contradicts (for example `budget_insufficient` when the budget check passed).
3. `missing_information` is code-owned; policy §1 is an explicit list.
4. `next_action` must be in the engine's allowed set, otherwise it is replaced by the preferred action. When Security, Privacy or Legal review is required, the allowed set excludes "check the existing tool first" (the sequencing rule in `config/policy.toml`); the existing-tool question is added to the next step to run in parallel. Recommendation and next-step wording are always generated in code. If the action was corrected, the contradictory model rationale is withheld.
5. The factual panel contains only the engine's verified facts. Model evidence without an exact `(source, finding, reference)` match is dropped and logged. Exact copying is a conservative support check, not a semantic entailment model.
6. `human_review_required` is always true.

Field corrections are recorded in `telemetry.guardrail_corrections`; routine template rendering is not counted as a model error. The raw draft and retrieved evidence remain in the trace for evaluation. Human review is bound to a unique run ID and request fingerprint; changing request content, architecture or provider/model hides stale recommendations.

## Handoff format

Staged variant, analyst to reviewer:

```json
{
  "request_summary": "…",
  "facts": [{"source": "check_budget", "finding": "…", "reference": "department_budgets.csv:Sales"}],
  "uncertainties": ["…"],
  "overlap_assessment": "…",
  "untrusted_text_observations": "…"
}
```

plus the raw tool outputs as a JSON list. Both architectures emit the same final `CopilotDecision` (a `ProcurementDecision` with `next_action`, `rationale`, `request_summary` and extended telemetry added).

## Stop and escalation conditions

| Condition | Result |
|---|---|
| Any required field missing or unusable | `request_clarification`; approvals stay partial; nothing is invented |
| Vendor-risk service unreachable, 5xx or timeout | `vendor_risk_unavailable`, Security review, `escalate_manual_review` |
| Registry and service disagree on status or dates | `conflicting_vendor_evidence`, Security review, `escalate_manual_review` |
| Cost above available budget or no budget line | Finance added, `budget_exception_required` |
| Model unavailable, refuses, or returns an invalid output schema | Decision built from the deterministic findings only; the error is in the trace and the UI shows it |
| Agent exceeds 8 tool iterations | Tools are disabled for the final turn; invalid output produces deterministic fallback |

## Assumptions

- The policy reference date (2026-09-30) is the "today" for every date check; it is parsed from `data/procurement_policy.md`.
- Annual cost is already annualised; no proration or multi-year handling.
- "Within budget" compares against `available_usd` for the requester's department only; cross-department funding is a Finance decision.
- Data sensitivity comes from the classification register in `config/policy.toml`, matched by whole words. Internal and public data are not sensitive; confidential documents, source code, production systems, credentials and personal data (customer, employee, HR, payroll, health) are. An unregistered label is routed to Security and Privacy for classification rather than treated as safe.
- SSO is a standard integration, not a security trigger; production, cloud-account, repository, source-control, database, warehouse and credential integrations are. The list is in the same config.
- A vendor-level `processes_personal_data=true` does not by itself trigger Privacy review; the request's data-access level does, as does cross-region storage of sensitive data.
- "New vendor" (policy §7) means not `Approved` in the internal registry, or absent from it.
- Overlap with the same vendor in the same category is an expansion; whether it is a legitimate add-on or a duplicate is a judgement left to the model (and ultimately the human), with the conservative default being to check existing capacity when the existing agreement already covers the requesting department.
- `Go To Market` (employee E007's department) has no budget line in the starter data; it is handled as "budget unverifiable" rather than patched in the data.

## Policy as configuration

`config/policy.toml` holds every value the engine enforces: approval tiers, the assessment validity window, the legal new-vendor threshold, the review-order rule, the data-classification register and the security-sensitive integrations. `src/policy_config.py` loads it and compares it with the written policy; `verify_setup.py` and `tests/test_policy_config.py` fail on any difference in tiers, validity window, legal threshold or version. Each decision records `policy_version`.

Moving these values out of code was verified by snapshotting the engine on all 28 cases and requests before and after: approvals, flags, missing information, evidence and preferred actions were identical. The only differences were the allowed-action sets that the new review-order rule was meant to tighten.

## Not built, on purpose

- No automatic approval, purchase order creation or budget mutation anywhere in the code paths.
- No retrieval over policy text; the policy is short and is passed whole to the model, and every rule that matters is also in code.
- No third agent, planner or critic loop. The live comparison supports shipping the single agent; the second role remains available for experiments.
- No fuzzy matching of employees or vendors beyond case-insensitive equality; an unknown ID is reported as missing information, not guessed.

## Provider and experiment boundaries

OpenAI is the only live provider. `src/openai_client.py` calls the Responses API using the shell's `OPENAI_API_KEY`, strict function schemas and `text.format` JSON schema. Reasoning items are carried in memory between tool calls via encrypted content, with `store=false`. They are not written into evaluation traces. Provider response IDs and model names are retained for provenance.

OpenAI 429 responses with a numeric Retry-After of up to 60 seconds get at most two retries. Other errors fail visibly. Retry count and wait duration are recorded, and total latency includes throttling. This bounds a failure without silently switching providers or dropping cases.

Tests and default evaluations exercise the actual vendor API handlers in-process; the application uses HTTP. Experiments preserve both raw drafts and final decisions, distinguish model failure from safe fallback, and record a source fingerprint. Resuming an interrupted run requires identical source and experiment settings and never removes prior failed trials.


## Product interface

`app.py` is the page entry point. `ui/review.py` owns request input and human review; `ui/comparison.py` offers current-request comparison and the fixed benchmark. Shared presentation and handoff formatting live in `ui/components.py`, with styles in `ui/styles.css`. The evaluated code under `src/` is unchanged by these application features.

`ui/themes/dark.css` and `ui/themes/light.css` supply separate colour tokens for the shared layout. The native theme switch is per session, with a `theme` query parameter to preserve the choice on refresh. Appearance is excluded from the decision context: switching it keeps the exact run and never invokes the agent. The textured background and reflective shapes are CSS, with decorative content hidden from screen readers and movement disabled for reduced-motion preferences. Browser checks cover the installed Streamlit controls, popup options, text contrast in request selectors and mobile overflow in both themes.

Only the explicit analysis or comparison run buttons call `handle_request_payload`, through `ui/runs.py`. Input changes invalidate stale displayed results. Tab navigation, downloads, saving a human review and inspecting saved analyses or the benchmark make no model calls. Result tabs retain their selection across reruns, so validation and saved-review feedback stay visible. Readable handoffs include run identity, model/mode, policy evidence and required approvals.

The project config sets Streamlit's toolbar to minimal and the interface removes its developer/deployment chrome. See the [official configuration reference](https://docs.streamlit.io/develop/api-reference/configuration/config.toml). The application has no cache-clear or deployment action. Its tool cache exists only within an individual analysis.

## Persistence and exploratory comparison

```mermaid
flowchart LR
    I[Typed or sample request] --> E[Explicit analysis]
    E --> P[Shared agent and policy pipeline]
    P --> R[Immutable run snapshot]
    R --> S[(Local SQLite history)]
    S --> V[View original result and evidence]
    S --> C[Compare matching single and staged runs]
    C --> M[Run only a missing design on request]
    M --> P
    B[Fixed labelled benchmark] --> D[Evidence for the ship decision]
```

`ui/history.py` stores each request, result, full diagnostic trace, run ID, creation time and analysis configuration in `logs/analyses.sqlite3`. SQLite transactions serialize local writes. A repeated identical save is idempotent; changing an existing run is rejected. Model fallbacks are retained with their errors. A failed write leaves the result in the current session with a visible warning and download options. Runtime history is ignored by Git; benchmark artifacts remain committed and unchanged.

A matching input requires the full request hash, architecture, provider, model, effort, analysis-code/data/lockfile hash and vendor endpoint. UI themes do not invalidate analysis. This detects local changes, not changes inside an external service. The UI therefore shows snapshot timestamps and never calls a saved result fresh evidence. Historical benchmark results and configuration-mismatched runs are inspectable, but a new human review requires a run under the current configuration.

The request-comparison view reuses compatible runs and invokes only missing designs when explicitly requested. A successful first result survives failure of the second; a retry targets the missing design. A request pair displays action/approval/risk differences, evidence, corrections and measured resource use. It has no ground-truth labels and never changes the fixed benchmark's accuracy, cost table or memo.

`ui/intake.py` resolves typed names using normalised exact equality, not fuzzy similarity. Duplicate names require an employee ID; an ID must match the supplied name. Unknown names and supplied departments remain in the request, while the unchanged policy engine requires a real directory record for verified budget ownership. No directory mutation or identity-authentication claim is made.

This storage is appropriate for a local assessment demo. A production rollout needs authenticated employees and reviewer roles, per-user access to history, retention/deletion policy, protected backups, current organisational data and actual ticket/approval-system integration.
