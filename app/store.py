from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .config import settings


@dataclass
class Session:
    id: str
    url: str
    title: str
    markdown: str
    chat_context: str
    summary: str
    mode: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    history: list[dict] = field(default_factory=list)

    def touched(self) -> None:
        self.created_at = datetime.now(timezone.utc)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def _prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.session_ttl_minutes)
        for key in [k for k, s in self._sessions.items() if s.created_at < cutoff]:
            self._sessions.pop(key, None)

    def create(
        self,
        *,
        url: str,
        title: str,
        markdown: str,
        chat_context: str,
        summary: str,
        mode: str,
    ) -> Session:
        self._prune()
        session = Session(
            id=secrets.token_urlsafe(12),
            url=url,
            title=title,
            markdown=markdown,
            chat_context=chat_context,
            summary=summary,
            mode=mode,
        )
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        self._prune()
        session = self._sessions.get(session_id)
        if session:
            session.touched()
        return session


store = SessionStore()
