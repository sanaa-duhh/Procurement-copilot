"""Assessment adapter: `handle_request(request_id, architecture)`.

Pipeline for both architectures:
    request -> agent(s) with tools -> model draft
            -> deterministic policy engine (always runs, independent of the agent)
            -> guardrail reconciliation -> CopilotDecision (a ProcurementDecision)
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from src.audit import request_fingerprint

from src import rules
from src.agents import single, staged
from src.contracts import Architecture, CopilotDecision
from src.data_access import get_request
from src.guardrails import reconcile
from src.llm import LLMClient, get_llm_client
from src.telemetry import RunTelemetryCounter
from src.tools import ToolRegistry
from src.tools.policy import gather_evidence


def handle_request(request_id: str, architecture: Architecture = "single") -> CopilotDecision:
    """Entry point used by the public and hidden evaluation harness."""
    return handle_request_payload(get_request(request_id), architecture=architecture)


def handle_request_payload(request: dict[str, Any], architecture: Architecture = "single", llm: LLMClient | None = None) -> CopilotDecision:
    """Same pipeline for an ad-hoc request dict (UI form, synthetic evaluation cases)."""
    if architecture not in ("single", "staged"):
        raise ValueError(f"unknown architecture '{architecture}'")
    telemetry = RunTelemetryCounter()
    registry = ToolRegistry(request=request, telemetry=telemetry)
    client = llm or get_llm_client()

    runner = single.run if architecture == "single" else staged.run
    draft, trace = runner(client, request, registry, telemetry)

    # The policy engine runs in code regardless of what the agent did; cached tool results are reused.
    findings = rules.evaluate(gather_evidence(registry, actor="guardrail"))
    decision = reconcile(draft, findings, registry, request, telemetry, architecture=architecture, model=client.model, trace=trace)
    decision.run_id = str(uuid4())
    decision.request_fingerprint = request_fingerprint(request)
    decision.policy_version = rules.POLICY_VERSION
    return decision
