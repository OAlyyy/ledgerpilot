"""Scripted stand-in for a model provider: deterministic, free, offline."""

from __future__ import annotations

from typing import Any

from ledgerpilot.llm import TransportResponse


class ScriptedTransport:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, *, model: str, messages: list[dict[str, Any]], response_format: Any
    ) -> TransportResponse:
        self.calls.append({"model": model, "messages": messages, "response_format": response_format})
        if not self.replies:
            raise AssertionError("model called more often than scripted")
        return TransportResponse(
            content=self.replies.pop(0), input_tokens=100, output_tokens=50, cost_usd=0.001
        )
