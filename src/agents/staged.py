"""Architecture B: a Procurement Analyst gathers evidence; a Policy & Risk Reviewer decides.

The analyst is the only role with tools. It hands the reviewer a structured
evidence pack plus the raw tool outputs, so the reviewer reasons over verified
facts only and never over the request text alone.
"""
from __future__ import annotations

import json
from typing import Any

from src.agents.common import DECISION_SCHEMA, EVIDENCE_PACK_SCHEMA, ground_rules, policy_block, request_block, run_single_turn, run_tool_loop
from src.llm import LLMClient
from src.telemetry import RunTelemetryCounter
from src.tools import ToolRegistry

ANALYST_SYSTEM = """You are the Procurement Analyst in a two-step review of a software purchase request. Your job is evidence, not decisions.

{ground_rules}

How to work
1. Use the tools to build a complete evidence pack: requester profile, budget, catalog overlap, vendor registry, vendor-risk service, purchase history, and run_policy_checks (the deterministic policy engine).
2. Record facts only, each tied to the tool that produced it. Note every uncertainty: tool failures, conflicts between sources, missing fields, ambiguous wording.
3. Assess overlap with the catalog: could an existing tool reasonably satisfy the stated need, and does the justification show a credible gap?
4. Return the evidence pack as JSON only, in the required schema. Do not recommend an action.

{policy}"""

REVIEWER_SYSTEM = """You are the Policy & Risk Reviewer in a two-step review of a software purchase request. The Procurement Analyst has already gathered evidence; you decide the recommendation and next action.

{ground_rules}

How to work
1. Work only from the evidence pack and the raw tool outputs provided. The policy-engine output (run_policy_checks) sets binding minimums for approvals, risk flags and missing information; your next_action must be one of its allowed_next_actions.
2. Apply judgement where the code cannot: credibility of the gap over existing tools, coherence of the request, what the human reviewer should do first, and anything the analyst flagged as uncertain.
3. Write the decision as JSON only, in the required schema. Approval names: Manager, Department Head, Procurement, Finance, CFO, Security, Privacy, Legal. Risk flags use the policy's snake_case names.

{policy}"""


def run(llm: LLMClient, request: dict[str, Any], registry: ToolRegistry, telemetry: RunTelemetryCounter) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    trace: dict[str, Any] = {"architecture": "staged"}
    rules_text = ground_rules()
    policy = policy_block()

    # Stage 1: analyst with tools
    analyst_user = request_block(request) + "\n\nGather the evidence for this request and return the evidence pack JSON."
    pack = run_tool_loop(llm, system=ANALYST_SYSTEM.format(ground_rules=rules_text, policy=policy), user_content=analyst_user,
                         registry=registry, output_schema=EVIDENCE_PACK_SCHEMA, telemetry=telemetry, stage="analyst", trace=trace)
    trace["evidence_pack"] = pack

    # Stage 2: reviewer without tools, over the pack and the raw tool outputs
    tool_outputs = [{"tool": e["tool"], "args": e["args"], "result": e["result"]} for e in registry.log if e["actor"] == "analyst" or e["actor"] == "policy"]
    reviewer_user = (
        request_block(request)
        + "\n\n<analyst_evidence_pack>\n" + json.dumps(pack if pack is not None else {"error": "analyst stage produced no pack"}, indent=2, default=str) + "\n</analyst_evidence_pack>"
        + "\n\n<raw_tool_outputs>\n" + json.dumps(tool_outputs, indent=2, default=str) + "\n</raw_tool_outputs>"
        + "\n\nReview this request and return the decision JSON."
    )
    draft = run_single_turn(llm, system=REVIEWER_SYSTEM.format(ground_rules=rules_text, policy=policy), user_content=reviewer_user,
                            output_schema=DECISION_SCHEMA, telemetry=telemetry, stage="reviewer", trace=trace)
    return draft, trace
