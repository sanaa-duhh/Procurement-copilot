"""Request entry, a single decision surface, and an explicit human handoff."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import streamlit as st

from src.audit import record_review, request_fingerprint
from src.solution import handle_request_payload
from ui.components import ACTION_LABELS, ARCHITECTURES, DATA_LABELS, SOURCE_LABELS, chips, esc, handoff_document, request_card, text

DATA_LEVELS = ["unknown", "none", "internal_documents", "internal_marketing", "source_code", "production_telemetry",
               "confidential_documents", "employee_pii", "customer_pii"]


def new_request(employees: dict) -> dict:
    previous = st.session_state.get("decision")
    completed = previous is not None and previous.request_id == "REQ-NEW"
    with st.expander("Request details", expanded=not completed):
        st.caption("Describe the purchase. Leave unknown values blank; the analysis will identify any required information.")
        left, right = st.columns(2, gap="large")
        with left:
            requester = st.selectbox("Requester", list(employees), key="new_requester",
                                    format_func=lambda k: f"{employees[k]['name']} · {employees[k]['department']}")
            product = st.text_input("Product or service", key="new_product")
            category = st.text_input("Category", placeholder="e.g. Project management", key="new_category")
            users = st.number_input("People / licences", min_value=1, value=None, step=1, key="new_users", placeholder="Number of users")
            data_access = st.selectbox("Data the product will access", DATA_LEVELS, key="new_data", format_func=DATA_LABELS.get)
        with right:
            vendor = st.text_input("Vendor", key="new_vendor")
            cost = st.number_input("Annual cost (USD)", min_value=0.0, value=None, step=100.0, format="%.2f", key="new_cost", placeholder="Annual amount or estimate")
            integrations = st.text_input("Integrations", placeholder="e.g. CRM, SSO — leave blank if none", key="new_integrations")
            urgency = st.selectbox("Priority", ["normal", "high", "urgent"], key="new_priority", format_func=str.capitalize)
        purpose = st.text_area("Business purpose", placeholder="What do you need to achieve, and why is existing software insufficient?", height=100, key="new_purpose")
    return {"request_id": "REQ-NEW", "requester_id": requester, "product_name": product, "vendor_name": vendor,
            "category": category, "annual_cost_usd": cost, "user_count": users, "business_justification": purpose,
            "data_access_level": data_access, "requested_integrations": [s.strip() for s in integrations.split(",") if s.strip()], "urgency": urgency}


def show_evidence(decision) -> None:
    st.caption("Facts from the records and policy checks. Each finding includes its source; model interpretation is shown separately above.")
    for item in decision.evidence:
        st.html('<article class="evidence-card">'
                f'<div class="evidence-title">{esc(SOURCE_LABELS.get(item.source, item.source))}</div>'
                f'<p>{esc(item.finding)}</p>'
                f'<div class="evidence-source">{esc(item.reference or "Reference not supplied")} · {esc(item.source)}</div></article>')


def show_run_details(decision, request: dict) -> None:
    tel = decision.telemetry
    a, b, c = st.columns(3)
    a.metric("Analysis time", f"{(tel.latency_ms or 0)/1000:.1f} s")
    b.metric("Model calls", tel.llm_calls or 0)
    c.metric("Executed tool calls", tel.tool_calls or 0)
    st.caption(f"{ARCHITECTURES.get(tel.architecture, tel.architecture)} · {tel.model} · {tel.input_tokens:,} input / {tel.output_tokens:,} output tokens")
    st.caption(f"Run {decision.run_id}")
    if decision.trace.get("errors"):
        with st.expander("Model error details", expanded=True):
            for error in decision.trace["errors"]:
                text(error)
    with st.expander(f"Policy corrections ({len(tel.guardrail_corrections)})"):
        if tel.guardrail_corrections:
            for correction in tel.guardrail_corrections:
                text("• " + correction)
        else:
            st.write("No field corrections were required. The final recommendation still passed through the policy checks.")
    with st.expander("Tool activity and retrieved records"):
        st.caption("Tool results can be reused within this analysis. Completed recommendations are not cached across analysis runs.")
        for entry in decision.trace.get("tool_log", []):
            state = "Reused earlier result" if entry.get("cached") else f"Executed by {entry.get('actor', 'agent')}"
            st.markdown(f"**{SOURCE_LABELS.get(entry['tool'], entry['tool'])}** · {state}")
            st.json({"tool": entry["tool"], "arguments": entry["args"], "result": entry["result"]}, expanded=False)
    with st.expander("Original request and policy findings"):
        st.json({"request": request, "policy_findings": decision.trace.get("findings", {})}, expanded=False)
    if decision.trace.get("evidence_pack"):
        with st.expander("Analyst-to-reviewer handoff"):
            st.json(decision.trace["evidence_pack"], expanded=False)


def human_review(decision, request: dict, audit_log: Path) -> None:
    st.subheader("Record the human review")
    st.caption("Save your recommendation locally, then share the handoff with the required reviewers. Saving here does not route a ticket or approve spending.")
    with st.form(f"human_review_{decision.run_id}"):
        left, right = st.columns(2)
        reviewer = left.text_input("Reviewer name")
        action = right.selectbox("Review outcome", ["Recommend the proposed next step", "Request clarification", "Hold for discussion", "Recommend declining"])
        note = st.text_area("Review note", placeholder="Record your reasoning or any follow-up needed.", height=90)
        save = st.form_submit_button("Save review", type="primary")
    if save:
        if not reviewer.strip():
            st.error("Enter a reviewer name before saving.")
        else:
            try:
                event_id = record_review(audit_log, decision, reviewer=reviewer, action=action, note=note)
            except (OSError, ValueError):
                st.error("The review could not be saved. Download the handoff and check the local review log before trying again.")
            else:
                st.session_state["saved_review"] = {"run_id": decision.run_id, "event_id": event_id, "reviewer": reviewer.strip(), "action": action}
    saved = st.session_state.get("saved_review", {})
    if saved.get("run_id") == decision.run_id:
        st.success(f"Saved locally for {saved['reviewer']}: {saved['action']}. Share the handoff to continue the process.")


def show_decision(decision, request: dict, audit_log: Path) -> None:
    action = decision.next_action
    tone = "" if action == "proceed_to_approval" else ("blocked" if action in {"escalate_manual_review", "budget_exception_required"} else "attention")
    fallback = bool(decision.trace.get("errors"))
    if fallback:
        st.warning("AI analysis was unavailable. This recommendation uses the deterministic policy checks; inspect Run details before handoff.")
    mode = "Scripted demo" if decision.telemetry.model == "mock" else ("Policy fallback" if fallback else "OpenAI analysis")
    st.html(f'<section class="decision {tone}"><div class="decision-meta">{esc(mode)} · {esc(ARCHITECTURES.get(decision.telemetry.architecture))} · Human approval required</div>'
            f'<div class="small-label">{esc(request.get("product_name") or request.get("request_id"))}</div>'
            f'<h2>{esc(ACTION_LABELS.get(action, "Review required"))}</h2><p>{esc(decision.recommendation)}</p>'
            f'<div class="next-step"><div class="small-label">Next step</div><p>{esc(decision.next_step)}</p></div></section>')
    st.markdown("**Required approvals**")
    if decision.required_approvals:
        chips(decision.required_approvals)
    else:
        st.caption("Approvals cannot yet be determined from the available information.")
    if decision.missing_information:
        st.error("Required information is missing. Return the request for clarification before proceeding.")
        for missing in decision.missing_information:
            text("• " + missing)
    if decision.risk_flags:
        st.markdown("**Issues to resolve**")
        chips(decision.risk_flags, risk=True)
    if decision.rationale and decision.telemetry.model != "mock":
        with st.expander("Model assessment — verify before acting", expanded=True):
            text(decision.rationale)
    if not decision.missing_information and decision.trace.get("llm_missing_information"):
        with st.expander("Suggested follow-up questions"):
            st.caption("Model suggestions for the reviewer, separate from mandatory intake fields.")
            for question in decision.trace["llm_missing_information"]:
                text("• " + question)
    evidence, review, details = st.tabs(["Evidence", "Human review", "Run details"], key=f"result_tabs_{decision.run_id}", on_change="rerun")
    with evidence:
        show_evidence(decision)
    with review:
        human_review(decision, request, audit_log)
    with details:
        show_run_details(decision, request)
    st.markdown("**Take this review forward**")
    a, b = st.columns(2)
    a.download_button("Download handoff", handoff_document(decision, request), file_name=f"{decision.request_id}_handoff.md", mime="text/markdown", on_click="ignore", width="stretch")
    b.download_button("Download decision JSON", json.dumps(decision.model_dump(), indent=2, default=str), file_name=f"{decision.request_id}_{decision.telemetry.architecture}.json", mime="application/json", on_click="ignore", width="stretch")


def render(requests: list[dict], employees: dict, *, provider: str, model: str, audit_log: Path) -> None:
    st.title("Review a purchase")
    text("Understand the need, check the evidence, and give the right people a clear next step.", "intro")
    left, right = st.columns([1, 1], gap="large")
    source = left.radio("Request source", ["Sample request", "New request"], horizontal=True, key="request_source")
    architecture = right.radio("Analysis approach", ["single", "staged"], horizontal=True, format_func=ARCHITECTURES.get, key="architecture")
    text("Single agent gathers evidence and recommends an action. Analyst + reviewer separates those two responsibilities.", "approach-note")
    if source == "Sample request":
        by_id = {r["request_id"]: r for r in requests}
        rid = st.selectbox("Choose a request", list(by_id), format_func=lambda k: f"{k} · {by_id[k]['product_name']}", key="sample_request")
        request = dict(by_id[rid])
        current = (request_fingerprint(request), architecture, provider, model, os.getenv("LLM_EFFORT", "medium"))
        if st.session_state.get("decision") is not None and st.session_state.get("decision_context") == current:
            with st.expander("Request details", expanded=False):
                request_card(request, employees)
        else:
            request_card(request, employees)
    else:
        request = new_request(employees)
    context = (request_fingerprint(request), architecture, provider, model, os.getenv("LLM_EFFORT", "medium"))
    if st.session_state.get("decision") is not None and st.session_state.get("decision_context") != context:
        st.session_state.pop("decision", None)
        st.session_state.pop("saved_review", None)
    decision = st.session_state.get("decision")
    credentials_ready = provider == "mock" or bool(os.getenv("OPENAI_API_KEY"))
    if not credentials_ready:
        st.warning("Live analysis is unavailable: configure OPENAI_API_KEY in the shell or .env, then restart the app.")
    st.caption("Scripted demo · no model calls. Use the comparison tab to inspect saved live results." if provider == "mock" else "Live OpenAI analysis · starts only when you click Analyse · each run uses API credits.")
    run = st.button("Analyse again" if decision is not None else "Analyse request", type="primary", key="analyse", disabled=not credentials_ready)
    if run:
        st.session_state.pop("decision", None)
        st.session_state.pop("saved_review", None)
        decision = None
        completed = False
        with st.status("Analysing the request…", expanded=True) as progress:
            st.write("Collecting evidence and preparing a recommendation. Policy checks run before the result is shown.")
            try:
                decision = handle_request_payload(request, architecture=architecture)
            except Exception as exc:
                progress.update(label="Analysis could not finish", state="error", expanded=True)
                st.error("No new recommendation was saved. Check the service details and try again.")
                with st.expander("Technical details"):
                    text(f"{type(exc).__name__}: {exc}")
            else:
                st.session_state["decision"] = decision
                st.session_state["decision_context"] = context
                st.session_state["analysed_at"] = datetime.now(timezone.utc).isoformat()
                progress.update(label="Policy checks complete; model unavailable" if decision.trace.get("errors") else "Analysis complete", state="error" if decision.trace.get("errors") else "complete", expanded=False)
                completed = True
        if completed:
            # Re-render the completed state once: collapse intake, preserve the
            # decision, and reset the button event without another model call.
            st.rerun()
    if decision is not None:
        show_decision(decision, request, audit_log)
    else:
        st.html('<div class="empty-state"><div class="empty-title">Your recommendation will appear here.</div>Submit the request to see the next step, required approvals and supporting evidence. You can inspect the saved architecture comparison without running an analysis.</div>')
