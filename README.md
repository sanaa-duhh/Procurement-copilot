# Procurement Request Copilot

**Sanaa's FDE Assessment 3**

_An internal copilot that gathers evidence on a software purchase request, applies the procurement policy in code, and recommends the next action. Humans approve._

---

## The problem

Employees ask for new software. Before anything is bought, Procurement has to check the catalog for an existing tool, the department's budget, the vendor's status in the registry and in the external risk service, and the security, privacy and legal rules that apply to the data the tool will touch. The checks are routine but easy to skip under time pressure, and the sensitive decisions (approving spend, accepting a vendor, waiving a review) must stay with people.

This project is a small, reliable version of that copilot, built two ways and evaluated on the same test set to decide which one to ship.

## What it does

```
Request → gather evidence (7 tools) → deterministic policy engine → model recommends within policy → guardrail → human review
```

For every request the copilot returns the required output: **recommendation · evidence · approvals required · missing information · risk flags · next step**, plus a `next_action` label, a rationale and run telemetry.

The UI has three panels: the **request** (resolved requester, cost, data access, justification), the **evidence** (every finding with the tool it came from and a record reference, the tool-call trace, the deterministic findings), and the **recommendation** (next action, approvals checklist, flags, missing information, next step, and a form where a named reviewer records the human decision). The copilot never purchases, approves spend or edits a budget; the only write it performs is an audit line in `logs/human_decisions.jsonl` when a human records a decision.

## Quick start

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/). The project pins 3.12.

```bash
uv sync --extra dev                 # install (or: python -m venv .venv && pip install -r requirements.txt)
cp .env.example .env                # add ANTHROPIC_API_KEY; model defaults to claude-opus-5
uv run python verify_setup.py       # preflight: data, contract, mock API, policy engine, credentials
uv run python run_local.py          # vendor-risk API on :8001 + copilot UI on :8501
```

Open http://127.0.0.1:8501. `LLM_PROVIDER=mock` in `.env` runs the UI and tests on a scripted stand-in model with no key (useful to try the flow; never used for results).

```bash
uv run pytest -q                                   # 73 tests, no model, no network
uv run python evals/run_evals.py --repeats 3       # full comparison (API must be running)
uv run python evals/run_public_evals.py --architecture single   # starter harness
```

## Repository

```
Assignment_3/
├── app.py                      ← Streamlit product UI (request · evidence · recommendation + human action)
├── run_local.py                ← one-command start: mock vendor-risk API + UI
├── verify_setup.py             ← preflight checks
├── src/
│   ├── solution.py             ← handle_request(request_id, architecture) adapter (unchanged signature)
│   ├── rules.py                ← deterministic policy engine: thresholds, budget, staleness, conflicts, injection scan
│   ├── tools/                  ← 7 tools + ToolRegistry (per-run cache, telemetry, JSON schemas)
│   ├── agents/single.py        ← Architecture A: one agent, tool loop, structured output
│   ├── agents/staged.py        ← Architecture B: Procurement Analyst → Policy & Risk Reviewer
│   ├── guardrails.py           ← reconciles the model draft with the engine; logs every correction
│   ├── llm.py                  ← Anthropic SDK adapter + scripted mock
│   ├── contracts.py            ← ProcurementDecision (starter) + CopilotDecision (extended)
│   └── vendor_client.py        ← vendor-risk HTTP client with typed failures
├── mock_api/app.py             ← starter vendor-risk service (FastAPI)
├── data/                       ← starter data + policy (unmodified)
├── evals/
│   ├── cases.json              ← 18 cases: 6 public + 4 further starter requests + 8 synthetic
│   ├── run_evals.py            ← both architectures, same cases, raw-draft vs final scoring
│   ├── run_public_evals.py     ← starter harness
│   └── results/                ← committed results (runs.csv, decisions.jsonl, summary.md/json)
├── docs/
│   ├── architecture.md         ← diagrams, responsibility split, handoff format, assumptions
│   ├── architecture_decision.md← the ship decision memo (≤ 500 words)
│   └── workflow_notes.md       ← build log: starter issues found, design calls
└── tests/                      ← rules, tools, guardrails, pipeline (mock), UI, starter integrity
```

## Tools

All seven are plain Python functions with strict JSON schemas, bound to one request run through a registry that caches results per `(tool, args)` and records telemetry.

| Tool | Source | Deterministic |
|---|---|---|
| `get_requester_profile` | `employees.csv` | yes |
| `check_budget` | `department_budgets.csv` | yes: cost vs. available budget, shortfall |
| `search_software_catalog` | `software_catalog.csv` | yes: same product / same vendor + category / same category |
| `get_vendor_registry_record` | `vendors.csv` | yes |
| `get_vendor_risk_assessment` | mock vendor-risk API (external) | yes; outage returns `available: false`, never raises |
| `get_purchase_history` | `purchase_history.csv` | yes |
| `run_policy_checks` | policy engine over all of the above | yes: the policy as code |

The policy engine also runs in code after the agent finishes, whether or not the agent called it. Cached tool results mean this costs no extra tool calls.

## Design principle

