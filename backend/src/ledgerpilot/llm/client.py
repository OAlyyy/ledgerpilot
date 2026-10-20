"""``LLMClient.structured()``: ask a model for JSON matching a Pydantic model.

Two layers of defence against malformed output:

1. **Constrained decoding** where the provider supports it: the JSON schema is
   sent as ``response_format`` and the provider restricts generation to it.
2. **Validate and repair**: the reply is parsed with Pydantic anyway. On failure
   the validation errors are sent back to the model ("your JSON failed because
   ...") and it gets ``max_retries`` more attempts. This catches what (1) cannot:
   providers without schema support, and values that are well-typed but invalid.

Every provider call goes through an on-disk cache keyed by the exact request, so
re-running an eval on unchanged inputs costs no quota.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from ledgerpilot.llm.transport import LiteLLMTransport, Transport, TransportResponse

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


@dataclass
class Usage:
    calls: int = 0
    cached_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0  # list-price equivalent; we may actually be on a free tier
    latency_ms: float = 0.0  # as originally measured, even when served from cache

    def add(self, other: Usage) -> None:
        self.calls += other.calls
        self.cached_calls += other.cached_calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cost_usd += other.cost_usd
        self.latency_ms += other.latency_ms


@dataclass
class StructuredResult[T: BaseModel]:
    value: T
    attempts: int
    usage: Usage
    errors: list[str] = field(default_factory=list)  # validation errors from failed attempts


class StructuredOutputError(Exception):
    def __init__(self, errors: list[str], last_output: str, usage: Usage) -> None:
        super().__init__(f"no valid output after {len(errors)} attempts: {errors[-1][:300]}")
        self.errors = errors
        self.last_output = last_output
        self.usage = usage


class LLMClient:
    def __init__(
        self,
        model: str,
        transport: Transport | None = None,
        *,
        max_retries: int = 2,
        cache_dir: Path | None = None,
        min_interval_s: float = 0.0,
        native_schema: bool = True,
    ) -> None:
        self.model = model
        self.transport = transport or LiteLLMTransport()
        self.max_retries = max_retries
        self.cache_dir = cache_dir
        self.min_interval_s = min_interval_s
        self.native_schema = native_schema
        self._last_call = 0.0

    # ------------------------------------------------------------------ public

    def structured[T: BaseModel](
        self,
        schema: type[T],
        *,
        system: str,
        user: str,
        images: list[bytes] | None = None,
    ) -> StructuredResult[T]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": _user_content(user, images or [])},
        ]
        response_format = self._response_format(schema)
        usage = Usage()
        errors: list[str] = []
        output = ""
        for attempt in range(1, self.max_retries + 2):
            resp, call_usage = self._call(messages, response_format)
            usage.add(call_usage)
            output = resp.content
            try:
                value = schema.model_validate_json(_strip_fences(output))
                return StructuredResult(value=value, attempts=attempt, usage=usage, errors=errors)
            except ValidationError as e:
                problems = _summarise(e)
                errors.append(problems)
                messages += [
                    {"role": "assistant", "content": output},
                    {
                        "role": "user",
                        "content": (
                            "Your reply did not match the required JSON schema:\n"
                            f"{problems}\n"
                            "Reply again with the complete, corrected JSON object only."
                        ),
                    },
                ]
        raise StructuredOutputError(errors, output, usage)

    # ----------------------------------------------------------------- private

    def _response_format(self, schema: type[BaseModel]) -> dict[str, Any]:
        if not self.native_schema:
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
        }

    def _call(
        self, messages: list[dict[str, Any]], response_format: dict[str, Any]
    ) -> tuple[TransportResponse, Usage]:
        key = _cache_key(self.model, messages, response_format)
        cached = self._cache_get(key)
        if cached is not None:
            resp = TransportResponse(**cached["response"])
            return resp, Usage(
                calls=1,
                cached_calls=1,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cost_usd=resp.cost_usd or 0.0,
                latency_ms=cached["latency_ms"],
            )

        wait = self.min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:  # stay under free-tier requests-per-minute limits
            time.sleep(wait)
        start = time.monotonic()
        resp = self.transport(model=self.model, messages=messages, response_format=response_format)
        self._last_call = time.monotonic()
        latency_ms = (self._last_call - start) * 1000
        self._cache_put(key, {"response": resp.__dict__, "latency_ms": latency_ms})
        return resp, Usage(
            calls=1,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_usd=resp.cost_usd or 0.0,
            latency_ms=latency_ms,
        )

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / key[:2] / f"{key}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def _cache_put(self, key: str, value: dict[str, Any]) -> None:
        if self.cache_dir is None:
            return
        path = self.cache_dir / key[:2] / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))


def _user_content(text: str, images: list[bytes]) -> str | list[dict[str, Any]]:
    if not images:
        return text
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for img in images:
        b64 = base64.b64encode(img).decode()
        parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    return parts


def _cache_key(model: str, messages: list[dict[str, Any]], response_format: dict[str, Any]) -> str:
    blob = json.dumps({"model": model, "messages": messages, "format": response_format}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def _strip_fences(text: str) -> str:
    """Some models wrap JSON in ```json fences even in JSON mode."""
    return _FENCE.sub("", text.strip())


def _summarise(e: ValidationError, limit: int = 8) -> str:
    lines = [
        f"- {'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}" for err in e.errors()[:limit]
    ]
    if e.error_count() > limit:
        lines.append(f"- ... and {e.error_count() - limit} more")
    return "\n".join(lines)
