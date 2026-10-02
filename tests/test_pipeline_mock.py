"""End-to-end pipeline on every request with the scripted mock model.

Proves the adapter, tool loop, policy engine and guardrail work together and that
both architectures meet the public minimum expectations without any model judgement.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

from run_public_evals import evaluate  # noqa: E402

from src.contracts import ProcurementDecision  # noqa: E402
from src.data_access import load_requests  # noqa: E402
from src.llm import MockClient  # noqa: E402
from src.solution import handle_request_payload  # noqa: E402

CASES = {c["request_id"]: c for c in json.loads((ROOT / "evals" / "public_cases.json").read_text())}


@pytest.mark.parametrize("architecture", ["single", "staged"])
@pytest.mark.parametrize("purchase_request", load_requests(), ids=lambda r: r["request_id"])
def test_every_request_produces_a_valid_decision(purchase_request, architecture):
    decision = handle_request_payload(purchase_request, architecture=architecture, llm=MockClient())
    ProcurementDecision.model_validate(decision.model_dump())
    assert decision.human_review_required is True
    assert decision.telemetry.llm_calls == (2 if architecture == "single" else 3)
    assert decision.telemetry.tool_calls >= 6
    if purchase_request["request_id"] in CASES:
        assert evaluate(decision, CASES[purchase_request["request_id"]]["expectations"]) == []
