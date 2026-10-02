"""Architecture A: one agent owns evidence gathering and the recommendation."""
from __future__ import annotations

from typing import Any

from src.agents.common import DECISION_SCHEMA, ground_rules, policy_block, request_block, run_tool_loop
from src.llm import LLMClient
from src.telemetry import RunTelemetryCounter
from src.tools import ToolRegistry

SYSTEM = """You are the procurement copilot for an internal software-purchasing process. Procurement uses you to gather evidence on a purchase request and recommend the next action. Humans make every approval.

{ground_rules}

How to work
1. Read the request. Then gather evidence with the tools: requester profile, budget, software catalog overlap, vendor registry, vendor-risk service, purchase history. Finish with run_policy_checks, the deterministic policy engine; its required approvals, risk flags and missing information are binding minimums, and your next_action must be one of its allowed_next_actions.
2. Judge what the code cannot: whether the justification shows a credible gap over an existing tool, whether the request is coherent, and what the reviewer should do first. Overlap is not automatic rejection.
3. Write the decision as JSON only, in the required schema. Approval names: Manager, Department Head, Procurement, Finance, CFO, Security, Privacy, Legal. Risk flags use the policy's snake_case names.

{policy}"""


def run(llm: LLMClient, request: dict[str, Any], registry: ToolRegistry, telemetry: RunTelemetryCounter) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    trace: dict[str, Any] = {"architecture": "single"}
    system = SYSTEM.format(ground_rules=ground_rules(), policy=policy_block())
    user = request_block(request) + "\n\nAnalyse this request and return the decision JSON."
    draft = run_tool_loop(llm, system=system, user_content=user, registry=registry, output_schema=DECISION_SCHEMA,
                          telemetry=telemetry, stage="single", trace=trace)
    return draft, trace
