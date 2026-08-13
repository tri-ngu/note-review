"""Session-keyed store for the v1 generation pipeline's per-user state
(uploaded Note text, Analyzer checkpoint, generated QuestionSet) — same
lock-guarded-dict pattern as store.py's RoomStore, keyed by the HTTP-only
session cookie (session.py) instead of a Room PIN.

Unlike RoomStore, a session with no entry yet isn't an error case — it's
just a fresh browser session with nothing uploaded, i.e. GET /session's
`status: "empty"`. So get() returns a default SessionState instead of
raising, and mutate() auto-creates one via setdefault.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.models import SessionState


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> SessionState:
        async with self._lock:
            return self._sessions.get(session_id, SessionState())

    @asynccontextmanager
    async def mutate(self, session_id: str) -> AsyncIterator[SessionState]:
        async with self._lock:
            state = self._sessions.setdefault(session_id, SessionState())
            yield state
