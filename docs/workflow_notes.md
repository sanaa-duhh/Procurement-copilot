# Workflow notes

A short record of decisions made while building, in the order they came up.

**Starting point.** The scaffold ran, but several things needed attention before it could support the assignment:

- `evals/results_*.csv` was git-ignored, which contradicts "reproducible evaluation script and results". The full runner writes to `evals/results/`, which is committed; the starter runner's output path is left as is.
- `src/vendor_client.py` let a 503 surface as a raw `HTTPError` and a refused connection as a `ConnectionError`. Both now map to a typed `VendorRiskUnavailable`, and a 404 to `VendorRiskNotFound`, so the tool can return a structured "could not verify" instead of crashing the run.
- Employee E007 belongs to `Go To Market`, a department with no row in `department_budgets.csv`. The starter preflight does not notice because no starter request uses E007. The budget tool reports "not found" and the engine flags `budget_unverified`; the data is not edited.
- `vendors.csv` marks SignalWatch `Approved` with a 2025-07-01 review while the service says `expired`. This is the intended conflict case, and it decided how the engine treats disagreement: raw statuses are compared, and a disagreement is surfaced even when staleness explains it.
- `app.py` used `use_container_width`, deprecated in current Streamlit; replaced.
- `requirements.txt` carried no model SDK (by design); `openai` is the current provider SDK, and the project also carries a `pyproject.toml` + `uv.lock` for a reproducible install.
- The default `python3` on this machine is 3.14; the project pins 3.12 via `.python-version`.

**Reference date.** All date arithmetic uses the policy's snapshot date. It is read from the policy file at runtime rather than hard-coded, with the documented constant as fallback.

**Where the model is allowed to matter.** Early on the engine decided everything and the model only wrote prose, which made the architecture comparison meaningless. The split that stuck: the engine computes constraints (approvals, flags, missing information, allowed next actions) and the model chooses within those constraints and explains. The guardrail enforces the constraints and logs every correction, which turned out to be the most useful comparison signal.

**Overlap.** The catalog tool classifies matches (same product, same vendor and category, same category, same vendor). The engine flags overlap for the first three. Whether an expansion is legitimate is a judgement the engine cannot make from the data, so both actions are allowed and the model picks. REQ-1008 (Marketing asking for a task tracker when TaskFlow is company-wide) is the case that tests this.

**Missing vendor record vs. outage.** A 404 from the vendor-risk service means "no assessment exists", which is the normal state for a new vendor and should not read as a service failure. Only connection errors, timeouts and 5xx responses raise `vendor_risk_unavailable`.

**Prompt injection.** Two layers: a regex scan over request text and vendor notes (deterministic, always runs) and an instruction in every prompt that data is never instructions. Either can raise the flag; the guardrail never removes it. The scan also removes instruction-like sentences before judging whether a business purpose was given, which is why REQ-1006 is also missing a usable justification.

**Mock model.** A scripted stand-in that calls every tool and copies the engine's output exists so tests, the UI and the harness run without a key. It is not a baseline and its results are not reported.

## Submission audit — 8 October 2026

A clean test run exposed four failures: guardrail and pipeline tests depended on a listening vendor-risk service despite being described as offline. Tests now exercise the real FastAPI routes through an in-process transport.

The review found two trust-boundary bugs. A model could cite a real tool but invent its result; the factual panel now contains only code-authored verified facts. A valid action label could retain contradictory purchase instructions; operational wording now comes from the validated action. Exact evidence support is scored separately from model interpretation, with no semantic-grounding claim.

Additional regression coverage checks invalid monetary values, fractional user counts, missing/future vendor review dates, malformed API records, failed catalog lookups, invalid model schemas and endless tool calls. UI decisions are invalidated on request/configuration changes; review events carry the actual run ID and request fingerprint.

The evaluator now preserves each trial immediately, retains errors in denominators, distinguishes safe fallback from successful model analysis, randomises paired order and records source/configuration fingerprints. Unknown token prices remain unknown. Resumption appends only unattempted trials and retains all previous failures.

