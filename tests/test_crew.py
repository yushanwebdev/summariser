import pytest

from app import crew


def test_prompt_adapts_to_short_sources():
    prompt = crew._summary_prompt("short text", "T", "https://x")
    assert "This source is short" in prompt
    assert "Do not pad" in prompt


def test_prompt_asks_for_detail_on_long_sources():
    prompt = crew._summary_prompt("word " * 5000, "T", "https://x")
    assert "300-400 words" in prompt
    assert "6-8 bullets" in prompt


@pytest.mark.asyncio
async def test_summarise_passes_the_full_markdown(monkeypatch):
    captured = {}

    def fake_crew(source, title, url):
        captured["source"] = source
        return "## Overview\n\nA summary."

    monkeypatch.setattr(crew, "_run_crew", fake_crew)
    raw = "| ![logo](x) | [home](y) |\n| --- |\n| Raw article text. |"
    result = await crew.summarise(raw, "T", "https://x")
    assert captured["source"] == raw
    assert result["mode"] == "crew"
