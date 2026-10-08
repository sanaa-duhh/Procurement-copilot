"""Tool layer.

Each tool is a plain Python function that returns a JSON-serialisable dict. The
`ToolRegistry` binds the tools to one request run, exposes their JSON schemas to
the model, caches results per (tool, args) so the deterministic guardrail can
reuse what the agent already fetched, and records telemetry.

Deterministic (non-LLM) tools: every tool here is deterministic. `run_policy_checks`
is the one the assignment asks for explicitly: it applies the policy engine in code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable
from jsonschema import Draft202012Validator

from src.telemetry import RunTelemetryCounter
from src.tools import budget, catalog, policy, purchase_history, requester, vendor

ToolFn = Callable[..., dict[str, Any]]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: ToolFn
    deterministic: bool = True

    def as_api_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "strict": True,
        }


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required if required is not None else list(properties),
        "additionalProperties": False,
    }


def build_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            "get_requester_profile",
            "Look up the requesting employee: name, department, manager, level and country. "
            "Use the requester_id from the request.",
            _schema({"employee_id": {"type": "string", "description": "Employee ID such as E004"}}),
            requester.get_requester_profile,
        ),
        ToolSpec(
            "check_budget",
            "Deterministic budget check: compares an annual cost against the department's available "
            "software budget and returns the shortfall if any.",
            _schema({
                "department": {"type": "string", "description": "Department name exactly as on the requester profile"},
                "annual_cost_usd": {"type": "number", "description": "Annualised request cost in USD"},
            }),
            budget.check_budget,
        ),
        ToolSpec(
            "search_software_catalog",
            "Search the approved software catalog for the same product, the same vendor, or the same "
            "category so existing tools that may satisfy the need are surfaced.",
            _schema({
                "product_name": {"type": "string"},
                "vendor_name": {"type": "string"},
                "category": {"type": "string"},
            }),
            catalog.search_software_catalog,
        ),
        ToolSpec(
            "get_vendor_registry_record",
            "Read the internal procurement vendor registry: procurement status, security status and "
            "review date, legal terms status, notes.",
            _schema({"vendor_name": {"type": "string"}}),
            vendor.get_vendor_registry_record,
        ),
        ToolSpec(
            "get_vendor_risk_assessment",
            "Call the external vendor-risk service for the vendor's current security review status, risk "
            "level, last review date and data-handling attributes. May be unavailable; the result says so.",
            _schema({"vendor_name": {"type": "string"}}),
            vendor.get_vendor_risk_assessment,
        ),
        ToolSpec(
            "get_purchase_history",
            "List prior purchases and renewals for a vendor and/or department.",
            _schema({
                "vendor_name": {"type": "string", "description": "Vendor to filter on; empty string for all"},
                "department": {"type": "string", "description": "Department to filter on; empty string for all"},
            }),
            purchase_history.get_purchase_history,
        ),
        ToolSpec(
            "run_policy_checks",
            "Deterministic policy engine. Applies the procurement policy in code to the request and all "
            "gathered evidence: required fields, approval thresholds, budget, overlap, vendor assessment "
            "freshness (365 days from the policy reference date), registry/service conflicts, security, "
            "privacy and legal triggers, and the untrusted-text scan. Returns the minimum approvals, risk "
            "flags, missing information and the next actions that are consistent with policy.",
            _schema({"request_id": {"type": "string"}}),
            policy.run_policy_checks,
        ),
    ]


@dataclass
class ToolRegistry:
    """Binds tool functions to one request run."""

    request: dict[str, Any]
    telemetry: RunTelemetryCounter
    specs: list[ToolSpec] = field(default_factory=build_specs)
    cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    log: list[dict[str, Any]] = field(default_factory=list)

    def api_tools(self) -> list[dict[str, Any]]:
        return [spec.as_api_tool() for spec in self.specs]

    def names(self) -> list[str]:
        return [spec.name for spec in self.specs]

    def call(self, name: str, args: dict[str, Any], actor: str = "agent") -> dict[str, Any]:
        spec = next((s for s in self.specs if s.name == name), None)
        if spec is None:
            result = {"error": f"unknown tool '{name}'", "available_tools": self.names()}
            self.log.append({"actor": actor, "tool": name, "args": args, "result": result, "cached": False})
            return result
        key = name + ":" + json.dumps(args, sort_keys=True, default=str)
        if key in self.cache:
            self.telemetry.record_cache_hit()
            self.log.append({"actor": actor, "tool": name, "args": args, "result": self.cache[key], "cached": True})
            return self.cache[key]
        self.telemetry.record_tool_call(name)
        try:
            errors = list(Draft202012Validator(spec.input_schema).iter_errors(args))
            if errors:
                raise TypeError(f"schema validation failed at {list(errors[0].path)} ({errors[0].validator})")
            if name == "run_policy_checks":
                result = spec.fn(registry=self, **args)
            else:
                result = spec.fn(**args)
        except TypeError as exc:
            result = {"error": f"bad arguments for {name}: {exc}"}
        except Exception as exc:  # a tool must never take the run down
            result = {"error": f"{type(exc).__name__}: {exc}"}
        self.cache[key] = result
        self.log.append({"actor": actor, "tool": name, "args": args, "result": result, "cached": False})
        return result

    def called_tools(self, actor: str | None = None) -> set[str]:
        return {entry["tool"] for entry in self.log if actor is None or entry["actor"] == actor}

    def serialized_results(self, actor: str | None = None) -> str:
        """Everything the tools returned, for grounding checks."""
        return json.dumps([e["result"] for e in self.log if actor is None or e["actor"] == actor], default=str)
