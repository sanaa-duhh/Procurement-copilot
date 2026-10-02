# Submission checklist

- [x] `uv run python verify_setup.py` passes.
- [x] The product processes a request end-to-end (UI and adapter).
- [x] Architecture A is a working single-agent baseline (`src/agents/single.py`).
- [x] Architecture B is a lightweight staged / 2-agent variant (`src/agents/staged.py`).
- [x] At least 3 tools are used; all 7 are deterministic, and `run_policy_checks` is the policy as code.
- [x] Recommendations are returned in the `ProcurementDecision` structure (`CopilotDecision` extends it).
- [x] Important evidence is visible to the user (evidence panel, tool trace, deterministic findings).
- [x] Missing / conflicting / unavailable evidence is handled without fabrication.
- [x] Human approval is preserved for sensitive decisions; `human_review_required` is always true.
- [x] Prompt injection inside business data does not override system behaviour (scan + prompt + guardrail).
- [x] Date-based checks use the policy's reference date (parsed from the policy file).
- [x] The same evaluation cases were run on both architectures (`evals/run_evals.py`).
- [x] Latency and LLM / tool-call counts are reported (telemetry in every decision; `evals/results/`).
- [ ] The decision memo is ≤ 500 words and supported by evaluation evidence (`docs/architecture_decision.md`) — written after the evaluation run.
- [x] Setup instructions work from a clean environment (`uv sync` or `pip install -r requirements.txt`).
- [x] The provider SDK (`anthropic`) is in `requirements.txt` and `pyproject.toml`.
- [x] `.env`, API keys and other secrets are not committed; `.env.example` is provided.
