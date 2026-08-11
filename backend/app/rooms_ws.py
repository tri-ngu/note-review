import asyncio
import time

from fastapi import WebSocket, WebSocketDisconnect

from app.game_logic import compute_points, is_answer_correct, rank_standings
from app.models import Answer
from app.session import SESSION_COOKIE_NAME
from app.store import RoomNotFoundError, RoomStore

QUESTION_TIMEOUT_SECONDS = 30.0


class _RoomConnections:
    """Tracks live WebSocket connections for one Room's broadcast fan-out."""

    def __init__(self) -> None:
        self.host: WebSocket | None = None
        self.players: dict[str, WebSocket] = {}

    def all_sockets(self):
        sockets = list(self.players.values())
        if self.host is not None:
            sockets.append(self.host)
        return sockets


_connections: dict[str, _RoomConnections] = {}


def _connections_for(pin: str) -> _RoomConnections:
    return _connections.setdefault(pin, _RoomConnections())


async def _broadcast(pin: str, message: dict) -> None:
    conns = _connections_for(pin)
    for socket in conns.all_sockets():
        await socket.send_json(message)


async def rooms_websocket_endpoint(websocket: WebSocket, pin: str) -> None:
    store: RoomStore = websocket.app.state.room_store
    try:
        room = await store.get(pin)
    except RoomNotFoundError:
        await websocket.close(code=4404)
        return

    player_id = websocket.query_params.get("player_id")
    conns = _connections_for(pin)

    if player_id is not None:
        if player_id not in room.players:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        existing = conns.players.get(player_id)
        if existing is not None:
            await existing.close(code=4409)
        conns.players[player_id] = websocket
        await _broadcast(
            pin,
            {"type": "player_joined", "player_id": player_id, "nickname": room.players[player_id].nickname},
        )
        role = "player"
    else:
        session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
        if session_id != room.host_session_id:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        conns.host = websocket
        role = "host"

    try:
        while True:
            message = await websocket.receive_json()
            await _handle_message(store, pin, role, player_id, message)
    except WebSocketDisconnect:
        await _handle_disconnect(store, pin, role, player_id, websocket)


async def _handle_message(store: RoomStore, pin: str, role: str, player_id: str | None, message: dict) -> None:
    message_type = message.get("type")
    if role == "host" and message_type == "advance":
        await _handle_advance(store, pin)
    elif role == "host" and message_type == "end_game":
        await _end_game(store, pin, reason="host_ended")
    elif role == "player" and message_type == "submit_answer":
        await _handle_submit_answer(store, pin, player_id, message)
    # any other role/message_type combination is silently ignored —
    # DESIGN.md says "rejected", enforced here by simply not acting on it


async def _handle_disconnect(store: RoomStore, pin: str, role: str, player_id: str | None, websocket: WebSocket) -> None:
    conns = _connections_for(pin)
    if role == "host":
        conns.host = None
        await _end_game(store, pin, reason="host_disconnected")
        return

    if conns.players.get(player_id) is not websocket:
        return  # this connection was already replaced by a newer one — its own state is stale, no-op
    conns.players.pop(player_id, None)
    lobby_still_open = False
    try:
        async with store.mutate(pin) as room:
            if room.status == "lobby":
                room.players.pop(player_id, None)
                lobby_still_open = True
            else:
                room.players[player_id].connected = False
    except RoomNotFoundError:
        return
    if lobby_still_open:
        await _broadcast(pin, {"type": "player_left", "player_id": player_id})


def _question_start_payload(room, round_index: int) -> dict:
    question = room.question_set.questions[round_index]
    return {
        "type": "question_start",
        "round": round_index + 1,
        "total_rounds": len(room.question_set.questions),
        "question_text": question.question_text,
        "options": question.options,
        "is_select_all": question.is_select_all,
        "page_number": question.page_number,
        "concept": question.concept,
        "server_time": time.monotonic(),
    }


