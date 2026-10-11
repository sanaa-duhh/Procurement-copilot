"""Reconcile the model's draft with the deterministic findings.

The model may add context on top of the policy engine but never lower it:
approvals and risk flags are unioned with the engine's, missing information is
code-owned, the next action must be in the engine's allowed set, the factual panel contains
only code-authored findings from retrieved records, and human review is always required.
Every correction is recorded so the evaluation can measure how often each
architecture needed one.
"""
from __future__ import annotations

import re
from typing import Any

from src.contracts import CopilotDecision, ExtendedTelemetry, NEXT_ACTIONS
from src.evidence import fact_key
from src.rules import APPROVAL_ORDER, FLAG_TAXONOMY, RuleFindings, sort_approvals
from src.telemetry import RunTelemetryCounter
from src.tools import ToolRegistry

_APPROVAL_SYNONYMS = {
    "manager": "Manager", "line manager": "Manager", "direct manager": "Manager", "reporting manager": "Manager",
    "department head": "Department Head", "dept head": "Department Head", "head of department": "Department Head",
    "department director": "Department Head", "director": "Department Head",
    "procurement": "Procurement", "procurement team": "Procurement",
    "finance": "Finance", "finance team": "Finance", "budget owner": "Finance",
    "cfo": "CFO", "chief financial officer": "CFO",
    "security": "Security", "security team": "Security", "infosec": "Security", "information security": "Security",
    "privacy": "Privacy", "privacy team": "Privacy", "dpo": "Privacy", "data protection": "Privacy",
    "legal": "Legal", "legal team": "Legal",
}

_FLAG_SYNONYMS = {
    "overlap": "existing_tool_overlap", "existing tool": "existing_tool_overlap", "duplicate": "existing_tool_overlap",
    "budget": "budget_insufficient", "over budget": "budget_insufficient",
    "security": "security_review_required", "privacy": "privacy_review_required", "legal": "legal_review_required",
    "expired": "vendor_review_expired", "stale": "vendor_review_expired",
    "conflict": "conflicting_vendor_evidence",
    "unavailable": "vendor_risk_unavailable", "api": "vendor_risk_unavailable", "tool failure": "vendor_risk_unavailable",
    "injection": "prompt_injection_detected", "untrusted": "prompt_injection_detected",
    "missing": "missing_information", "incomplete": "missing_information",
}

NEXT_STEP_TEMPLATES = {
    "proceed_to_approval": "Send the request with this evidence package to {approvals} for approval.",
    "route_for_reviews": "Route the evidence package to {approvals}; the business approvals wait for the review outcomes.",
    "evaluate_existing_tool_first": "Ask the requester and the owner of the existing tool to confirm whether it already covers the need; if a gap is confirmed, continue to {approvals}.",
    "request_clarification": "Return the request to the requester for the missing information before any approval is routed.",
    "budget_exception_required": "Route to Finance for a budget-exception decision alongside {approvals}.",
    "escalate_manual_review": "Escalate to Procurement and Security for manual review; evidence could not be fully verified.",
}


def canonical_approval(name: str) -> str | None:
    key = re.sub(r"[\s_\-]+", " ", str(name)).strip().lower()
    key = re.sub(r"\b(approval|approver|review|reviewer|sign[- ]?off)\b", "", key).strip()
    if key in _APPROVAL_SYNONYMS:
        return _APPROVAL_SYNONYMS[key]
    for synonym, canonical in _APPROVAL_SYNONYMS.items():
        if synonym in key:
            return canonical
    return None


def canonical_flag(name: str) -> str | None:
    key = re.sub(r"[\s\-]+", "_", str(name)).strip().lower()
    if key in FLAG_TAXONOMY:
        return key
    spaced = key.replace("_", " ")
    for synonym, canonical in _FLAG_SYNONYMS.items():
        if synonym in spaced:
            return canonical
    return None


def _contradicted(flag: str, f: RuleFindings) -> bool:
    """Flags the deterministic evidence rules out."""
    if flag == "budget_insufficient":
        return f.budget_ok is True
    if flag == "budget_unverified":
        return f.budget_ok is not None
    if flag == "vendor_risk_unavailable":
        return not f.vendor_unavailable
    if flag == "missing_information":
        return not f.missing_information
    if flag == "vendor_review_expired":
        return "vendor_review_expired" not in f.risk_flags and f.vendor_status == "approved"
    if flag == "conflicting_vendor_evidence":
        return not f.vendor_conflict
    return False


