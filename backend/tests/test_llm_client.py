from __future__ import annotations

import pytest
from fakes import ScriptedTransport
from pydantic import BaseModel, Field

from ledgerpilot.llm import LLMClient, StructuredOutputError


class Thing(BaseModel):
    name: str = Field(max_length=10)
    amount: int


def client(transport: ScriptedTransport, **kw) -> LLMClient:
    return LLMClient("fake/model", transport, **kw)


def test_valid_first_time():
    t = ScriptedTransport(['{"name": "a", "amount": 1}'])
    r = client(t).structured(Thing, system="s", user="u")
    assert r.value == Thing(name="a", amount=1)
    assert r.attempts == 1 and r.usage.calls == 1


def test_native_schema_is_sent():
    t = ScriptedTransport(['{"name": "a", "amount": 1}'])
    client(t).structured(Thing, system="s", user="u")
    fmt = t.calls[0]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["schema"]["title"] == "Thing"


def test_retry_feeds_validation_errors_back():
    t = ScriptedTransport(['{"name": "way too long a name", "amount": "x"}', '{"name": "ok", "amount": 2}'])
    r = client(t).structured(Thing, system="s", user="u")
    assert r.value.amount == 2 and r.attempts == 2
    feedback = t.calls[1]["messages"][-1]["content"]
    assert "name" in feedback and "amount" in feedback  # the model is told exactly what was wrong
    assert t.calls[1]["messages"][-2] == {
        "role": "assistant",
        "content": '{"name": "way too long a name", "amount": "x"}',
    }


def test_broken_json_and_code_fences():
    t = ScriptedTransport(['{"name": "a", ', '```json\n{"name": "a", "amount": 3}\n```'])
    assert client(t).structured(Thing, system="s", user="u").value.amount == 3


def test_gives_up_after_max_retries():
    t = ScriptedTransport(["nope"] * 3)
    with pytest.raises(StructuredOutputError) as exc:
        client(t, max_retries=2).structured(Thing, system="s", user="u")
    assert len(exc.value.errors) == 3 and exc.value.usage.calls == 3


def test_cache_makes_reruns_free(tmp_path):
    t = ScriptedTransport(['{"name": "a", "amount": 1}'])
    first = client(t, cache_dir=tmp_path).structured(Thing, system="s", user="u")
    second = client(ScriptedTransport([]), cache_dir=tmp_path).structured(Thing, system="s", user="u")
    assert first.value == second.value
    assert second.usage.cached_calls == 1
    assert second.usage.latency_ms == first.usage.latency_ms  # original latency is kept for reports


def test_images_become_content_parts():
    t = ScriptedTransport(['{"name": "a", "amount": 1}'])
    client(t).structured(Thing, system="s", user="look", images=[b"\x89PNG fake"])
    parts = t.calls[0]["messages"][1]["content"]
    assert parts[0] == {"type": "text", "text": "look"}
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_daily_quota_is_not_retried():
    from ledgerpilot.llm.transport import retry_after_seconds

    gemini = 'Quota exceeded ... Please retry in 9h23m15.15s.", "retryDelay": "33795s"'
    assert retry_after_seconds(gemini) == 33795
    assert retry_after_seconds("Please retry in 9h23m15.15s.") == 9 * 3600 + 23 * 60 + 15.15
    assert retry_after_seconds("please retry in 12.5s") == 12.5
    assert retry_after_seconds("internal error") is None