async def _handle_advance(store: RoomStore, pin: str) -> None:
    payload = None
    reveal_to_leaderboard = False
    async with store.mutate(pin) as room:
        if room.status == "lobby":
            round_index = 0
            room.status = "question_active"
            room.current_round = round_index
            room.question_start_time = time.monotonic()
            room.answers = {}
            payload = _question_start_payload(room, round_index)
        elif room.status == "answer_reveal":
            reveal_to_leaderboard = True
        elif room.status == "leaderboard" and room.current_round + 1 < len(room.question_set.questions):
            round_index = room.current_round + 1
            room.status = "question_active"
            room.current_round = round_index
            room.question_start_time = time.monotonic()
            room.answers = {}
            payload = _question_start_payload(room, round_index)
        elif room.status == "leaderboard":
            pass  # payload stays None: last question already played, fall through to finish
        else:
            return  # advance is a no-op outside lobby/leaderboard/answer_reveal

    if reveal_to_leaderboard:
        await _show_leaderboard(store, pin)
    elif payload is not None:
        await _broadcast(pin, payload)
        asyncio.create_task(_run_question_timer(store, pin, payload["round"]))
    else:
        await _finish_game(store, pin, reason="natural_end")


async def _run_question_timer(store: RoomStore, pin: str, round_number: int) -> None:
    await asyncio.sleep(QUESTION_TIMEOUT_SECONDS)
    try:
        async with store.mutate(pin) as room:
            if room.status != "question_active" or room.current_round + 1 != round_number:
                return  # already advanced by all-answered path
    except RoomNotFoundError:
        return
    await _reveal_answers(store, pin)


async def _handle_submit_answer(store: RoomStore, pin: str, player_id: str, message: dict) -> None:
    now = time.monotonic()
    should_reveal = False
    answered_count = 0
    total_connected = 0
    async with store.mutate(pin) as room:
        if room.status != "question_active":
            return
        if player_id in room.answers:
            return  # one-shot: already answered
        if room.current_round != message.get("round", 0) - 1:
            return
        question = room.question_set.questions[room.current_round]
        elapsed = now - (room.question_start_time or now)
        if elapsed > QUESTION_TIMEOUT_SECONDS:
            return  # arrived after server cutoff — treated as timeout, no answer recorded
        selected = message.get("selected", [])
        correct = is_answer_correct(question, selected)
        points = compute_points(elapsed) if correct else 0
        room.answers[player_id] = Answer(
            player_id=player_id, selected=selected, elapsed=elapsed, correct=correct, points=points
        )
        room.players[player_id].score += points
        connected_players = [p for p in room.players.values() if p.connected]
        answered_count = len(room.answers)
        total_connected = len(connected_players)
        should_reveal = answered_count >= total_connected and total_connected > 0

    await _broadcast(pin, {"type": "answered_count", "answered": answered_count, "total_connected": total_connected})
    if should_reveal:
        await _reveal_answers(store, pin)


async def _reveal_answers(store: RoomStore, pin: str) -> None:
    payload = None
    async with store.mutate(pin) as room:
        if room.status != "question_active":
            return
        room.status = "answer_reveal"
        question = room.question_set.questions[room.current_round]
        results = {
            player_id: {"correct": answer.correct, "points": answer.points}
            for player_id, answer in room.answers.items()
        }
        payload = {
            "type": "answer_reveal",
            "round": room.current_round + 1,
            "correct_answers": question.correct_answers,
            "explanation": question.explanation,
            "results": results,
        }
    await _broadcast(pin, payload)
    # Room stays in "answer_reveal" until the Host sends `advance` (see
    # _handle_advance) — no auto-transition to leaderboard.


async def _show_leaderboard(store: RoomStore, pin: str) -> None:
    async with store.mutate(pin) as room:
        room.status = "leaderboard"
        standings = rank_standings(room.players)
        is_final = room.current_round + 1 >= len(room.question_set.questions)
        payload = {
            "type": "leaderboard",
            "round": room.current_round + 1,
            "total_rounds": len(room.question_set.questions),
            "standings": standings,
            "is_final": is_final,
        }
    await _broadcast(pin, payload)


async def _finish_game(store: RoomStore, pin: str, reason: str) -> None:
    async with store.mutate(pin) as room:
        room.status = "finished"
        room.terminal_reason = reason
        room.terminal_at = time.monotonic()
        standings = rank_standings(room.players)
        payload = {"type": "game_over", "reason": reason, "final_standings": standings}
    await _broadcast(pin, payload)


async def _end_game(store: RoomStore, pin: str, reason: str) -> None:
    try:
        await _finish_game(store, pin, reason)
    except RoomNotFoundError:
        pass
