import pytest
from starlette.websockets import WebSocketDisconnect

from fastapi.testclient import TestClient
from app.main import create_app
import app.rooms_ws as rooms_ws


def _create_room_and_host_client():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    return client, pin


def test_host_can_connect_with_session_cookie():
    client, pin = _create_room_and_host_client()
    with client.websocket_connect(f"/ws/room/{pin}") as ws:
        ws.send_json({"type": "advance"})
        message = ws.receive_json()
        assert message["type"] == "question_start"


def test_host_connect_rejected_without_matching_session():
    client, pin = _create_room_and_host_client()
    other_client = TestClient(client.app)  # same app/room, no cookie for this room's host
    with pytest.raises(WebSocketDisconnect):
        with other_client.websocket_connect(f"/ws/room/{pin}"):
            pass


def test_player_can_connect_with_player_id():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as ws:
        message = ws.receive_json()
        assert message["type"] == "player_joined"
        assert message["player_id"] == player_id


def test_player_connect_rejected_with_unknown_player_id():
    client, pin = _create_room_and_host_client()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/room/{pin}?player_id=not-a-real-id"):
            pass


def test_advance_from_lobby_starts_first_question_and_broadcasts_to_player():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        host_ws.receive_json()  # player_joined (broadcast to everyone in the Room)
        player_ws.receive_json()  # player_joined
        host_ws.send_json({"type": "advance"})
        host_question = host_ws.receive_json()
        player_question = player_ws.receive_json()
        assert host_question["type"] == "question_start"
        assert player_question["type"] == "question_start"
        assert "correct_answers" not in player_question
        assert "explanation" not in player_question
        assert host_question["round"] == 1


def test_submit_answer_from_all_players_triggers_answer_reveal():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        host_ws.receive_json()  # player_joined (broadcast to everyone in the Room)
        player_ws.receive_json()  # player_joined
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # question_start
        question = player_ws.receive_json()  # question_start

        player_ws.send_json({"type": "submit_answer", "round": question["round"], "selected": [1]})

        host_answered_count = host_ws.receive_json()
        assert host_answered_count["type"] == "answered_count"
        assert host_answered_count["answered"] == 1
        assert host_answered_count["total_connected"] == 1

        host_reveal = host_ws.receive_json()
        player_ws.receive_json()  # answered_count (also broadcast to the answering player)
        player_reveal = player_ws.receive_json()
        assert host_reveal["type"] == "answer_reveal"
        assert player_reveal["type"] == "answer_reveal"
        assert "correct_answers" in host_reveal


def test_advance_after_reveal_moves_to_leaderboard_then_next_question():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        host_ws.receive_json()  # player_joined (broadcast to everyone in the Room)
        player_ws.receive_json()  # player_joined
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()
        question = player_ws.receive_json()
        player_ws.send_json({"type": "submit_answer", "round": question["round"], "selected": [1]})
        host_ws.receive_json()  # answered_count
        host_ws.receive_json()  # answer_reveal
        player_ws.receive_json()  # answered_count (also broadcast to the answering player)
        player_ws.receive_json()  # answer_reveal

        host_leaderboard = host_ws.receive_json()  # auto-broadcast, no host action needed to reach it
        assert host_leaderboard["type"] == "leaderboard"
        assert host_leaderboard["standings"][0]["player_id"] == player_id

        host_ws.send_json({"type": "advance"})
        next_question = host_ws.receive_json()
        assert next_question["type"] == "question_start"
        assert next_question["round"] == 2


def test_end_game_from_leaderboard_broadcasts_game_over():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        host_ws.receive_json()  # player_joined (broadcast to everyone in the Room)
        player_ws.receive_json()  # player_joined
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()
        question = player_ws.receive_json()
        player_ws.send_json({"type": "submit_answer", "round": question["round"], "selected": [1]})
        host_ws.receive_json()  # answered_count
        host_ws.receive_json()  # answer_reveal
        player_ws.receive_json()  # answered_count (also broadcast to the answering player)
        player_ws.receive_json()  # answer_reveal
        host_ws.receive_json()  # leaderboard (auto-broadcast, no host action needed to reach it)

        host_ws.send_json({"type": "end_game"})
        game_over = host_ws.receive_json()
        assert game_over["type"] == "game_over"
        assert game_over["reason"] == "host_ended"


def test_question_times_out_and_reveals_with_zero_points_for_non_answerer(monkeypatch):
    monkeypatch.setattr(rooms_ws, "QUESTION_TIMEOUT_SECONDS", 0.05)
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        host_ws.receive_json()  # player_joined (broadcast to everyone in the Room)
        player_ws.receive_json()  # player_joined
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # question_start
        player_ws.receive_json()  # question_start
        # nobody answers — wait for the shortened timer to fire
        reveal = host_ws.receive_json()
        assert reveal["type"] == "answer_reveal"
        assert reveal["results"] == {}


def test_host_disconnect_ends_game_for_remaining_players(monkeypatch):
    monkeypatch.setattr(rooms_ws, "QUESTION_TIMEOUT_SECONDS", 30.0)
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        player_ws.receive_json()  # player_joined
        with client.websocket_connect(f"/ws/room/{pin}") as host_ws:
            pass  # host connects then immediately disconnects
        game_over = player_ws.receive_json()
        assert game_over["type"] == "game_over"
        assert game_over["reason"] == "host_disconnected"
