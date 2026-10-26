from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _chat_models() -> tuple[str, ...]:
    primary = os.getenv("CHAT_MODEL", "google/gemma-4-31b-it:free")
    fallbacks = os.getenv(
        "CHAT_FALLBACK_MODELS", (
            "poolside/laguna-s-2.1:free,dots-studio/dots-3-note-preview:free,"
            "recursive/flint-v1.0:free,cohere/north-mini-code:free,openrouter/free"
        )
    )
    seen: list[str] = []
    for name in [primary, *fallbacks.split(",")]:
        name = name.strip()
        if name and name not in seen:
            seen.append(name)
    return tuple(seen)


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    firecrawl_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    firecrawl_base_url: str = "https://api.firecrawl.dev/v2"
    summariser_model: str = os.getenv("SUMMARISER_MODEL", "scaledown/summarize")
    chat_model: str = os.getenv("CHAT_MODEL", "google/gemma-4-31b-it:free")
    chat_models: tuple[str, ...] = ()
    mammoth_model: str = os.getenv("MAMMOTH_MODEL", "baseten/mammoth-1:free")
    mammoth_confidence: bool = os.getenv("MAMMOTH_CONFIDENCE", "1") != "0"
    max_source_chars: int = _int("MAX_SOURCE_CHARS", 200_000)
    chat_context_chars: int = _int("CHAT_CONTEXT_CHARS", 120_000)
    session_ttl_minutes: int = _int("SESSION_TTL_MINUTES", 180)


def load_settings() -> Settings:
    return Settings(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        firecrawl_api_key=os.getenv("FIRECRAWL_API_KEY", ""),
        chat_models=_chat_models(),
    )


settings = load_settings()
