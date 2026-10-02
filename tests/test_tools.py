"""Tool-layer tests: deterministic lookups and failure handling. No model."""
from __future__ import annotations

import requests

from src.data_access import get_request
from src.telemetry import RunTelemetryCounter
from src.tools import ToolRegistry
from src.tools import vendor as vendor_tool
from src.tools.budget import check_budget
from src.tools.catalog import search_software_catalog


def test_budget_tool_reports_shortfall():
    result = check_budget("Sales", 22000)
    assert result["found"] and result["within_budget"] is False and result["shortfall_usd"] == 4000.0


def test_budget_tool_unknown_department():
    assert check_budget("Go To Market", 100)["found"] is False


def test_catalog_expansion_vs_service_from_same_vendor():
    addon = search_software_catalog("SignFlow Add-on", "SignFlow", "E-signature")
    assert addon["matches"][0]["match_type"] == "same_vendor_same_category"
    training = search_software_catalog("SignFlow Training Pack", "SignFlow", "Professional Services")
    assert training["matches"][0]["match_type"] == "same_vendor"


def test_catalog_same_category_different_vendor():
    result = search_software_catalog("BrandBoard Enterprise", "BrandBoard", "Design & Creative")
    assert {m["match_type"] for m in result["matches"]} == {"same_category"}
    assert {m["vendor_name"] for m in result["matches"]} == {"PixelCraft", "CreativeSuite Labs"}


def test_vendor_risk_tool_degrades_on_connection_error(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(vendor_tool, "get_vendor_risk", lambda name, timeout_seconds=3.0: (_ for _ in ()).throw(vendor_tool.VendorRiskUnavailable("ConnectionError")))
    result = vendor_tool.get_vendor_risk_assessment("Anyone")
    assert result["available"] is False and result["error_kind"] == "unavailable"


def test_vendor_risk_tool_handles_503(monkeypatch):
    class Resp:
        status_code = 503
        ok = False
        text = ""
        def json(self):
            return {"detail": "Upstream vendor assessment provider is temporarily unavailable."}
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp())
    result = vendor_tool.get_vendor_risk_assessment("NimbusAI")
    assert result["available"] is False and "503" in result["error"]


def test_registry_caches_and_counts_once():
    reg = ToolRegistry(request=get_request("REQ-1001"), telemetry=RunTelemetryCounter())
    reg.call("check_budget", {"department": "Finance", "annual_cost_usd": 800})
    reg.call("check_budget", {"department": "Finance", "annual_cost_usd": 800}, actor="guardrail")
    assert reg.telemetry.tool_calls == 1 and reg.telemetry.cache_hits == 1
    assert reg.called_tools(actor="agent") == {"check_budget"}


def test_registry_rejects_policy_checks_for_other_request():
    reg = ToolRegistry(request=get_request("REQ-1001"), telemetry=RunTelemetryCounter())
    assert "error" in reg.call("run_policy_checks", {"request_id": "REQ-9999"})


def test_unknown_tool_is_reported_not_raised():
    reg = ToolRegistry(request=get_request("REQ-1001"), telemetry=RunTelemetryCounter())
    assert "error" in reg.call("purchase_now", {})
