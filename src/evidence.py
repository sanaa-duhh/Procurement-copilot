"""Exact support checks against code-authored facts exposed by the policy tool.

This deliberately does not claim to measure semantic entailment of free prose.
Models select/copy facts; their interpretation belongs in the rationale field.
"""
from typing import Any


def fact_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return tuple(str(item.get(key) or "").strip() for key in ("source", "finding", "reference"))


def draft_support(evidence: list[dict[str, Any]], tool_log: list[dict[str, Any]]) -> float:
    facts = set()
    for entry in tool_log:
        if entry["actor"] == "guardrail" or entry["tool"] != "run_policy_checks":
            continue
        facts.update(fact_key(item) for item in entry["result"].get("evidence", []))
    if not evidence:
        return 0.0
    return round(sum(isinstance(e, dict) and fact_key(e) in facts for e in evidence) / len(evidence), 3)
