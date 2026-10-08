"""Procurement Request Copilot — product UI.

Three panels: request details, evidence, recommendation + human action.
The copilot recommends; a named human records the decision here. Nothing in
this UI purchases, approves spend or edits budgets.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st

from src.contracts import CopilotDecision
from src.audit import record_review, request_fingerprint
from src.data_access import load_budgets, load_employees, load_requests, load_software_catalog, load_vendors
from src.rules import reference_date
from src.solution import handle_request_payload
from src.llm import configured_model

ROOT = Path(__file__).resolve().parent
AUDIT_LOG = ROOT / "logs" / "human_decisions.jsonl"
REQUESTS = load_requests()
BY_ID = {r["request_id"]: r for r in REQUESTS}
EMPLOYEES = load_employees().set_index("employee_id")

ACTION_LABELS = {
    "proceed_to_approval": "Proceed to approval",
    "route_for_reviews": "Route for reviews",
    "evaluate_existing_tool_first": "Check existing tool first",
    "request_clarification": "Request clarification",
    "budget_exception_required": "Budget exception required",
    "escalate_manual_review": "Escalate for manual review",
}

st.set_page_config(page_title="Procurement Request Copilot", layout="wide")
st.title("Procurement Request Copilot")
st.caption(f"Advisory only. Humans approve. Policy reference date {reference_date()}.")

# --------------------------------------------------------------------------
# Sidebar: architecture + request source
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Run settings")
    architecture = st.radio("Architecture", ["single", "staged"], horizontal=True,
                            help="single: one agent gathers evidence and decides. staged: an analyst gathers, a reviewer decides.")
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = configured_model(provider)
    st.caption(f"Model: `{model}` · provider `{provider}`")
    credential = "OPENAI_API_KEY"
    if provider != "mock" and not os.getenv(credential):
        st.warning(f"No {credential} found. Add it to .env, or set LLM_PROVIDER=mock to try the flow offline.")

    source = st.radio("Request source", ["Existing request", "New request"])
    if source == "Existing request":
        request_id = st.selectbox("Request", list(BY_ID), format_func=lambda rid: f"{rid} · {BY_ID[rid]['product_name']}")
        request = dict(BY_ID[request_id])
    else:
        with st.form("new_request"):
            st.caption("Describe the purchase and the data it will access.")
            requester_id = st.selectbox("Requester", list(EMPLOYEES.index), format_func=lambda e: f"{e} · {EMPLOYEES.loc[e, 'name']} ({EMPLOYEES.loc[e, 'department']})")
            product_name = st.text_input("Product name")
            vendor_name = st.text_input("Vendor name")
            category = st.text_input("Category")
            annual_cost = st.number_input("Annual cost (USD)", min_value=0.0, step=100.0, value=0.0)
            cost_known = st.checkbox("Annual cost is known", value=True)
            user_count = st.number_input("Users / licenses", min_value=0, step=1, value=0)
            data_access = st.selectbox("Data access level", ["none", "internal_documents", "internal_marketing", "source_code", "production_telemetry",
                                                             "confidential_documents", "employee_pii", "customer_pii", "unknown"])
            integrations = st.text_input("Requested integrations (comma separated)")
            justification = st.text_area("Business justification")
            urgency = st.selectbox("Urgency", ["normal", "high", "urgent"])
            submitted = st.form_submit_button("Use this request")
        request = {
            "request_id": "REQ-NEW",
            "requester_id": requester_id,
            "product_name": product_name,
            "vendor_name": vendor_name,
            "category": category,
            "annual_cost_usd": annual_cost if cost_known else None,
            "user_count": int(user_count) or None,
            "business_justification": justification,
            "data_access_level": data_access,
            "requested_integrations": [s.strip() for s in integrations.split(",") if s.strip()],
            "urgency": urgency,
        }
    run = st.button("Run analysis", type="primary", width="stretch")

# --------------------------------------------------------------------------
# Panel 1: request details
# --------------------------------------------------------------------------
col_request, col_evidence, col_decision = st.columns([0.9, 1.2, 1.0], gap="large")

with col_request:
    st.subheader("Request")
    req_id = request.get("requester_id")
    requester = EMPLOYEES.loc[req_id] if req_id in EMPLOYEES.index else None
    st.markdown(f"**{request.get('product_name') or '—'}**  \n{request.get('vendor_name') or '—'} · {request.get('category') or '—'}")
    if requester is not None:
        st.markdown(f"Requested by **{requester['name']}** ({req_id}), {requester['department']}, {requester['country']}")
    cost = request.get("annual_cost_usd")
    st.metric("Annual cost", f"${cost:,.2f}" if cost is not None else "not provided")
    c1, c2 = st.columns(2)
    c1.metric("Users", request.get("user_count") if request.get("user_count") is not None else "not provided")
    c2.metric("Urgency", request.get("urgency") or "—")
    st.markdown(f"**Data access:** `{request.get('data_access_level')}`  \n**Integrations:** {', '.join(request.get('requested_integrations') or []) or 'none'}")
    st.markdown("**Justification**")
    st.info(request.get("business_justification") or "—")
    with st.expander("Raw request JSON"):
        st.json(request)

# --------------------------------------------------------------------------
# Run the copilot
# --------------------------------------------------------------------------
if run:
    with st.spinner(f"Running the {architecture} architecture…"):
        try:
            decision = handle_request_payload(request, architecture=architecture)
        except Exception as exc:  # surface, never hide
            st.session_state.pop("decision", None)
            st.error(f"The copilot could not complete this run: {type(exc).__name__}: {exc}")
        else:
            st.session_state["decision"] = decision
            st.session_state["decision_context"] = (request_fingerprint(request), architecture, provider, model)

decision: CopilotDecision | None = st.session_state.get("decision")
if decision is not None and st.session_state.get("decision_context") != (request_fingerprint(request), architecture, provider, model):
    decision = None

# --------------------------------------------------------------------------
# Panel 2: evidence
# --------------------------------------------------------------------------
with col_evidence:
    st.subheader("Evidence")
    if decision is None:
        st.caption("Run the analysis to gather evidence from the tools.")
    else:
        for item in decision.evidence:
            label = item.finding if len(item.finding) <= 90 else item.finding[:87] + "…"
            material_uncertainty = any(term in item.finding.lower() for term in ("disagree", "could not verify", "could not be verified", "missing:"))
            with st.expander(label.replace("$", r"\$"), expanded=material_uncertainty):
                st.write(item.finding.replace("$", r"\$"))
                st.caption(f"Source: {item.source} · Reference: {item.reference or 'not supplied'}")
        trace = decision.trace
        with st.expander(f"Tool calls ({decision.telemetry.tool_calls} executed)"):
            for entry in trace.get("tool_log", []):
                tag = "cached" if entry["cached"] else entry["actor"]
                st.markdown(f"`{entry['tool']}` · {tag} · args `{json.dumps(entry['args'])}`")
                st.json(entry["result"], expanded=False)
        with st.expander("Deterministic policy findings"):
            st.json(trace.get("findings", {}), expanded=False)
        if trace.get("evidence_pack"):
            with st.expander("Analyst evidence pack (staged only)"):
                st.json(trace["evidence_pack"], expanded=False)
        if trace.get("errors"):
            st.warning("Model stage errors: " + "; ".join(trace["errors"]))

# --------------------------------------------------------------------------
# Panel 3: recommendation + human action
# --------------------------------------------------------------------------
with col_decision:
    st.subheader("Recommendation")
    if decision is None:
        st.caption("No recommendation yet.")
    else:
        label = ACTION_LABELS.get(decision.next_action or "", decision.next_action or "")
        st.markdown(f"### {label}")
        st.markdown(decision.recommendation)
        if decision.rationale:
            st.markdown("**Model assessment · requires human verification**")
            st.caption(decision.rationale)
        st.markdown("**Approvals required**")
        st.markdown("\n".join(f"- {a}" for a in decision.required_approvals) or "_none determinable yet_")
        if decision.risk_flags:
            st.markdown("**Risk flags**  \n" + " ".join(f"`{f}`" for f in decision.risk_flags))
        if decision.missing_information:
            st.markdown("**Missing information**")
            st.markdown("\n".join(f"- {m}" for m in decision.missing_information))
        if not decision.missing_information and decision.trace.get("llm_missing_information"):
            with st.expander("Reviewer follow-up questions"):
                st.caption("Model-suggested questions for human verification; these are separate from required intake fields.")
                for question in decision.trace["llm_missing_information"]:
                    st.write("• " + question.replace("$", r"\$"))
        st.markdown("**Next step**")
        st.info(decision.next_step)
        if decision.telemetry.guardrail_corrections:
            with st.expander(f"Guardrail corrections ({len(decision.telemetry.guardrail_corrections)})"):
                for c in decision.telemetry.guardrail_corrections:
                    st.markdown(f"- {c}")

        st.divider()
        st.markdown("**Human review**")
        with st.form("human_action"):
            reviewer = st.text_input("Reviewer")
            action = st.selectbox("Decision", ["Route as recommended", "Send back to requester", "Hold for discussion", "Decline request"])
            note = st.text_area("Note", height=80)
            recorded = st.form_submit_button("Record decision")
        if recorded:
            if not reviewer.strip():
                st.error("A reviewer name is required.")
            else:
                event_id = record_review(AUDIT_LOG, decision, reviewer=reviewer, action=action, note=note)
                st.success(f"Review recorded locally ({event_id[:12]}). Share the downloaded decision with the reviewers to complete the handoff.")
        st.download_button("Download decision JSON", data=json.dumps(decision.model_dump(), indent=2, default=str),
                           file_name=f"{decision.request_id}_{architecture}.json", mime="application/json")

# --------------------------------------------------------------------------
# Footer: telemetry
# --------------------------------------------------------------------------
if decision is not None:
    t = decision.telemetry
    st.divider()
    st.caption(
        f"{t.architecture} · {t.model} · {t.llm_calls} LLM calls · {t.tool_calls} tool calls · {t.latency_ms:.0f} ms "
        f"({', '.join(f'{k} {v:.0f} ms' for k, v in t.stage_latency_ms.items())}) · {t.input_tokens} in / {t.output_tokens} out tokens"
    )
