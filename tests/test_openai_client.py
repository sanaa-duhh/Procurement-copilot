"""Actual OpenAI SDK serialization through an in-memory HTTP transport."""
import json

import httpx
import pytest
from openai import OpenAI

from src.data_access import get_request
from src.llm import LLMError
from src.openai_client import OpenAIClient
from src.solution import handle_request_payload


@pytest.mark.parametrize("architecture", ["single", "staged"])
def test_responses_tool_roundtrip_preserves_reasoning_and_strict_schema(monkeypatch, architecture):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    bodies, policy = [], {}

    def handler(request):
        nonlocal policy
        body = json.loads(request.content)
        bodies.append(body)
        assert request.headers["authorization"] == "Bearer test-openai-key"
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert body["store"] is False
        assert body["include"] == ["reasoning.encrypted_content"]
        assert body["text"]["format"]["strict"] is True
        outputs = [m for m in body["input"] if m.get("type") == "function_call_output"]
        if body.get("tools") and not outputs:
            assert all(t["strict"] and t["type"] == "function" for t in body["tools"])
            output = [
                {"id": "rs_1", "type": "reasoning", "summary": [], "encrypted_content": "test-encrypted-state"},
                {"id": "fc_1", "type": "function_call", "call_id": "call_policy", "name": "run_policy_checks", "arguments": '{"request_id":"REQ-1010"}', "status": "completed"},
            ]
        else:
            if outputs:
                assert outputs[0]["call_id"] == "call_policy"
                assert any(m.get("encrypted_content") == "test-encrypted-state" for m in body["input"])
                policy = json.loads(outputs[0]["output"])
            schema = body["text"]["format"]["schema"]
            if "facts" in schema["properties"]:
                result = {"request_summary": "Training", "facts": policy["evidence"], "uncertainties": [],
                          "overlap_assessment": "No overlap", "untrusted_text_observations": "None"}
            else:
                result = {"request_summary": "Training", "recommendation": "Route", "next_action": policy["preferred_next_action"],
                          "rationale": "Within budget", "evidence": policy["evidence"], "required_approvals": policy["required_approvals"],
                          "missing_information": [], "risk_flags": policy["risk_flags"], "next_step": "Ask Manager", "prompt_injection_detected": False}
            output = [{"id": "msg_1", "type": "message", "role": "assistant", "status": "completed",
                       "content": [{"type": "output_text", "text": json.dumps(result), "annotations": []}]}]
        return httpx.Response(200, json={"id": "resp_test", "object": "response", "created_at": 1,
            "model": "gpt-6-astra", "status": "completed", "output": output,
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}})

    client = OpenAIClient()
    client._client = OpenAI(api_key="test-openai-key", base_url="https://api.openai.com/v1", max_retries=0,
                            http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    decision = handle_request_payload(get_request("REQ-1010"), architecture=architecture, llm=client)
    assert not decision.trace.get("errors")
    assert decision.required_approvals == ["Manager"]
    assert len(bodies) == (2 if architecture == "single" else 3)
    assert decision.telemetry.llm_calls == len(bodies)
    assert decision.telemetry.input_tokens == 10 * len(bodies)
    assert "encrypted_content" not in json.dumps(decision.trace)


def test_no_other_credential_or_endpoint_can_be_used(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "must-not-be-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://another-provider.invalid")
    client = OpenAIClient()
    assert str(client._client.base_url) == "https://api.openai.com/v1/"
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        client.create(system="", messages=[], tools=None, output_schema={}, max_tokens=10)


def test_rate_limit_retries_are_bounded_and_recorded(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    waits, calls = [], []
    monkeypatch.setattr("src.openai_client.time.sleep", waits.append)
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"retry-after": "2"}, json={"error": {"message": "rate limit"}})
    client = OpenAIClient()
    client._client = OpenAI(api_key="test-openai-key", base_url="https://api.openai.com/v1", max_retries=0,
                            http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(LLMError) as error:
        client.create(system="", messages=[], tools=None, output_schema={}, max_tokens=10)
    assert len(calls) == 3
    assert waits == [2, 2]
    assert error.value.rate_limit_retries == 2
    assert error.value.rate_limit_wait_ms == 4000
