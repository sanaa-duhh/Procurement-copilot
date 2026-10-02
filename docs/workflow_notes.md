# Workflow notes

A short record of decisions made while building, in the order they came up.

**Starting point.** The scaffold ran, but several things needed attention before it could support the assignment:

- `evals/results_*.csv` was git-ignored, which contradicts "reproducible evaluation script and results". The full runner writes to `evals/results/`, which is committed; the starter runner's output path is left as is.
- `src/vendor_client.py` let a 503 surface as a raw `HTTPError` and a refused connection as a `ConnectionError`. Both now map to a typed `VendorRiskUnavailable`, and a 404 to `VendorRiskNotFound`, so the tool can return a structured "could not verify" instead of crashing the run.
- Employee E007 belongs to `Go To Market`, a department with no row in `department_budgets.csv`. The starter preflight does not notice because no starter request uses E007. The budget tool reports "not found" and the engine flags `budget_unverified`; the data is not edited.
- `vendors.csv` marks SignalWatch `Approved` with a 2025-07-01 review while the service says `expired`. This is the intended conflict case, and it decided how the engine treats disagreement: raw statuses are compared, and a disagreement is surfaced even when staleness explains it.
- `app.py` used `use_container_width`, deprecated in current Streamlit; replaced.
- `requirements.txt` carried no model SDK (by design); `anthropic` added, and the project also carries a `pyproject.toml` + `uv.lock` for a reproducible install.
- The default `python3` on this machine is 3.14; the project pins 3.12 via `.python-version`.

**Reference date.** All date arithmetic uses the policy's snapshot date. It is read from the policy file at runtime rather than hard-coded, with the documented constant as fallback.

**Where the model is allowed to matter.** Early on the engine decided everything and the model only wrote prose, which made the architecture comparison meaningless. The split that stuck: the engine computes constraints (approvals, flags, missing information, allowed next actions) and the model chooses within those constraints and explains. The guardrail enforces the constraints and logs every correction, which turned out to be the most useful comparison signal.

**Overlap.** The catalog tool classifies matches (same product, same vendor and category, same category, same vendor). The engine flags overlap for the first three. Whether an expansion is legitimate is a judgement the engine cannot make from the data, so both actions are allowed and the model picks. REQ-1008 (Marketing asking for a task tracker when TaskFlow is company-wide) is the case that tests this.

**Missing vendor record vs. outage.** A 404 from the vendor-risk service means "no assessment exists", which is the normal state for a new vendor and should not read as a service failure. Only connection errors, timeouts and 5xx responses raise `vendor_risk_unavailable`.

**Prompt injection.** Two layers: a regex scan over request text and vendor notes (deterministic, always runs) and an instruction in every prompt that data is never instructions. Either can raise the flag; the guardrail never removes it. The scan also removes instruction-like sentences before judging whether a business purpose was given, which is why REQ-1006 is also missing a usable justification.

**Mock model.** A scripted stand-in that calls every tool and copies the engine's output exists so tests, the UI and the harness run without a key. It is not a baseline and its results are not reported.