OpenAI is the final provider choice. Both architectures use the same Responses API model and reasoning setting. SDK protocol tests verify tool results, strict output validation and encrypted reasoning-state handoff. Existing shell credentials are used without copying them into project files.

## Starter-pack provenance

The starter data, mock API, public cases and runner, data-access helpers and integrity tests stay unchanged at their original paths. The original `ProcurementDecision` contract is untouched; the extended decision is a subclass and validates against it.

## Findings from the live comparison

The 36-trial OpenAI comparison favoured the single agent: 18/18 final and raw checks, versus staged's 17/18 final and 14/18 raw checks. The staged final miss retains required reviews but disagrees with the label about which step should happen first. Labels and completed trials remain unchanged; this qualification is part of the architecture decision.

Reviewing SYN-13 exposed rounded money in the policy engine's narrative evidence. Exact arithmetic and approval tiers were already correct, but a one-cent shortfall could be displayed as “by $0.” Three regression checks reproduced the problem before the fix. Three formatting expressions now retain two decimal places. A separate live threshold experiment checks the updated source; the main comparison still measures its original fingerprint.

The UI audit also found clipped evidence and hidden references. Findings now expand to show full text and provenance; conflicts open by default. Model-proposed follow-up questions remain separate from policy-required intake fields and are visible to the human reviewer. The README screenshot is a labelled scripted demo, not live model evidence.

## Product interface review

The original three-column screen gave long decisions and evidence too little room. The final interface separates request review from architecture comparison. Intake and the decision use the full workspace width; evidence, human review and diagnostics have dedicated tabs. Findings now show their complete text and references in cards. The comparison view reads the saved OpenAI experiment, including the original disagreement and limitations, without invoking either agent.

Streamlit's developer menu and deployment prompt are hidden. Analysis starts only on an explicit button press. Changing request content or architecture invalidates the displayed recommendation; review saves, downloads and comparison browsing preserve it without another model call. Review confirmation stays visible in its tab, and an unsuccessful rerun cannot leave an old recommendation on screen.

The offline interaction tests cover these state transitions and actual review-log writes. The browser audit exercises both architectures, sample and new requests, four downloads, review validation, untrusted HTML escaping and mobile layouts. Screenshot generation is restricted to the scripted demo. No paid model calls were used to validate this interface change; the saved architecture experiment and agent implementation are unchanged.

The visual direction was refined from supplied references: deep teal with layered lighting and grain by default, and a soft mint/blue gradient in light mode. Reflective curved forms use CSS gradients and masks, avoiding downloaded imagery and external assets. The theme switch retains the current analysis and remembers the preference in the URL. Testing caught native controls retaining dark backgrounds in light mode and decorative artwork overflowing on mobile; both were corrected against the actual installed Streamlit DOM. The suite now includes a theme-state regression check.

## Analysis lifecycle and requirement closure

App analyses previously existed only in Streamlit session state; only evaluation artifacts and explicit human reviews were durable. The app now saves immutable request/result/trace snapshots in local SQLite. A new session can retrieve the exact prior run, and rerunning creates a new record. The full input and configuration identity prevent unrelated or outdated results from being treated as compatible. Known historical sample results are exposed from the committed benchmark without rewriting it. They cannot record a fresh human review under a different configuration.

The requester dropdown was replaced with typed name, optional employee ID and a supplied department. An exact directory match provides verified organisation data. Unknown names are accepted and retained, but they do not create an employee or a budget entitlement. The existing policy engine produces clarification when identity cannot be resolved.

The comparison workspace now has two purposes: an exploratory pair for the selected request, and the fixed labelled benchmark that supports the ship decision. The exploratory view reuses compatible local analyses and runs only a missing architecture on explicit request. Completed results survive a partial failure, and a retry does not bill for the successful half again. Unlabelled agreement never becomes an accuracy claim or changes the published experiment.

New tests cover restart persistence, immutable and concurrent saves, configuration changes, benchmark provenance, name ambiguity, partial comparison failure and disk-write failure. All verification for these changes uses the scripted model; the paid experiment remains unchanged.
