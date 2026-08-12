import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.fixture import DIGESTIVE_SYSTEM_QUESTION_SET
from app.game_logic import shuffle_questions
from app.models import PlayerState
from app.session import get_or_create_session_id
from app.store import RoomNotFoundError, RoomStore

rooms_router = APIRouter()

ROOM_CAPACITY = 10


class JoinRequest(BaseModel):
    nickname: str


def _room_store(request: Request) -> RoomStore:
    return request.app.state.room_store


@rooms_router.post("/rooms")
async def create_room(request: Request, response: Response):
    session_id = get_or_create_session_id(request, response)
    store = _room_store(request)
    room = await store.create_room(
        host_session_id=session_id,
        question_set=shuffle_questions(DIGESTIVE_SYSTEM_QUESTION_SET),
    )
    return {"pin": room.pin}


def _unique_nickname(existing_nicknames: set[str], requested: str) -> str:
    if requested not in existing_nicknames:
        return requested
    suffix = 1
    while f"{requested} ({suffix})" in existing_nicknames:
        suffix += 1
    return f"{requested} ({suffix})"


@rooms_router.post("/rooms/{pin}/join")
async def join_room(pin: str, body: JoinRequest, request: Request):
    store = _room_store(request)
    try:
        async with store.mutate(pin) as room:
            if room.status != "lobby":
                raise HTTPException(status_code=409, detail="already_started")
            if len(room.players) >= ROOM_CAPACITY:
                raise HTTPException(status_code=409, detail="room_full")
            existing_nicknames = {p.nickname for p in room.players.values()}
            nickname = _unique_nickname(existing_nicknames, body.nickname)
            player_id = uuid.uuid4().hex
            room.players[player_id] = PlayerState(player_id=player_id, nickname=nickname)
            return {"player_id": player_id, "nickname": nickname}
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="room_not_found")


_PUBLIC_STATUS = {
    "lobby": "lobby",
    "question_active": "in_progress",
    "answer_reveal": "in_progress",
    "leaderboard": "in_progress",
    "finished": "finished",
}


@rooms_router.get("/rooms/{pin}")
async def get_room(pin: str, request: Request):
    store = _room_store(request)
    try:
        room = await store.get(pin)
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="room_not_found")
    return {
        "status": _PUBLIC_STATUS[room.status],
        "player_count": len(room.players),
    }
