from __future__ import annotations

import asyncio
import logging
import re

from .config import settings
from .llm import LLMError, chat

logger = logging.getLogger(__name__)


def _openrouter_llm(model: str, max_tokens: int):
    from crewai import LLM

    return LLM(
        model=f"openrouter/{model}",
        api_key=settings.openrouter_api_key,
        max_tokens=max_tokens,
    )


def _summary_prompt(source: str, title: str, url: str) -> str:
    size = len(source)
    if size < 2_000:
        shape = (
            "This source is short. Write one paragraph of 2-4 sentences that captures "
            "everything it says, then '## Key points' with 2-3 bullets. Do not pad, do "
            "not add background, and do not repeat the same idea in different words."
        )
    elif size < 15_000:
        shape = (
            "Write '## Overview' with 2-3 short paragraphs, 150-250 words in total, "
            "then '## Key points' with 4-6 bullets."
        )
    else:
        shape = (
            "Write '## Overview' with 3-4 short paragraphs, 300-400 words in total, "
            "then '## Key points' with 6-8 bullets."
        )

    return (
        "Using only the article below, write a summary in Markdown.\n\n"
        f"{shape}\n\n"
        "Cover the author's main argument, the concrete advice or findings, the "
        "examples and reasoning behind them, and any important numbers or names. "
        "Preserve the author's meaning and keep specific facts. Do not add outside "
        "knowledge, do not flatter the piece, and do not pad.\n\n"
        f"TITLE: {title}\nURL: {url}\n\n"
        "ARTICLE:\n"
        f"{source}"
    )

def _tidy(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:markdown)?\s*\n(.*)\n```$", r"\1", text, flags=re.DOTALL)
    if text.startswith("# ") and "\n" in text:
        text = text.split("\n", 1)[1].lstrip()
    return text.strip()


def _run_crew(source: str, title: str, url: str) -> str:
    try:
        import litellm

        litellm.drop_params = True
    except Exception:
        pass

    from crewai import Agent, Crew, Process, Task

    summariser = Agent(
        role="Editorial Summariser",
        goal="Produce a detailed, faithful summary of a long-form article.",
        backstory=(
            "You are a careful editor. You extract the author's argument, the "
            "evidence, and the concrete advice, and you never invent facts or "
            "bring in outside knowledge."
        ),
        llm=_openrouter_llm(settings.summariser_model, 4000),
        allow_delegation=False,
        verbose=False,
        max_iter=2,
    )

    summary_task = Task(
        description=_summary_prompt(source, title, url),
        expected_output=(
            "Markdown with an overview proportionate to the source and a "
            "'## Key points' section, without padding."
        ),
        agent=summariser,
    )

    crew = Crew(
        agents=[summariser],
        tasks=[summary_task],
        process=Process.sequential,
        verbose=False,
        memory=False,
    )
    result = crew.kickoff()
    return _tidy(str(getattr(result, "raw", result)))


async def summarise(raw_markdown: str, title: str, url: str) -> dict:
    """Send the scraped markdown to the crew; fall back to a direct ScaleDown call."""
    source = raw_markdown

    try:
        summary = await asyncio.to_thread(_run_crew, source, title, url)
        if summary:
            return {"summary": summary, "mode": "crew"}
    except Exception as exc:
        logger.warning("crewAI run failed, using direct summariser: %s", exc)

    try:
        summary = await chat(
            [{"role": "user", "content": _summary_prompt(source, title, url)}],
            model=settings.summariser_model,
            max_tokens=4000,
            temperature=None,
            timeout=240,
        )
        return {"summary": _tidy(summary), "mode": "direct"}
    except LLMError as exc:
        raise LLMError(f"Summarisation failed: {exc}") from exc
