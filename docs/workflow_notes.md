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

The user-supplied pack was compared file-by-file against the root implementation and the initial commit. All nine data files, mock API files, public cases and runner, data-access helpers, brief and integrity tests match byte-for-byte. The original ProcurementDecision JSON schema also matches. Optional templates and sample output are retained at their original root paths; completed documents are in docs/. The hash manifest and compatibility tests make this check reproducible after cloning.
