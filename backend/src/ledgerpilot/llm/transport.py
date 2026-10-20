"""The only module that talks to a model provider.

Everything above it (retries on bad JSON, caching, budgets, tracing) is ours and
provider-independent. Swapping LiteLLM for direct SDK calls means rewriting this
file and nothing else. Tests replace it with a scripted fake.
"""

from __future__ import annotations

import logging
import re
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


class QuotaExhaustedError(Exception):
    """The provider says to come back much later (e.g. a daily free-tier quota).

    Retrying in-process is pointless; callers should stop and resume later. The
    response cache makes resuming free for everything already done.
    """

    def __init__(self, model: str, retry_after_s: float | None, detail: str) -> None:
        wait = f"in ~{retry_after_s / 3600:.1f} h" if retry_after_s else "later"
        super().__init__(f"{model}: quota exhausted, retry {wait}. {detail[:200]}")
        self.model = model
        self.retry_after_s = retry_after_s


def retry_after_seconds(message: str) -> float | None:
    """Pull the provider's suggested wait out of an error message, if any."""
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', message)
    if m:
        return float(m.group(1))
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", message)
    if m and any(m.groups()):
        h, mi, sec = (float(g) if g else 0.0 for g in m.groups())
        return h * 3600 + mi * 60 + sec
    return None


class Transport(Protocol):
    def __call__(
        self, *, model: str, messages: list[dict[str, Any]], response_format: dict[str, Any] | None
    ) -> TransportResponse: ...


class LiteLLMTransport:
    """LiteLLM call with backoff on rate limits and transient overloads.

    Free tiers return HTTP 429 (quota) and 503 (overloaded) often; both are worth
    waiting for. Anything else (bad request, auth) fails immediately.
    """

    def __init__(
        self,
        max_attempts: int = 6,
        base_delay_s: float = 2.0,
        max_wait_s: float = 90.0,
        **completion_kwargs: Any,
    ) -> None:
        self.max_attempts = max_attempts
        self.base_delay_s = base_delay_s
        self.max_wait_s = max_wait_s
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
                suggested = retry_after_seconds(str(e))
                if suggested is not None and suggested > self.max_wait_s:
                    raise QuotaExhaustedError(model, suggested, str(e)) from e
                if attempt == self.max_attempts:
                    raise
                delay = max(self.base_delay_s * 2 ** (attempt - 1), suggested or 0)
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
