# Starter-pack audit

The application is built on the supplied **FDE Assessment 3 Starter Pack**. The working project lives at the repository root; `FDE_Assessment_3_Starter_Pack/` is an untouched local reference copy, not a second application to run.

On 8 October 2026, the supplied pack was compared byte-for-byte with the working tree and with initial commit `49875e0`. That commit already contained the matching starter datasets, mock API, public cases/runner and integrity tests. Later commits implemented the deliberately empty adapter and extended the optional UI.

## What is preserved

| Starter component | Check |
|---|---|
| All nine files under `data/`, including policy and vendor-risk fixture | Exact SHA-256 match |
| Both `mock_api/` Python files | Exact SHA-256 match |
| `evals/public_cases.json` and `evals/run_public_evals.py` | Exact SHA-256 match |
| `src/data_access.py` and `src/__init__.py` | Exact SHA-256 match |
| `tests/test_data_integrity.py`, `tests/test_mock_api.py` | Exact SHA-256 match |
| `docs/Assignment_3_Brief.pdf` | Exact SHA-256 match |
| `src/sample_output.json` and the three original templates | Preserved as reference examples |
| `ProcurementDecision` and its nested model schemas | Exact JSON-schema equality with the original |
| `handle_request(request_id, architecture)` | Same callable adapter; extended result validates as the original contract |

`docs/starter_manifest.json` records every source file's original SHA-256, its handling, and the original output schema. The local duplicate is ignored by Git; this manifest and the preserved root files travel with the submission.

## What is deliberately extended

- **`src/solution.py`:** replaces `NotImplementedError` with the single/staged pipelines.
- **`src/contracts.py`:** preserves the starter models and adds a compatible subclass for action labels, run IDs and telemetry.
- **`src/vendor_client.py`:** converts service failures into typed outcomes and validates returned assessments.
- **`app.py`:** replaces the optional UI scaffold with request, evidence and recommendation panels plus a local human-review record.
- **`run_local.py`, `verify_setup.py`:** add one-command demo mode, provider checks and startup diagnostics.
- **Dependencies, README, evaluation documentation and checklist:** updated for the implemented product.

The starter README expressly allows refactoring while retaining the adapter, permits replacing the UI, and does not require a particular provider/framework. Its templates are examples; the completed memo and workflow documentation belong in `docs/`.

The separately supplied final `FDE_Assessment_3.pdf` additionally specifies a **public GitHub URL submitted through the Google Form** and lists the required README topics. The reviewer guide and submission checklist follow those final submission instructions; the starter's shorter brief is preserved unchanged for provenance.

## Reproduce the checks

```bash
uv run pytest tests/test_starter_compatibility.py tests/test_data_integrity.py tests/test_mock_api.py -q
```

These checks use no model credentials or listening service. They verify provenance and compatibility, not model quality. The separate [complete OpenAI comparison](../evals/results/openai-comparison-20261008/summary.md) evaluates model behaviour; integration pilots are retained separately.

There is no scaffold-related reason to restart: the required source material and interfaces are present. The engineering work is to test and complete this implementation, then defend its architecture choice with real evaluation evidence.
