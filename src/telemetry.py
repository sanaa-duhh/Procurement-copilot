from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RunTelemetryCounter:
    """Per-run counters. One instance per handle_request call."""

    llm_calls: int = 0
    tool_calls: int = 0
    tool_names: list[str] = field(default_factory=list)
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    rate_limit_retries: int = 0
    rate_limit_wait_ms: float = 0
    stage_latency_ms: dict[str, float] = field(default_factory=dict)
    started: float = field(default_factory=time.perf_counter)

    def record_llm_call(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.llm_calls += 1
        self.record_tokens(input_tokens, output_tokens)

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def record_throttling(self, response) -> None:
        self.rate_limit_retries += response.rate_limit_retries
        self.rate_limit_wait_ms += response.rate_limit_wait_ms

    def record_tool_call(self, name: str) -> None:
        self.tool_calls += 1
        self.tool_names.append(name)

    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    def record_stage(self, name: str, started_at: float) -> None:
        self.stage_latency_ms[name] = round((time.perf_counter() - started_at) * 1000, 1)

    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self.started) * 1000, 1)
