from __future__ import annotations

import httpx

from .config import settings


class FirecrawlError(RuntimeError):
    pass


async def scrape_markdown(url: str) -> dict:
    """Scrape a URL with Firecrawl and return markdown plus metadata."""
    payload = {
        "url": url,
        "formats": ["markdown"],
        "onlyMainContent": True,
        "removeBase64Images": True,
        "timeout": 60_000,
    }
    headers = {
        "Authorization": f"Bearer {settings.firecrawl_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=90) as client:
        try:
            response = await client.post(
                f"{settings.firecrawl_base_url}/scrape", json=payload, headers=headers
            )
        except httpx.HTTPError as exc:
            raise FirecrawlError(f"Could not reach Firecrawl: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise FirecrawlError(f"Firecrawl returned non-JSON ({response.status_code})") from exc

    if response.status_code >= 400 or not body.get("success", False):
        message = body.get("error") or f"Firecrawl error {response.status_code}"
        raise FirecrawlError(str(message))

    data = body.get("data") or {}
    markdown = (data.get("markdown") or "").strip()
    if not markdown:
        raise FirecrawlError("Firecrawl returned an empty page")

    meta = data.get("metadata") or {}
    return {
        "url": url,
        "title": (meta.get("title") or url).strip(),
        "description": (meta.get("description") or "").strip(),
        "markdown": markdown[: settings.max_source_chars],
    }
