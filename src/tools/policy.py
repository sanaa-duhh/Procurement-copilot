"""`run_policy_checks` tool: the deterministic policy engine exposed to the agent.

It gathers whatever evidence it needs through the same registry (so results are
cached and counted once) and then calls `rules.evaluate`. The guardrail layer calls
the same function, which is what makes the final decision independent of whether
the model remembered to run it.
"""
from __future__ import annotations

from typing import Any

from src import rules


def gather_evidence(registry: Any, actor: str = "policy") -> rules.EvidencePack:
    request = registry.request
    requester = registry.call("get_requester_profile", {"employee_id": str(request.get("requester_id") or "")}, actor=actor)
    department = requester.get("department") if requester.get("found") else ""
    cost = request.get("annual_cost_usd")
    budget = registry.call("check_budget", {"department": department or "", "annual_cost_usd": cost if cost is not None else -1}, actor=actor) if cost is not None else None
    catalog = registry.call("search_software_catalog", {
        "product_name": str(request.get("product_name") or ""),
        "vendor_name": str(request.get("vendor_name") or ""),
        "category": str(request.get("category") or ""),
    }, actor=actor)
    vendor_name = str(request.get("vendor_name") or "")
    registry_record = registry.call("get_vendor_registry_record", {"vendor_name": vendor_name}, actor=actor) if vendor_name else None
    risk = registry.call("get_vendor_risk_assessment", {"vendor_name": vendor_name}, actor=actor) if vendor_name else None
    history = registry.call("get_purchase_history", {"vendor_name": vendor_name, "department": department or ""}, actor=actor)
    return rules.EvidencePack(
        request=request,
        requester=requester if requester.get("found") else None,
        budget=budget,
        catalog=catalog,
        vendor_registry=registry_record,
        vendor_risk=risk,
        purchase_history=history,
    )


def run_policy_checks(request_id: str, registry: Any) -> dict[str, Any]:
    if request_id != registry.request.get("request_id"):
        return {"error": f"policy checks run for the active request only ({registry.request.get('request_id')}), got '{request_id}'"}
    pack = gather_evidence(registry, actor="policy")
    findings = rules.evaluate(pack)
    return {"request_id": request_id, "reference_date": str(rules.reference_date()), **findings.as_dict(), "reference": "procurement_policy.md"}