def reconcile(
    draft: dict[str, Any] | None,
    findings: RuleFindings,
    registry: ToolRegistry,
    request: dict[str, Any],
    telemetry: RunTelemetryCounter,
    *,
    architecture: str,
    model: str,
    trace: dict[str, Any],
) -> CopilotDecision:
    corrections: list[str] = []
    draft = draft or {}
    if not draft:
        corrections.append("model produced no usable draft; deterministic findings only")

    # Approvals: union of canonical model approvals and the engine's minimums.
    approvals: set[str] = set(findings.required_approvals)
    llm_added: list[str] = []
    for raw in draft.get("required_approvals") or []:
        canonical = canonical_approval(raw)
        if canonical is None:
            corrections.append(f"dropped unrecognised approval '{raw}'")
        elif canonical not in approvals:
            approvals.add(canonical)
            llm_added.append(canonical)
    missing_from_draft = [a for a in findings.required_approvals if canonical_approval(a) not in {canonical_approval(x) for x in draft.get("required_approvals") or []}]
    if draft and missing_from_draft:
        corrections.append("added policy approvals the model omitted: " + ", ".join(missing_from_draft))

    # Risk flags: canonicalise, drop contradicted ones, union with the engine.
    flags: list[str] = list(findings.risk_flags)
    for raw in draft.get("risk_flags") or []:
        canonical = canonical_flag(raw)
        if canonical is None:
            corrections.append(f"dropped unrecognised risk flag '{raw}'")
            continue
        if canonical in flags:
            continue
        if _contradicted(canonical, findings):
            corrections.append(f"removed model flag '{canonical}' contradicted by deterministic evidence")
            continue
        flags.append(canonical)
    if draft.get("prompt_injection_detected") and "prompt_injection_detected" not in flags:
        flags.append("prompt_injection_detected")
    missing_flags = [f for f in findings.risk_flags if canonical_flag(f) not in {canonical_flag(x) for x in draft.get("risk_flags") or []}]
    if draft and missing_flags:
        corrections.append("added policy flags the model omitted: " + ", ".join(missing_flags))

    # Missing information is code-owned (policy section 1 is an explicit list).
    llm_missing = [str(m) for m in draft.get("missing_information") or []]
    if draft and len(llm_missing) > 0 and not findings.missing_information:
        corrections.append(f"discarded {len(llm_missing)} model missing-information item(s) on a complete request")

    # Next action must be consistent with the deterministic findings.
    next_action = draft.get("next_action")
    overridden = False
    if next_action not in NEXT_ACTIONS or next_action not in findings.allowed_next_actions:
        if draft:
            corrections.append(f"next_action '{next_action}' replaced by '{findings.preferred_next_action}' (allowed: {', '.join(findings.allowed_next_actions)})")
        next_action = findings.preferred_next_action
        overridden = True

    # The factual panel contains only code-authored facts from this request.
    # Naming a real tool is insufficient: the claimed value could still be invented.
    evidence = list(findings.evidence)
    supported = {fact_key(e.model_dump()) for e in evidence}
    ungrounded = sum(
        not isinstance(raw, dict) or fact_key(raw) not in supported
        for raw in draft.get("evidence") or []
    )
    if ungrounded:
        corrections.append(f"dropped {ungrounded} evidence item(s) without an exact verified fact")

    sorted_approvals = sort_approvals(approvals)
    approvals_text = " + ".join(sorted_approvals) if sorted_approvals else "the appropriate approvers"
    # These are operational instructions. Always render from the validated action;
    # a valid enum must not let 'buy immediately / skip Security' through in prose.
    next_step = NEXT_STEP_TEMPLATES[next_action].format(approvals=approvals_text)
    if findings.overlap_kind and next_action in {"route_for_reviews", "budget_exception_required"}:
        # Reviews come first (config/policy.toml sequencing rule); the overlap question still runs, in parallel.
        next_step += " In parallel, ask the owner of the existing catalog tool to confirm whether it already covers the need."
    recommendation = _default_recommendation(next_action, findings)

    telemetry_out = ExtendedTelemetry(
        llm_calls=telemetry.llm_calls,
        tool_calls=telemetry.tool_calls,
        tool_names=list(telemetry.tool_names),
        latency_ms=telemetry.elapsed_ms(),
        input_tokens=telemetry.input_tokens,
        output_tokens=telemetry.output_tokens,
        rate_limit_retries=telemetry.rate_limit_retries,
        rate_limit_wait_ms=telemetry.rate_limit_wait_ms,
        stage_latency_ms=dict(telemetry.stage_latency_ms),
        guardrail_corrections=corrections,
        architecture=architecture,
        model=model,
    )
    trace.update({
        "draft": draft,
        "findings": findings.as_dict(),
        "guardrail_corrections": corrections,
        "llm_added_approvals": llm_added,
        "llm_missing_information": llm_missing,
        "ungrounded_evidence_dropped": ungrounded,
        "tool_log": registry.log,
        "agent_tools_called": sorted(registry.called_tools(actor="single") | registry.called_tools(actor="analyst")),
    })
    return CopilotDecision(
        request_id=str(request.get("request_id")),
        recommendation=recommendation,
        evidence=evidence,
        required_approvals=sorted_approvals,
        missing_information=list(findings.missing_information),
        risk_flags=flags,
        next_step=next_step,
        human_review_required=True,
        telemetry=telemetry_out,
        next_action=next_action,
        rationale=(str(draft.get("rationale") or "").strip() or None) if not overridden else None,
        request_summary=str(draft.get("request_summary") or "").strip() or None,
        trace=trace,
    )


def _default_recommendation(next_action: str, f: RuleFindings) -> str:
    return {
        "proceed_to_approval": "Proceed to the standard approvals; no policy blockers found.",
        "route_for_reviews": "Route for " + " and ".join(f.reviews or ["policy"]) + " review before approval.",
        "evaluate_existing_tool_first": "Check whether the existing catalog tool already covers this need before buying.",
        "request_clarification": "Request clarification; the request is not ready for approval.",
        "budget_exception_required": "Budget exception needed before this can proceed.",
        "escalate_manual_review": "Escalate for manual review; evidence could not be fully verified.",
    }[next_action]
