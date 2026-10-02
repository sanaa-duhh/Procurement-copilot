"""The guardrail may add to the model's draft but never lower the deterministic findings."""
from __future__ import annotations

from src import rules
from src.data_access import get_request
from src.guardrails import reconcile
from src.telemetry import RunTelemetryCounter
from src.tools import ToolRegistry
from src.tools.policy import gather_evidence


def _setup(request_id: str):
    request = get_request(request_id)
    telemetry = RunTelemetryCounter()
    registry = ToolRegistry(request=request, telemetry=telemetry)
    findings = rules.evaluate(gather_evidence(registry, actor="guardrail"))
    return request, telemetry, registry, findings


def _reconcile(draft, request_id="REQ-1005"):
    request, telemetry, registry, findings = _setup(request_id)
    return reconcile(draft, findings, registry, request, telemetry, architecture="single", model="test", trace={})


def test_model_cannot_remove_policy_approvals_or_flags():
    draft = {"required_approvals": ["Manager"], "risk_flags": [], "next_action": "proceed_to_approval",
             "recommendation": "Approve.", "next_step": "Buy it.", "evidence": [], "missing_information": []}
    decision = _reconcile(draft)
    assert {"Department Head", "Finance", "Procurement", "Security", "Privacy", "Legal"} <= set(decision.required_approvals)
    assert "budget_insufficient" in decision.risk_flags
    assert decision.next_action == "budget_exception_required"
    assert decision.next_step != "Buy it."
    assert any("next_action" in c for c in decision.telemetry.guardrail_corrections)


def test_model_approval_synonyms_are_canonicalised():
    draft = {"required_approvals": ["dept head", "Security team", "CFO sign-off", "The Wizard"], "risk_flags": [], "next_action": "route_for_reviews",
             "recommendation": "", "next_step": "", "evidence": [], "missing_information": []}
    decision = _reconcile(draft, "REQ-1003")
    assert "CFO" in decision.required_approvals
    assert "The Wizard" not in decision.required_approvals
    assert any("unrecognised approval" in c for c in decision.telemetry.guardrail_corrections)


def test_contradicted_model_flags_are_removed():
    draft = {"required_approvals": [], "risk_flags": ["budget_insufficient", "vendor_risk_unavailable"], "next_action": "route_for_reviews",
             "recommendation": "", "next_step": "", "evidence": [], "missing_information": []}
    decision = _reconcile(draft, "REQ-1003")  # within budget, service available
    assert "budget_insufficient" not in decision.risk_flags
    assert "vendor_risk_unavailable" not in decision.risk_flags


def test_missing_information_is_code_owned():
    draft = {"required_approvals": [], "risk_flags": [], "next_action": "route_for_reviews", "recommendation": "", "next_step": "",
             "evidence": [], "missing_information": ["favourite colour"]}
    decision = _reconcile(draft, "REQ-1001")
    assert decision.missing_information == []
    decision = _reconcile({**draft, "next_action": "request_clarification"}, "REQ-1006")
    assert any("cost" in m for m in decision.missing_information)


def test_ungrounded_evidence_is_dropped_and_engine_evidence_kept():
    draft = {"required_approvals": [], "risk_flags": [], "next_action": "route_for_reviews", "recommendation": "", "next_step": "",
             "evidence": [{"source": "crystal_ball", "finding": "Vendor is fine.", "reference": ""},
                          {"source": "check_budget", "finding": "Within budget.", "reference": "department_budgets.csv:Engineering"}],
             "missing_information": []}
    decision = _reconcile(draft, "REQ-1003")
    sources = [e.source for e in decision.evidence]
    assert "crystal_ball" not in sources and "check_budget" in sources
    assert any("policy_checks" == s for s in sources)


def test_human_review_is_always_required():
    decision = _reconcile({"next_action": "proceed_to_approval", "human_review_required": False}, "REQ-1010")
    assert decision.human_review_required is True


def test_no_draft_still_yields_a_complete_decision():
    decision = _reconcile(None, "REQ-1009")
    assert decision.next_action == "escalate_manual_review"
    assert "vendor_risk_unavailable" in decision.risk_flags
    assert decision.recommendation and decision.next_step
    assert len(decision.evidence) >= 2
