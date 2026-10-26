from dataclasses import replace

import pytest

from app import llm
from app.config import settings


@pytest.mark.asyncio
async def test_falls_back_when_primary_fails(monkeypatch):
    monkeypatch.setattr(
        llm, "settings", replace(settings, chat_model="primary", chat_models=("primary", "backup"))
    )
    tried = []

    async def fake_once(messages, *, model, **kwargs):
        tried.append(model)
        if model == "primary":
            raise llm.LLMError("temporarily rate-limited", 429)
        return {"content": "ok", "model": "backup-v2", "provider": "test"}

    monkeypatch.setattr(llm, "_chat_once", fake_once)

    result = await llm.chat_with_model([{"role": "user", "content": "hi"}])
    assert result["content"] == "ok"
    assert result["model"] == "backup-v2"
    assert tried == ["primary", "backup"]


@pytest.mark.asyncio
async def test_auth_failure_stops_the_chain(monkeypatch):
    monkeypatch.setattr(
        llm, "settings", replace(settings, chat_model="primary", chat_models=("primary", "backup"))
    )
    tried = []

    async def fake_once(messages, *, model, **kwargs):
        tried.append(model)
        raise llm.LLMError("missing key", 401)

    monkeypatch.setattr(llm, "_chat_once", fake_once)

    with pytest.raises(llm.LLMError) as excinfo:
        await llm.chat_with_model([{"role": "user", "content": "hi"}])
    assert excinfo.value.status_code == 401
    assert tried == ["primary"]


@pytest.mark.asyncio
async def test_all_rate_limited_raises_429(monkeypatch):
    monkeypatch.setattr(
        llm, "settings", replace(settings, chat_model="a", chat_models=("a", "b"))
    )

    async def fake_once(messages, *, model, **kwargs):
        raise llm.LLMError("rate-limited", 429)

    monkeypatch.setattr(llm, "_chat_once", fake_once)

    with pytest.raises(llm.LLMError) as excinfo:
        await llm.chat_with_model([{"role": "user", "content": "hi"}])
    assert excinfo.value.status_code == 429


def test_model_chain_dedupes_and_keeps_order(monkeypatch):
    monkeypatch.setattr(
        llm,
        "settings",
        replace(settings, chat_model="a", chat_models=("a", "b", "a", " ")),
    )
    assert llm.model_chain() == ("a", "b")
    assert llm.model_chain("explicit") == ("explicit",)


@pytest.mark.asyncio
async def test_empty_output_retries_with_more_tokens(monkeypatch):
    monkeypatch.setattr(
        llm, "settings", replace(settings, chat_model="reasoner", chat_models=("reasoner",))
    )
    calls = []

    async def fake_once(messages, *, model, max_tokens, **kwargs):
        calls.append(max_tokens)
        if len(calls) == 1:
            raise llm.EmptyOutputError("reasoner returned no text (length)")
        return {"content": "answer", "model": model, "provider": "test"}

    monkeypatch.setattr(llm, "_chat_once", fake_once)

    result = await llm.chat_with_model([{"role": "user", "content": "hi"}], max_tokens=1200)
    assert result["content"] == "answer"
    assert calls == [1200, 3600]
