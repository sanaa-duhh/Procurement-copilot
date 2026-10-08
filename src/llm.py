"""Model-provider adapter.

One small interface (`LLMClient.create`) so the agents never touch an SDK directly.
`OpenAIClient` is the only live provider; `MockClient` is a scripted stand-in used by
the test-suite and by `LLM_PROVIDER=mock` so the product runs without credentials.
Mock runs are never reported as evaluation results.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_MODEL = "gpt-6-astra"


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    assistant_content: Any          # passed back verbatim as the assistant turn
    input_tokens: int = 0
    output_tokens: int = 0
    rate_limit_retries: int = 0
    rate_limit_wait_ms: float = 0
    response_id: str | None = None
    response_model: str | None = None


class LLMError(RuntimeError):
    """The model could not produce a usable turn (auth, refusal, truncation, network)."""

    def __init__(self, message: str, *, rate_limit_retries=0, rate_limit_wait_ms=0):
        super().__init__(message)
        self.rate_limit_retries = rate_limit_retries
        self.rate_limit_wait_ms = rate_limit_wait_ms


class LLMClient(Protocol):
    model: str

    def create(self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None,
               output_schema: dict[str, Any] | None, max_tokens: int) -> LLMTurn: ...


# --------------------------------------------------------------------------
# Scripted mock (offline runs and tests)
# --------------------------------------------------------------------------

@dataclass
class MockClient:
    """Calls every tool once, then writes a draft straight from the policy-engine output.

    It exists so the pipeline, UI and tests run without a key. It is deliberately
    naive: it never exercises judgement, so it is not used for reported results.
    """

    model: str = "mock"
    calls: int = field(default=0)

    def create(self, *, system, messages, tools, output_schema, max_tokens=8000) -> LLMTurn:
        self.calls += 1
        request = _find_request(messages)
        if tools and not _has_tool_results(messages):
            calls = _scripted_tool_calls(request, tools)
            content = [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in calls]
            return LLMTurn(text="", tool_calls=calls, stop_reason="tool_use", assistant_content=content, input_tokens=0, output_tokens=0)
        policy = _find_policy_result(messages)
        schema_props = set((output_schema or {}).get("properties", {}))
        if "facts" in schema_props:   # analyst stage
            pack = {
                "request_summary": f"{request.get('product_name')} from {request.get('vendor_name')} for {request.get('user_count')} users at ${request.get('annual_cost_usd')}/yr.",
                "facts": policy.get("evidence", [])[:6],
                "uncertainties": policy.get("missing_information", []),
                "overlap_assessment": f"overlap kind: {policy.get('overlap_kind')}",
                "untrusted_text_observations": "instruction-like text present" if policy.get("prompt_injection", {}).get("detected") else "none",
            }
            return LLMTurn(text=json.dumps(pack), tool_calls=[], stop_reason="end_turn", assistant_content=[{"type": "text", "text": json.dumps(pack)}])
        draft = {
            "request_summary": f"{request.get('product_name')} from {request.get('vendor_name')}.",
            "recommendation": f"{policy.get('preferred_next_action', 'route_for_reviews').replace('_', ' ').capitalize()} (mock draft).",
            "next_action": policy.get("preferred_next_action", "route_for_reviews"),
            "rationale": "Scripted mock: mirrors the deterministic policy engine without judgement.",
            "evidence": policy.get("evidence", [])[:4],
            "required_approvals": policy.get("required_approvals", []),
            "missing_information": policy.get("missing_information", []),
            "risk_flags": policy.get("risk_flags", []),
            "next_step": "Mock next step: hand the evidence package to the named human reviewers.",
            "prompt_injection_detected": bool(policy.get("prompt_injection", {}).get("detected")),
        }
        text = json.dumps(draft)
        return LLMTurn(text=text, tool_calls=[], stop_reason="end_turn", assistant_content=[{"type": "text", "text": text}])


def _has_tool_results(messages: list[dict[str, Any]]) -> bool:
    for m in messages:
        content = m.get("content")
        if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return True
    return False


def _find_request(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for m in messages:
        content = m.get("content")
        text = content if isinstance(content, str) else " ".join(b.get("text", "") for b in content if isinstance(b, dict))
        match = re.search(r"<purchase_request[^>]*>\s*(\{.*?\})\s*</purchase_request>", text, flags=re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    return {}


def _find_policy_result(messages: list[dict[str, Any]]) -> dict[str, Any]:
    # Reviewer stage: the raw tool outputs are embedded as a JSON list inside a tagged block.
    for m in reversed(messages):
        content = m.get("content")
        if isinstance(content, str):
            match = re.search(r"<raw_tool_outputs>\s*(\[.*\])\s*</raw_tool_outputs>", content, flags=re.S)
            if match:
                try:
                    for entry in json.loads(match.group(1)):
                        if isinstance(entry.get("result"), dict) and "preferred_next_action" in entry["result"]:
                            return entry["result"]
                except (json.JSONDecodeError, AttributeError):
                    pass
    for m in reversed(messages):
        content = m.get("content")
        blobs: list[str] = []
        if isinstance(content, str):
            blobs.append(content)
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    blobs.append(b.get("content") if isinstance(b.get("content"), str) else json.dumps(b.get("content")))
                elif isinstance(b, dict) and b.get("type") == "text":
                    blobs.append(b.get("text", ""))
        for blob in blobs:
            for candidate in re.findall(r"\{.*\}", blob, flags=re.S):
                try:
                    data = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict) and "preferred_next_action" in data:
                    return data
                if isinstance(data, dict):
                    for v in data.values():
                        if isinstance(v, dict) and "preferred_next_action" in v:
                            return v
    return {}


def _scripted_tool_calls(request: dict[str, Any], tools: list[dict[str, Any]]) -> list[ToolCall]:
    names = {t["name"] for t in tools}
    args = {
        "get_requester_profile": {"employee_id": str(request.get("requester_id") or "")},
        "check_budget": {"department": "", "annual_cost_usd": request.get("annual_cost_usd") if request.get("annual_cost_usd") is not None else 0},
        "search_software_catalog": {"product_name": str(request.get("product_name") or ""), "vendor_name": str(request.get("vendor_name") or ""), "category": str(request.get("category") or "")},
        "get_vendor_registry_record": {"vendor_name": str(request.get("vendor_name") or "")},
        "get_vendor_risk_assessment": {"vendor_name": str(request.get("vendor_name") or "")},
        "get_purchase_history": {"vendor_name": str(request.get("vendor_name") or ""), "department": ""},
        "run_policy_checks": {"request_id": str(request.get("request_id") or "")},
    }
    return [ToolCall(id=f"mock-{i}", name=name, input=args[name]) for i, name in enumerate(args) if name in names]


# --------------------------------------------------------------------------
# Factory and JSON helpers
# --------------------------------------------------------------------------

def get_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider == "mock":
        return MockClient()
    if provider == "openai":
        from src.openai_client import OpenAIClient
        return OpenAIClient()
    raise LLMError(f"unsupported LLM_PROVIDER '{provider}' (use 'openai' or the offline 'mock' fixture)")


def configured_model(provider: str) -> str:
    return "scripted mock" if provider == "mock" else os.getenv("MODEL_NAME") or DEFAULT_MODEL


def extract_json(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from model text, tolerating code fences and surrounding prose."""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    while start != -1:
        try:
            data, _ = json.JSONDecoder().raw_decode(cleaned[start:])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        start = cleaned.find("{", start + 1)
    return None
