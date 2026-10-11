from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    source: str = Field(description="Tool/data source name")
    finding: str = Field(description="Concise factual finding")
    reference: str | None = Field(default=None, description="Optional record ID / policy section / endpoint")


class RunTelemetry(BaseModel):
    llm_calls: int | None = None
    tool_calls: int | None = None
    tool_names: list[str] = Field(default_factory=list)


class ProcurementDecision(BaseModel):
    request_id: str
    recommendation: str = Field(description="Short recommendation label or sentence")
    evidence: list[EvidenceItem] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    next_step: str
    human_review_required: bool = True
    telemetry: RunTelemetry | None = None


Architecture = Literal["single", "staged"]

# Approval names used throughout the project (policy section 4-7):
#   Manager, Department Head, Procurement, Finance, CFO, Security, Privacy, Legal
#
# Risk-flag taxonomy (policy sections 2-10):
#   existing_tool_overlap, budget_insufficient, security_review_required,
#   privacy_review_required, legal_review_required, vendor_review_expired,
#   conflicting_vendor_evidence, vendor_risk_unavailable,
#   prompt_injection_detected, missing_information, budget_unverified

NextAction = Literal[
    "proceed_to_approval",
    "route_for_reviews",
    "evaluate_existing_tool_first",
    "request_clarification",
    "budget_exception_required",
    "escalate_manual_review",
]

NEXT_ACTIONS: tuple[str, ...] = (
    "proceed_to_approval",
    "route_for_reviews",
    "evaluate_existing_tool_first",
    "request_clarification",
    "budget_exception_required",
    "escalate_manual_review",
)


class ExtendedTelemetry(RunTelemetry):
    """Telemetry the evaluation runner reads. Extends the starter contract."""

    latency_ms: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    rate_limit_retries: int = 0
    rate_limit_wait_ms: float = 0
    stage_latency_ms: dict[str, float] = Field(default_factory=dict)
    guardrail_corrections: list[str] = Field(default_factory=list)
    architecture: str | None = None
    model: str | None = None


class CopilotDecision(ProcurementDecision):
    """ProcurementDecision plus the fields the UI and evaluation need.

    Everything the starter harness validates is still present and unchanged;
    the extra fields are optional and ignored by the public runner.
    """

    run_id: str | None = None
    request_fingerprint: str | None = None
    policy_version: str | None = None
    next_action: NextAction | None = None
    rationale: str | None = None
    request_summary: str | None = None
    telemetry: ExtendedTelemetry | None = None
    trace: dict[str, Any] = Field(default_factory=dict, exclude=True)
