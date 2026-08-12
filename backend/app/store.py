import asyncio
import random
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.models import QuestionSet, RoomState


class RoomNotFoundError(Exception):
    def __init__(self, pin: str):
        super().__init__(f"no Room found for PIN {pin!r}")
        self.pin = pin


class RoomStore:
    def __init__(self) -> None:
        self._rooms: dict[str, RoomState] = {}
        self._lock = asyncio.Lock()

    def _random_pin(self) -> str:
        return f"{random.randint(0, 9999):04d}"

    async def create_room(
        self, host_session_id: str, question_set: QuestionSet, now: float | None = None
    ) -> RoomState:
        created_at = now if now is not None else time.monotonic()
        async with self._lock:
            pin = self._random_pin()
            while pin in self._rooms:
                pin = self._random_pin()
            room = RoomState(
                pin=pin,
                host_session_id=host_session_id,
                question_set=question_set,
                created_at=created_at,
            )
            self._rooms[pin] = room
            return room

    async def get(self, pin: str) -> RoomState:
        async with self._lock:
            room = self._rooms.get(pin)
            if room is None:
                raise RoomNotFoundError(pin)
            return room

    @asynccontextmanager
    async def mutate(self, pin: str) -> AsyncIterator[RoomState]:
        async with self._lock:
            room = self._rooms.get(pin)
            if room is None:
                raise RoomNotFoundError(pin)
            yield room

    async def delete(self, pin: str) -> None:
        async with self._lock:
            self._rooms.pop(pin, None)

    async def sweep_expired(self, ttl_seconds: float = 300.0, now: float | None = None) -> list[RoomState]:
        current = now if now is not None else time.monotonic()
        evicted: list[RoomState] = []
        async with self._lock:
            for pin, room in list(self._rooms.items()):
                expired = (
                    room.terminal_at is not None and current - room.terminal_at > ttl_seconds
                ) or (
                    room.terminal_at is None
                    and room.status == "lobby"
                    and current - room.created_at > ttl_seconds
                )
                if expired:
                    evicted.append(room)
                    del self._rooms[pin]
        return evicted
