"""Procurement Request Copilot — product UI.

Three panels: request details, evidence, recommendation + human action.
The copilot recommends; a named human records the decision here. Nothing in
this UI purchases, approves spend or edits budgets.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from src.contracts import CopilotDecision
from src.data_access import load_budgets, load_employees, load_requests, load_software_catalog, load_vendors
from src.rules import reference_date
from src.solution import handle_request_payload

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
    provider = os.getenv("LLM_PROVIDER", "anthropic")
    model = os.getenv("MODEL_NAME", "claude-opus-5") if provider != "mock" else "scripted mock"
    st.caption(f"Model: `{model}` · provider `{provider}`")
    if provider != "mock" and not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        st.warning("No ANTHROPIC_API_KEY found. Add it to .env, or set LLM_PROVIDER=mock to try the flow offline.")

    source = st.radio("Request source", ["Existing request", "New request"])
    if source == "Existing request":
        request_id = st.selectbox("Request", list(BY_ID), format_func=lambda rid: f"{rid} · {BY_ID[rid]['product_name']}")
        request = dict(BY_ID[request_id])
    else:
        with st.form("new_request"):
            st.caption("Fields are treated as untrusted data.")
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
            st.session_state["decision_request"] = request

decision: CopilotDecision | None = st.session_state.get("decision")
if decision is not None and st.session_state.get("decision_request", {}).get("request_id") != request.get("request_id"):
    decision = None

# --------------------------------------------------------------------------
# Panel 2: evidence
# --------------------------------------------------------------------------
with col_evidence:
    st.subheader("Evidence")
    if decision is None:
        st.caption("Run the analysis to gather evidence from the tools.")
    else:
        rows = [{"source": e.source, "finding": e.finding, "reference": e.reference or ""} for e in decision.evidence]
        st.dataframe(rows, width="stretch", hide_index=True, height=min(60 + 38 * len(rows), 520))
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
            st.caption(decision.rationale)
        st.markdown("**Approvals required**")
        st.markdown("\n".join(f"- {a}" for a in decision.required_approvals) or "_none determinable yet_")
        if decision.risk_flags:
            st.markdown("**Risk flags**  \n" + " ".join(f"`{f}`" for f in decision.risk_flags))
        if decision.missing_information:
            st.markdown("**Missing information**")
            st.markdown("\n".join(f"- {m}" for m in decision.missing_information))
        st.markdown("**Next step**")
        st.success(decision.next_step)
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
                AUDIT_LOG.parent.mkdir(exist_ok=True)
                with AUDIT_LOG.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                        "request_id": decision.request_id, "architecture": architecture, "reviewer": reviewer.strip(),
                        "human_action": action, "note": note.strip(), "copilot_next_action": decision.next_action,
                        "required_approvals": decision.required_approvals, "risk_flags": decision.risk_flags,
                    }) + "\n")
                st.success(f"Recorded. The request now goes to {', '.join(decision.required_approvals) or 'the requester'}; nothing has been purchased or approved by the copilot.")
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
