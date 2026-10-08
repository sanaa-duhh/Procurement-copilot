"""OpenAI Responses API with strict tools/output and request-local state.

The shell's OPENAI_API_KEY is used directly. No alternate provider or endpoint
is selected on failure. Reasoning items are carried between tool turns in
memory using encrypted content; response storage is disabled.
"""
import json
import os
import time

from src.llm import DEFAULT_MODEL, LLMError, LLMTurn, ToolCall


class OpenAIClient:
    def __init__(self, model=None, effort=None):
        from openai import OpenAI
        self.model = model or os.getenv("MODEL_NAME") or DEFAULT_MODEL
        self.effort = effort or os.getenv("LLM_EFFORT", "medium")
        self._key_present = bool(os.getenv("OPENAI_API_KEY"))
        self._client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY") or "missing-openai-key",
            base_url="https://api.openai.com/v1", timeout=60.0, max_retries=0,
        )

    @staticmethod
    def response_input(messages):
        items = []
        for message in messages:
            content = message["content"]
            if isinstance(content, str):
                items.append(message)
            elif message["role"] == "assistant":
                # Preserve all response items, including reasoning between calls.
                items.extend(content)
            else:
                for block in content:
                    if block["type"] == "tool_result":
                        items.append({"type": "function_call_output", "call_id": block["tool_use_id"], "output": block["content"]})
                    elif block["type"] == "text":
                        items.append({"role": "user", "content": block["text"]})
        return items

    def create(self, *, system, messages, tools, output_schema, max_tokens):
        from openai import APIConnectionError, APIStatusError
        if not self._key_present:
            raise LLMError("OPENAI_API_KEY is missing from the shell environment or .env")
        kwargs = {
            "model": self.model, "instructions": system, "input": self.response_input(messages),
            "max_output_tokens": max_tokens, "reasoning": {"effort": self.effort},
            "store": False, "include": ["reasoning.encrypted_content"],
        }
        if tools:
            kwargs["tools"] = [{"type": "function", "name": t["name"], "description": t["description"],
                                "parameters": t["input_schema"], "strict": True} for t in tools]
        if output_schema:
            kwargs["text"] = {"format": {"type": "json_schema", "name": "procurement_output", "strict": True, "schema": output_schema}}
        retries, wait_ms = 0, 0.0
        while True:
            try:
                response = self._client.responses.create(**kwargs)
                break
            except APIStatusError as exc:
                retry = exc.response.headers.get("retry-after", "unspecified")
                try:
                    delay = float(retry)
                except ValueError:
                    delay = 0
                if exc.status_code == 429 and retries < 2 and 0 < delay <= 60:
                    time.sleep(delay)
                    retries += 1
                    wait_ms += delay * 1000
                    continue
                raise LLMError(f"OpenAI HTTP {exc.status_code}; retry-after={retry}. Check model access, billing and account limits.",
                               rate_limit_retries=retries, rate_limit_wait_ms=wait_ms) from exc
            except APIConnectionError as exc:
                raise LLMError("OpenAI connection failed or timed out", rate_limit_retries=retries, rate_limit_wait_ms=wait_ms) from exc
        if response.status != "completed":
            reason = getattr(response.incomplete_details, "reason", None) or response.status
            raise LLMError(f"OpenAI response did not complete ({reason})", rate_limit_retries=retries, rate_limit_wait_ms=wait_ms)
        calls = []
        for item in response.output:
            if item.type == "message" and any(part.type == "refusal" for part in item.content):
                raise LLMError("OpenAI refused the request", rate_limit_retries=retries, rate_limit_wait_ms=wait_ms)
            if item.type == "function_call":
                try:
                    args = json.loads(item.arguments)
                    if not isinstance(args, dict):
                        raise ValueError("arguments must be an object")
                except (ValueError, TypeError) as exc:
                    raise LLMError("OpenAI returned invalid tool arguments") from exc
                calls.append(ToolCall(item.call_id, item.name, args))
        usage = response.usage
        return LLMTurn(
            text=response.output_text, tool_calls=calls, stop_reason="tool_use" if calls else "end_turn",
            assistant_content=response.output, input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            rate_limit_retries=retries, rate_limit_wait_ms=wait_ms,
            response_id=response.id, response_model=response.model,
        )
