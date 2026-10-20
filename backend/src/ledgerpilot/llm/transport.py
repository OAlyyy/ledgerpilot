"""The only module that talks to a model provider.

Everything above it (retries on bad JSON, caching, budgets, tracing) is ours and
provider-independent. Swapping LiteLLM for direct SDK calls means rewriting this
file and nothing else. Tests replace it with a scripted fake.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransportResponse:
    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None  # list price; None if the provider/model has no published price


class Transport(Protocol):
    def __call__(
        self, *, model: str, messages: list[dict[str, Any]], response_format: dict[str, Any] | None
    ) -> TransportResponse: ...


class LiteLLMTransport:
    """LiteLLM call with backoff on rate limits and transient overloads.

    Free tiers return HTTP 429 (quota) and 503 (overloaded) often; both are worth
    waiting for. Anything else (bad request, auth) fails immediately.
    """

    def __init__(self, max_attempts: int = 6, base_delay_s: float = 2.0, **completion_kwargs: Any) -> None:
        self.max_attempts = max_attempts
        self.base_delay_s = base_delay_s
        self.completion_kwargs = completion_kwargs

    def __call__(
        self, *, model: str, messages: list[dict[str, Any]], response_format: dict[str, Any] | None
    ) -> TransportResponse:
        import litellm  # heavy import; keep it out of module import time

        litellm.suppress_debug_info = True
        retryable = (litellm.RateLimitError, litellm.ServiceUnavailableError, litellm.InternalServerError)
        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = litellm.completion(
                    model=model, messages=messages, response_format=response_format, **self.completion_kwargs
                )
                break
            except retryable as e:
                if attempt == self.max_attempts:
                    raise
                delay = self.base_delay_s * 2 ** (attempt - 1)
                log.warning("%s from %s, retrying in %.0fs", type(e).__name__, model, delay)
                time.sleep(delay)

        try:
            cost: float | None = float(litellm.completion_cost(completion_response=resp))
        except Exception:  # unknown model in LiteLLM's price table
            cost = None
        usage = resp.usage
        return TransportResponse(
            content=resp.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_usd=cost,
        )
