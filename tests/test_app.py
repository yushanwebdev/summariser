from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.store import store


@pytest.fixture(autouse=True)
def _clean_store():
    store._sessions.clear()
    yield
    store._sessions.clear()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        main,
        "settings",
        replace(settings, openrouter_api_key="test-openrouter", firecrawl_api_key="test-fc"),
    )
    return TestClient(main.app)


def test_health_reports_keys(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["keys"] == {"openrouter": True, "firecrawl": True}
    assert body["models"]["summariser"] == "scaledown/summarize"


def test_ingest_rejects_bad_url(client):
    response = client.post("/api/ingest", json={"url": "not-a-url"})
    assert response.status_code == 400


def test_ingest_requires_keys(monkeypatch):
    monkeypatch.setattr(main, "settings", replace(settings, openrouter_api_key="", firecrawl_api_key=""))
    response = TestClient(main.app).post("/api/ingest", json={"url": "https://example.com"})
    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]


def test_ingest_then_chat(client, monkeypatch):
    async def fake_scrape(url: str) -> dict:
        return {
            "url": url,
            "title": "A page",
            "description": "",
            "markdown": "# A page\n\nBody text about widgets.",
        }

    async def fake_summarise(markdown: str, title: str, url: str) -> dict:
        assert "widgets" in markdown
        return {
            "summary": "## Overview\n\nA summary about widgets.",
            "mode": "crew",
        }

    async def fake_chat(messages, **kwargs):
        assert "Body text about widgets." in messages[0]["content"]
        assert messages[-1] == {"role": "user", "content": "What is it about?"}
        return {"content": "It is about widgets.", "model": "test/model", "provider": "test"}

    async def fake_groundedness(question, answer, source):
        return {"confidence": 0.91, "label": "grounded", "model": "baseten/mammoth-1"}

    monkeypatch.setattr(main, "scrape_markdown", fake_scrape)
    monkeypatch.setattr(main, "summarise", fake_summarise)
    monkeypatch.setattr(main, "chat_with_model", fake_chat)
    monkeypatch.setattr(main, "groundedness", fake_groundedness)

    ingest = client.post("/api/ingest", json={"url": "https://example.com/page"})
    assert ingest.status_code == 200
    data = ingest.json()
    assert data["title"] == "A page"
    assert data["mode"] == "crew"
    assert data["source_chars"] == len(data["markdown"])

    chat = client.post(
        "/api/chat", json={"session_id": data["session_id"], "message": "What is it about?"}
    )
    assert chat.status_code == 200
    assert chat.json()["answer"] == "It is about widgets."
    assert chat.json()["grounded"]["confidence"] == 0.91
    assert chat.json()["model"] == "test/model"


def test_chat_rate_limit_is_not_502(client, monkeypatch):
    async def fake_scrape(url: str) -> dict:
        return {"url": url, "title": "T", "description": "", "markdown": "Body"}

    async def fake_summarise(markdown: str, title: str, url: str) -> dict:
        return {"summary": "S", "mode": "crew"}

    async def fake_chat(messages, **kwargs):
        raise main.LLMError("All models rate-limited", 429)

    monkeypatch.setattr(main, "scrape_markdown", fake_scrape)
    monkeypatch.setattr(main, "summarise", fake_summarise)
    monkeypatch.setattr(main, "chat_with_model", fake_chat)

    session = client.post("/api/ingest", json={"url": "https://example.com"}).json()
    response = client.post("/api/chat", json={"session_id": session["session_id"], "message": "hi"})
    assert response.status_code == 429


def test_chat_unknown_session(client):
    response = client.post("/api/chat", json={"session_id": "missing", "message": "hi"})
    assert response.status_code == 404
