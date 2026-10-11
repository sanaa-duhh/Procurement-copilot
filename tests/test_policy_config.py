"""Policy-as-config: drift detection, the data-classification register and the sequencing rule."""
from __future__ import annotations

import dataclasses

import pytest

from src import policy_config, rules
from src.data_access import get_request, load_policy_text
from src.guardrails import reconcile
from src.llm import MockClient
from src.rules import data_access_profile, evaluate, integration_is_sensitive
from src.solution import handle_request_payload
from src.telemetry import RunTelemetryCounter
from src.tools import ToolRegistry
from src.tools.policy import gather_evidence
from test_rules import _pack, _request


# -- the config and the written policy agree, and drift is caught ------------------------

def test_config_matches_the_written_policy():
    assert policy_config.check_against_document(policy_config.current(), load_policy_text()) == []


@pytest.mark.parametrize("old, new, expected", [
    ("| $10,000.01 - $25,000 |", "| $10,000.01 - $30,000 |", "approval tiers differ"),
    ("current for **365 days**", "current for **180 days**", "assessment validity"),
    ("annual spend is **$10,000 or more**", "annual spend is **$5,000 or more**", "legal new-vendor threshold"),
    ("**Policy version:** 2026.09", "**Policy version:** 2027.01", "policy version"),
])
def test_editing_the_written_policy_is_reported_as_drift(old, new, expected):
    text = load_policy_text()
    assert old in text
    problems = policy_config.check_against_document(policy_config.current(), text.replace(old, new))
    assert any(expected in p for p in problems)


def test_engine_thresholds_come_from_config():
    config = policy_config.current()
    assert rules.SECURITY_ASSESSMENT_VALIDITY_DAYS == config.assessment_validity_days
    assert rules.LEGAL_NEW_VENDOR_SPEND_THRESHOLD == config.legal_new_vendor_threshold
    assert [b for b, _ in rules.APPROVAL_TIERS] == [b for b, _ in config.approval_tiers]


def test_misordered_tiers_are_rejected(tmp_path):
    text = policy_config.CONFIG_PATH.read_text().replace('up_to_usd = "10000"', 'up_to_usd = "100000"')
    path = tmp_path / "policy.toml"
    path.write_text(text)
    with pytest.raises(ValueError):
        policy_config.load(path)


# -- data classification: whole words, and unknown labels fail closed --------------------

@pytest.mark.parametrize("label", ["payroll_data", "hr_records", "employee_salaries", "health_records", "customer_pii", "employee_pii"])
def test_personal_data_labels_require_security_and_privacy(label):
    profile = data_access_profile(label)
    assert profile["security_sensitive"] and profile["pii"] and not profile["unclassified"]


@pytest.mark.parametrize("label", ["zip_codes", "encoded_assets"])
def test_substrings_no_longer_count_as_source_code(label):
    profile = data_access_profile(label)
    assert not profile["source_code"]
    assert profile["unclassified"]          # unknown, so it is routed for classification instead


@pytest.mark.parametrize("label", ["internal_documents", "internal_marketing", "none"])
def test_registered_low_risk_labels_stay_low_risk(label):
    profile = data_access_profile(label)
    assert not profile["security_sensitive"] and not profile["pii"] and not profile["unclassified"]


def test_unclassified_data_is_routed_to_security_and_privacy_not_approved():
    f = evaluate(_pack(request=_request(data_access_level="telemetry_exports_v2")))
    assert {"Security", "Privacy"} <= set(f.required_approvals)
    assert "proceed_to_approval" not in f.allowed_next_actions
    assert f.data_classes == ["unclassified"]
    assert not f.missing_information          # a label was given; it needs classifying, not re-asking


@pytest.mark.parametrize("integration, sensitive", [
    ("Digital asset manager", False), ("Outsourced payroll", False), ("SSO", False),
    ("Git repositories", True), ("GitHub", True), ("Document repository", True), ("Production cloud account", True),
])
def test_integration_matching_is_whole_word(integration, sensitive):
    assert bool(integration_is_sensitive([integration])) is sensitive


# -- sequencing: specialist reviews come before an existing-tool check ------------------

def _syn17_like_findings():
    request = get_request("REQ-1003")         # CodeMate expansion: Security review + catalog overlap
    registry = ToolRegistry(request=request, telemetry=RunTelemetryCounter())
    return request, registry, evaluate(gather_evidence(registry, actor="guardrail"))


def test_reviews_come_before_an_existing_tool_check():
    _, _, f = _syn17_like_findings()
    assert f.reviews and f.overlap_kind
    assert f.allowed_next_actions == ["route_for_reviews"]


def test_sequencing_rule_is_configurable(monkeypatch):
    monkeypatch.setattr(rules, "POLICY", dataclasses.replace(rules.POLICY, reviews_before_overlap_check=False))
    _, _, f = _syn17_like_findings()
    assert "evaluate_existing_tool_first" in f.allowed_next_actions


def test_guardrail_corrects_an_overlap_first_draft_and_keeps_the_check_in_parallel():
    request, registry, f = _syn17_like_findings()
    draft = {"next_action": "evaluate_existing_tool_first", "required_approvals": f.required_approvals, "risk_flags": f.risk_flags}
    decision = reconcile(draft, f, registry, request, registry.telemetry, architecture="staged", model="test", trace={})
    assert decision.next_action == "route_for_reviews"
    assert "In parallel" in decision.next_step
    assert any("next_action" in c for c in decision.telemetry.guardrail_corrections)


def test_decisions_record_the_policy_version():
    decision = handle_request_payload(get_request("REQ-1010"), architecture="single", llm=MockClient())
    assert decision.policy_version == policy_config.current().version
