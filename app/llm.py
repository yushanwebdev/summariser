from __future__ import annotations

import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
FATAL_CODES = {401, 402}


class LLMError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class EmptyOutputError(LLMError):
    pass


def model_chain(model: str | None = None) -> tuple[str, ...]:
    if model:
        return (model,)
    chain = settings.chat_models or (settings.chat_model,)
    return tuple(dict.fromkeys(name.strip() for name in chain if name.strip()))


def _error_code(body: dict, response: httpx.Response) -> int | None:
    error = body.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, (int, float)):
            return int(code)
    return response.status_code or None


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Summariser",
    }


async def _chat_once(
    messages: list[dict],
    *,
    model: str,
    max_tokens: int,
    temperature: float | None,
    timeout: float,
) -> dict:
    payload: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None:
        payload["temperature"] = temperature

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=_headers(),
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach OpenRouter: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise LLMError(f"OpenRouter returned non-JSON ({response.status_code})") from exc

    if not isinstance(body, dict):
        raise LLMError(f"Unexpected OpenRouter response ({response.status_code})")

    if response.status_code >= 400 or "error" in body:
        error = body.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise LLMError(
            message or f"OpenRouter error {response.status_code}",
            _error_code(body, response),
        )

    choices = body.get("choices") or []
    message = (choices[0] if choices else {}).get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        finish = (choices[0] if choices else {}).get("finish_reason") or "empty"
        actual = body.get("model") or model
        raise EmptyOutputError(f"{actual} returned no text ({finish})")

    return {
        "content": content,
        "model": body.get("model") or model,
        "provider": body.get("provider"),
    }


async def chat_with_model(
    messages: list[dict],
    *,
    model: str | None = None,
    max_tokens: int = 1200,
    temperature: float | None = 0.3,
    timeout: float = 120,
) -> dict:
    """Try the configured models in order until one returns text."""
    chain = model_chain(model)
    failures: list[tuple[str, LLMError]] = []

    for candidate in chain:
        try:
            try:
                result = await _chat_once(
                    messages,
                    model=candidate,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                )
            except EmptyOutputError:
                logger.warning("%s used its budget on reasoning; retrying with more tokens", candidate)
                result = await _chat_once(
                    messages,
                    model=candidate,
                    max_tokens=min(max_tokens * 3, 4000),
                    temperature=temperature,
                    timeout=timeout,
                )
            if failures:
                logger.warning(
                    "Fell back to %s after %s",
                    result["model"],
                    ", ".join(name for name, _ in failures),
                )
            return result
        except LLMError as exc:
            failures.append((candidate, exc))
            logger.warning("Model %s failed: %s", candidate, exc)
            if exc.status_code in FATAL_CODES:
                break

    rate_limited = any(exc.status_code == 429 for _, exc in failures)
    detail = "; ".join(f"{name}: {exc}" for name, exc in failures[-3:])
    raise LLMError(
        f"No model answered ({len(failures)} tried). {detail}",
        429 if rate_limited else (failures[-1][1].status_code if failures else None),
    )


async def chat(
    messages: list[dict],
    *,
    model: str | None = None,
    max_tokens: int = 1200,
    temperature: float | None = 0.3,
    timeout: float = 120,
) -> str:
    result = await chat_with_model(
        messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    return result["content"]


async def groundedness(question: str, answer: str, source: str) -> dict | None:
    """Ask mammoth-1 (a decision model) how well the source supports the answer."""
    payload = {
        "model": settings.mammoth_model,
        "state": {
            "user_question": question,
            "assistant_answer": answer,
            "source_excerpt": source[:12_000],
        },
        "questions": {
            "supported": {
                "type": "noul",
                "instructions": (
                    "Is the assistant's answer fully supported by the source excerpt, "
                    "without unsupported claims?"
                ),
                "criteria": {
                    "true": "Every substantive claim in the answer is stated in or directly inferable from the source.",
                    "false": "The answer adds claims the source does not support, or contradicts it.",
                },
            }
        },
    }

    async with httpx.AsyncClient(timeout=45) as client:
        try:
            response = await client.post(DECISIONS_URL, json=payload, headers=_headers())
            body = response.json()
        except (httpx.HTTPError, ValueError):
            return None

    if response.status_code >= 400 or "answers" not in body:
        return None

    try:
        confidence = float(body["answers"]["supported"]["noul"])
    except (KeyError, TypeError, ValueError):
        return None

    if confidence >= 0.8:
        label = "grounded"
    elif confidence >= 0.55:
        label = "partly grounded"
    else:
        label = "weakly grounded"

    return {
        "confidence": round(confidence, 2),
        "label": label,
        "model": body.get("model", settings.mammoth_model),
    }
