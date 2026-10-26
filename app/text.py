from __future__ import annotations

import html
import re

WORD_RE = re.compile(r"[a-z0-9][a-z0-9'-]+")
WORDS = re.compile(r"[A-Za-z0-9\u00c0-\u024f]+")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
BLOCK_BREAK = re.compile(
    r"<br\s*/?>|</(p|div|li|tr|h[1-6]|blockquote|section|article)>", re.IGNORECASE
)
HTML_TAG = re.compile(r"<[^>]+>")
IMAGE_MD = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_MD = re.compile(r"\[([^\]]+)\]\([^)]+\)")

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does", "for",
    "from", "has", "have", "he", "her", "his", "how", "in", "is", "it", "its",
    "of", "on", "or", "she", "that", "the", "their", "them", "there", "these",
    "they", "this", "to", "was", "were", "what", "when", "where", "which", "who",
    "why", "will", "with", "you", "your", "say", "says", "said", "about",
    "tell", "explain", "explains", "article", "author", "text", "mention",
    "mentions", "discuss", "discusses", "describe", "describes", "mean", "means",
}


def _terms(text: str) -> set[str]:
    return {w for w in WORD_RE.findall(text.lower()) if len(w) > 2 and w not in STOP_WORDS}


def parse_text(text: str) -> str:
    """Turn scraped markdown into readable prose without changing its meaning."""
    text = BLOCK_BREAK.sub("\n", text)
    text = IMAGE_MD.sub(" ", text)
    text = LINK_MD.sub(r"\1", text)
    text = HTML_TAG.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _chunks(text: str, target: int = 900) -> list[str]:
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    if len(sentences) <= 1:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        sentences = lines or [text]

    chunks: list[str] = []
    buffer = ""
    for sentence in sentences:
        if buffer and len(buffer) + len(sentence) > target:
            chunks.append(buffer)
            buffer = sentence
        else:
            buffer = f"{buffer} {sentence}".strip()
    if buffer:
        chunks.append(buffer)
    return chunks


def relevant_excerpt(question: str, markdown: str, limit: int = 10_000) -> str:
    """Pick passages that lexically overlap the question, preserving source order."""
    text = parse_text(markdown)
    if not text:
        return ""
    if len(text) <= limit:
        return text

    target = max(80, min(900, limit // 4))
    chunks = _chunks(text, target=target)
    wanted = _terms(question)
    scored = [
        (len(wanted & _terms(chunk)), index, chunk)
        for index, chunk in enumerate(chunks)
        if wanted & _terms(chunk)
    ]
    if not scored:
        return text[:limit]

    chosen: list[tuple[int, str]] = []
    used = 0
    for _, index, chunk in sorted(scored, key=lambda item: (-item[0], item[1])):
        if used + len(chunk) > limit:
            continue
        chosen.append((index, chunk))
        used += len(chunk)
        if used >= limit * 0.8:
            break

    if not chosen:
        return text[:limit]

    chosen.sort()
    return "\n\n".join(chunk for _, chunk in chosen)


def source_context(question: str, markdown: str, limit: int) -> str:
    """Return the whole source when it fits, otherwise the opening plus relevant passages."""
    text = parse_text(markdown)
    if len(text) <= limit:
        return text

    return (
        f"{text[: limit // 3]}\n\n[...]\n\n"
        f"PASSAGES MOST RELEVANT TO THE QUESTION:\n{relevant_excerpt(question, text, limit=limit - limit // 3)}"
    )
