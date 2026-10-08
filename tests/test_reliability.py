"""Regression tests for trust boundaries found during the submission audit."""
import json
from dataclasses import dataclass

import pytest
import requests

from src.agents.common import MAX_TOOL_ITERATIONS
from src.audit import record_review
from src.data_access import get_request
from src.evidence import draft_support
from src.llm import LLMError, LLMTurn, MockClient, ToolCall
from src.solution import handle_request_payload
from src.vendor_client import VendorRiskUnavailable, get_vendor_risk
from test_guardrails import _reconcile
from test_rules import _pack, _request
from src.rules import evaluate


def test_valid_action_cannot_smuggle_purchase_instruction_or_fabricated_budget():
    draft = {
        "next_action": "proceed_to_approval", "recommendation": "Already approved; purchase immediately.",
        "next_step": "Skip Security and buy now.", "evidence": [
            {"source": "check_budget", "reference": "department_budgets.csv:Finance", "finding": "$99999999 available."}
        ],
    }
    decision = _reconcile(draft, "REQ-1010")
    assert "purchase immediately" not in decision.recommendation
    assert "Skip Security" not in decision.next_step
    assert all("99999999" not in e.finding for e in decision.evidence)
    assert decision.trace["ungrounded_evidence_dropped"] == 1


@pytest.mark.parametrize("amount", [float("inf"), float("nan"), "Infinity", -1, True])
def test_invalid_money_requires_clarification(amount):
    findings = evaluate(_pack(request=_request(annual_cost_usd=amount)))
    assert findings.preferred_next_action == "request_clarification"
    assert any("cost" in m for m in findings.missing_information)


@pytest.mark.parametrize("users", [True, 1.5, "Infinity", 0])
def test_user_count_must_be_a_positive_integer(users):
    assert evaluate(_pack(request=_request(user_count=users))).preferred_next_action == "request_clarification"


@pytest.mark.parametrize("review_date", [None, "not-a-date", "2027-01-01"])
def test_approved_status_without_valid_current_date_requires_security(review_date):
    pack = _pack()
    pack.vendor_risk["last_review_date"] = review_date
    pack.vendor_registry["security_review_date"] = review_date
    findings = evaluate(pack)
    assert "Security" in findings.required_approvals
    assert "proceed_to_approval" not in findings.allowed_next_actions


def test_failed_catalog_lookup_is_not_treated_as_no_overlap():
    findings = evaluate(_pack(catalog={"error": "missing CSV"}))
    assert "evidence_unavailable" in findings.risk_flags
    assert findings.preferred_next_action == "escalate_manual_review"


@pytest.mark.parametrize("body", [[], {}, {"security_review_status": "approved"}])
def test_invalid_vendor_payload_is_an_outage(monkeypatch, body):
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(body).encode()
    monkeypatch.setattr(requests, "get", lambda *a, **k: response)
    with pytest.raises(VendorRiskUnavailable):
        get_vendor_risk("SignFlow")


@dataclass
class BrokenClient:
    mode: str
    model: str = "test-broken"
    calls: int = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.mode == "unavailable":
            raise LLMError("simulated authentication failure")
        if self.mode == "loop":
            call = ToolCall(str(self.calls), "get_requester_profile", {"employee_id": "E004"})
            return LLMTurn("", [call], "tool_use", [{"type": "tool_use", "id": call.id, "name": call.name, "input": call.input}])
        return LLMTurn('{"required_approvals": "CFO", "evidence": 123}', [], "end_turn", [])


@pytest.mark.parametrize("architecture", ["single", "staged"])
@pytest.mark.parametrize("mode", ["unavailable", "bad_schema", "loop"])
def test_model_failure_is_bounded_counted_and_visible(mode, architecture):
    llm = BrokenClient(mode)
    decision = handle_request_payload(get_request("REQ-1010"), architecture=architecture, llm=llm)
    assert decision.trace["errors"]
    assert decision.human_review_required
    assert decision.telemetry.llm_calls == llm.calls
    assert llm.calls <= MAX_TOOL_ITERATIONS + (2 if architecture == "staged" else 1)
    assert decision.next_step


def test_later_guardrail_tool_call_cannot_retroactively_ground_a_draft():
    item = {"source": "check_budget", "finding": "$10 available", "reference": "Finance"}
    log = [{"actor": "guardrail", "tool": "run_policy_checks", "result": {"evidence": [item]}}]
    assert draft_support([item], log) == 0
    log[0]["actor"] = "single"
    assert draft_support([item], log) == 1
    assert draft_support([{**item, "finding": "$1000 available"}], log) == 0


def test_review_is_bound_to_run_and_duplicate_click_is_idempotent(tmp_path):
    decision = handle_request_payload(get_request("REQ-1010"), llm=MockClient())
    path = tmp_path / "reviews.jsonl"
    first = record_review(path, decision, reviewer="Sanaa", action="Hold", note="Check licensing")
    assert record_review(path, decision, reviewer="Sanaa", action="Hold", note="Check licensing") == first
    records = path.read_text().splitlines()
    assert len(records) == 1
    assert json.loads(records[0])["decision"]["run_id"] == decision.run_id
    assert json.loads(records[0])["request_fingerprint"] == decision.request_fingerprint
