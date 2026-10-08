"""Small presentation helpers. Business text is escaped before HTML rendering."""
from html import escape
from typing import Any

import streamlit as st

ACTION_LABELS = {
    "proceed_to_approval": "Ready for the approval process",
    "route_for_reviews": "Specialist reviews required",
    "evaluate_existing_tool_first": "Check the existing tool first",
    "request_clarification": "More information needed",
    "budget_exception_required": "Budget exception required",
    "escalate_manual_review": "Manual review required",
}
ARCHITECTURES = {"single": "Single agent", "staged": "Analyst + reviewer"}
DATA_LABELS = {
    "unknown": "Not yet specified", "none": "No business data",
    "internal_documents": "Internal documents", "internal_marketing": "Internal marketing data",
    "source_code": "Source code", "production_telemetry": "Production monitoring data",
    "confidential_documents": "Confidential documents", "employee_pii": "Employee personal information",
    "customer_pii": "Customer personal information",
}
SOURCE_LABELS = {
    "policy_checks": "Procurement policy", "run_policy_checks": "Procurement policy",
    "check_budget": "Department budget", "search_software_catalog": "Existing software",
    "get_vendor_registry_record": "Vendor registry", "get_vendor_risk_assessment": "Vendor security assessment",
    "get_requester_profile": "Requester", "get_purchase_history": "Purchase history",
}
RISK_LABELS = {
    "budget_insufficient": "Over budget", "budget_unverified": "Budget not verified",
    "existing_tool_overlap": "Existing software may cover this need",
    "security_review_required": "Security review", "privacy_review_required": "Privacy review",
    "legal_review_required": "Legal review", "vendor_review_expired": "Expired vendor assessment",
    "conflicting_vendor_evidence": "Vendor records disagree", "vendor_risk_unavailable": "Vendor check unavailable",
    "prompt_injection_detected": "Embedded instruction ignored", "missing_information": "Incomplete request",
    "evidence_unavailable": "Evidence unavailable",
}


def esc(value: Any) -> str:
    return escape(str(value if value is not None else "Not provided"), quote=True)


def text(value: Any, css: str = "body-text") -> None:
    st.html(f'<div class="{css}">{esc(value)}</div>')


def chips(values: list[str], *, risk: bool = False) -> None:
    labels = [RISK_LABELS.get(v, v.replace("_", " ").capitalize()) for v in values] if risk else values
    st.html('<div class="chips">' + ''.join(f'<span class="chip{" risk" if risk else ""}">{esc(v)}</span>' for v in labels) + '</div>')


def request_card(request: dict, employees: dict) -> None:
    person = employees.get(request.get("requester_id"), {})
    cost = request.get("annual_cost_usd")
    facts = [
        ("Annual cost", f"${cost:,.2f}" if isinstance(cost, (int, float)) else "Not provided"),
        ("People / licences", request.get("user_count") or "Not provided"),
        ("Data access", DATA_LABELS.get(request.get("data_access_level"), "Not yet specified")),
        ("Integrations", ", ".join(request.get("requested_integrations") or []) or "None requested"),
    ]
    st.html(
        '<article class="request-card">'
        f'<div class="request-heading">{esc(request.get("product_name") or "Untitled request")}</div>'
        f'<div class="muted">{esc(request.get("vendor_name"))} · {esc(request.get("category"))} · {esc(request.get("request_id"))}</div>'
        '<div class="facts">' + ''.join(f'<div><div class="fact-label">{esc(k)}</div><div class="fact-value">{esc(v)}</div></div>' for k,v in facts) + '</div>'
        '<div class="small-label">Business purpose</div>'
        f'<div class="purpose">{esc(request.get("business_justification") or "Not provided")}</div>'
        f'<div class="muted" style="margin-top:.9rem">Requested by {esc(person.get("name", request.get("requester_id")))} · {esc(person.get("department", "Department unknown"))} · {esc(str(request.get("urgency") or "normal").capitalize())} priority</div>'
        '</article>'
    )


def table(headers: list[str], rows: list[list[Any]]) -> None:
    st.html('<div class="compare-table"><table><thead><tr>' + ''.join(f'<th scope="col">{esc(v)}</th>' for v in headers)
            + '</tr></thead><tbody>' + ''.join('<tr>'+''.join(f'<td>{esc(v)}</td>' for v in row)+'</tr>' for row in rows) + '</tbody></table></div>')


def handoff_document(decision, request: dict) -> str:
    """A readable handoff that can be shared with the named reviewers."""
    lines = ["# Procurement review", "", f"Request: {request.get('request_id')} — {request.get('product_name')}",
             f"Analysis run: {decision.run_id}", f"Request fingerprint: {decision.request_fingerprint}",
             f"Architecture: {ARCHITECTURES.get(decision.telemetry.architecture, decision.telemetry.architecture)}",
             f"Model: {decision.telemetry.model}",
             "Analysis mode: " + ("Scripted demo" if decision.telemetry.model == "mock" else "Policy fallback" if decision.trace.get("errors") else "Live OpenAI"),
             "", "## Recommendation", decision.recommendation, "", "## Next step", decision.next_step,
             "", "## Required approvals", *[f"- {a}" for a in decision.required_approvals],
             "", "## Missing information", *([f"- {m}" for m in decision.missing_information] or ["No mandatory intake fields are missing."]),
             "", "## Risk flags", *([f"- {f}" for f in decision.risk_flags] or ["None identified by the checks."]),
             "", "## Evidence"]
    for item in decision.evidence:
        lines += [f"- {item.finding}", f"  Source: {item.source}; reference: {item.reference or 'not supplied'}"]
    if decision.rationale:
        lines += ["", "## Model assessment — requires human verification", decision.rationale]
    if decision.trace.get("errors"):
        lines += ["", "## Model stage unavailable", "This recommendation uses deterministic policy checks. Inspect run details before handoff."]
    lines += ["", "This document records a recommendation. A human must obtain the required approvals and handle the actual routing."]
    return "\n".join(lines)+"\n"
