"""In-Memory Session-Store für die Zwischenschritte des Import-Wizards. Kein Disk-Persist."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

SESSION_TTL_SECONDS = 2 * 60 * 60


class SessionNotFoundError(Exception):
    pass


@dataclass
class Session:
    created_at: float = field(default_factory=time.time)
    source: Optional[str] = None  # 'upload' | 'example' | 'scenario' -- z.B. fuer die Spenden-Pruefung
    raw_df: Any = None
    parse_meta: dict = field(default_factory=dict)
    hourly_kwh: Any = None
    price_cache: Optional[dict] = None
    price_cache_range: Optional[tuple] = None


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def _cleanup(self) -> None:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now - s.created_at > SESSION_TTL_SECONDS]
        for sid in expired:
            del self._sessions[sid]

    def create(self, source: Optional[str] = None) -> tuple[str, Session]:
        self._cleanup()
        session_id = str(uuid.uuid4())
        session = Session(source=source)
        self._sessions[session_id] = session
        return session_id, session

    def get(self, session_id: str) -> Session:
        self._cleanup()
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError("Session nicht gefunden oder abgelaufen. Bitte CSV erneut hochladen.")
        return session


store = SessionStore()