| | Owns |
|---|---|
| **AI** | Reads the request in context, judges whether an overlap has a credible gap, chooses the next action from the policy-consistent set, writes the rationale and next step |
| **Code** | Required fields, approval tiers (`Decimal` boundaries), budget arithmetic, 365-day assessment validity from the policy reference date (2026-09-30), registry vs. service conflicts, security/privacy/legal triggers, untrusted-text scan, tool-failure handling |
| **Human** | Every approval. `human_review_required` is always true; the UI records a reviewer's decision and nothing else |

The guardrail (`src/guardrails.py`) is what makes this hold: approvals and flags are the union of model and engine, missing information is code-owned, the next action must be in the engine's allowed set, every evidence item must cite a tool that actually ran, and each correction is logged. Full split in [`docs/architecture.md`](docs/architecture.md).

## The two architectures

**A. Single agent.** One model, all seven tools, a tool-use loop (≤ 8 iterations), one structured decision. 2 to 4 model calls.

**B. Staged.** A *Procurement Analyst* with the tools builds an evidence pack (facts with sources, uncertainties, overlap assessment, untrusted-text observations) and is told not to decide. A *Policy & Risk Reviewer* with no tools receives the request, the pack and the raw tool outputs and writes the decision. Analyst calls + 1.

Same tools, same engine, same guardrail, same output contract, same ground rules in both prompts. Diagrams in [`docs/architecture.md`](docs/architecture.md).

## Reliability and human controls

- **Untrusted data.** Request fields and vendor notes are wrapped as data in every prompt. A deterministic scan over the same text raises `prompt_injection_detected`; instruction-like sentences are removed before judging whether a business purpose was given. The guardrail never lowers the flag.
- **Tool failure.** A refused connection, timeout or 5xx from the vendor-risk service becomes `vendor_risk_unavailable`, adds Security review and routes to manual review. A 404 is "no assessment on record", which is the normal state for a new vendor.
- **Conflicting evidence.** When the registry and the service disagree on status or dates, the conflict is surfaced with both values and routed to Security; neither source is picked.
- **Model failure.** If the model is unreachable, refuses or returns non-JSON, the decision is built from the deterministic findings only, the error is in the trace, and the UI shows it.
- **No fabrication.** Missing fields are listed, not guessed; evidence citing a tool that did not run is dropped.
- **Human authority.** No code path purchases, approves, modifies budgets or accepts terms.

## Evaluation

Both architectures run the same 18 cases (`evals/cases.json`) with the same checks: correct next action, exact approval set, required and forbidden risk flags, missing-information handling, human review, the starter's own minimum checks, evidence grounding, latency, LLM/tool calls and tokens. The model's **raw draft** is scored with the same checks *before* the guardrail, and the number of guardrail corrections per case is recorded. That is the comparison signal that matters: with the guardrail in place both architectures should be policy-correct, so the question is which one produces the right answer on its own, and at what cost.

How to run it, what each metric means and how the cases were built: [`evals/README.md`](evals/README.md).

### Results

<!-- RESULTS:BEGIN -->
_Pending: the evaluation runs against the Anthropic API and is executed once credentials are in `.env`. The table below is filled from `evals/results/summary.md`._
<!-- RESULTS:END -->

## Ship decision

See [`docs/architecture_decision.md`](docs/architecture_decision.md) (≤ 500 words).

## Assumptions

- The policy reference date is "today" for all date checks; it is parsed from `data/procurement_policy.md`.
- Annual cost is already annualised. Budget is compared to the requesting department's `available_usd` only.
- `internal_*` data classes are not sensitive; `confidential_documents`, `source_code`, `production_*`, `*_pii` and credentials are. SSO is a standard integration; production, cloud-account, repository, database and credential integrations trigger Security.
- A vendor is "new" for policy §7 if it is not `Approved` in the registry or absent from it.
- Same vendor and category in the catalog is an expansion; whether it is a legitimate add-on or a duplicate is a judgement for the model and the human.

The full list is in [`docs/architecture.md`](docs/architecture.md#assumptions).

## Starter issues found and fixed

- Evaluation CSVs were git-ignored, contrary to the deliverable; the full runner writes to a committed `evals/results/`.
- `vendor_client.py` raised raw `requests` exceptions on a 503 or refused connection; failures are now typed so the tool degrades instead of crashing.
- Employee `E007` belongs to `Go To Market`, which has no budget line; the engine reports `budget_unverified` rather than assuming a budget (the data is left as is).
- `vendors.csv` shows SignalWatch as `Approved` on a 2025-07-01 review while the service says `expired`; handled as an explicit conflict plus expiry, not silently overridden.
- `app.py` used a deprecated Streamlit argument; `python3` on the dev machine is 3.14 and the project now pins 3.12.

Details in [`docs/workflow_notes.md`](docs/workflow_notes.md).

## Known limitations

- The overlap judgement ("does the justification show a credible gap?") is the one place the model's opinion changes the next action, and it is scored on a single case (REQ-1008); more labelled cases would tighten that estimate.
- The injection scan is pattern-based; it catches the assessment's phrasings and obvious variants, not paraphrase. The prompt-level instruction is the second layer.
- Seat utilisation is not in the data, so "unused existing capacity" cannot be checked; the copilot can only route the question to the tool owner.
- Latency figures are for a single machine against a local mock API; model latency dominates and varies with the provider's load.
- One provider (Anthropic) is wired. The adapter in `src/llm.py` is small enough that adding another is a single class.
