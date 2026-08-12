import pytest
from starlette.websockets import WebSocketDisconnect

from fastapi.testclient import TestClient
from app.main import create_app
from app.fixture import DIGESTIVE_SYSTEM_QUESTION_SET
import app.rooms_ws as rooms_ws
import app.game_logic as game_logic


def _create_room_and_host_client():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    return client, pin


def _create_deterministic_room_and_host_client(monkeypatch):
    """Disables the per-Room shuffle so question order matches DIGESTIVE_SYSTEM_QUESTION_SET exactly."""
    monkeypatch.setattr(game_logic.random, "shuffle", lambda seq: None)
    return _create_room_and_host_client()


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

        host_ws.send_json({"type": "advance"})  # host must advance out of answer_reveal
        host_leaderboard = host_ws.receive_json()
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
        host_ws.send_json({"type": "advance"})  # host must advance out of answer_reveal
        host_ws.receive_json()  # leaderboard

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


def test_player_role_cannot_send_advance():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        host_ws.receive_json()  # player_joined
        player_ws.receive_json()  # player_joined
        player_ws.send_json({"type": "advance"})  # players cannot drive state
        # if the bogus advance had taken effect, the room would already be
        # question_active and this legitimate host advance would silently no-op,
        # leaving this receive_json() to hang forever waiting for a message that
        # never arrives — the assertion below only gets a chance to run at all
        # if the player's message was correctly ignored
        host_ws.send_json({"type": "advance"})
        question = host_ws.receive_json()
        assert question["type"] == "question_start"
        assert question["round"] == 1


def test_host_role_cannot_send_submit_answer():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        host_ws.receive_json()
        player_ws.receive_json()
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # question_start
        question = player_ws.receive_json()
        host_ws.send_json({"type": "submit_answer", "round": question["round"], "selected": [1]})
        player_ws.send_json({"type": "submit_answer", "round": question["round"], "selected": [1]})
        host_answered = host_ws.receive_json()
        assert host_answered["type"] == "answered_count"
        assert host_answered["answered"] == 1  # only the player's answer counted


def test_unknown_message_type_is_silently_ignored():
    client, pin = _create_room_and_host_client()
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws:
        host_ws.send_json({"type": "not_a_real_type"})
        host_ws.send_json({"type": "advance"})
        question = host_ws.receive_json()
        assert question["type"] == "question_start"


def test_message_missing_type_key_is_silently_ignored():
    client, pin = _create_room_and_host_client()
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws:
        host_ws.send_json({"round": 1})
        host_ws.send_json({"type": "advance"})
        question = host_ws.receive_json()
        assert question["type"] == "question_start"


def test_duplicate_answer_submission_from_same_player_is_ignored():
    client, pin = _create_room_and_host_client()
    p1 = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    p2 = client.post(f"/rooms/{pin}/join", json={"nickname": "Bob"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={p1}") as p1_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={p2}") as p2_ws:
        host_ws.receive_json()  # p1 joined
        host_ws.receive_json()  # p2 joined
        p1_ws.receive_json()  # p1's own player_joined
        p1_ws.receive_json()  # p2 joined
        p2_ws.receive_json()  # p2's own player_joined

        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # question_start
        q1 = p1_ws.receive_json()
        q2 = p2_ws.receive_json()

        p1_ws.send_json({"type": "submit_answer", "round": q1["round"], "selected": [1]})
        p1_ws.send_json({"type": "submit_answer", "round": q1["round"], "selected": [2]})  # duplicate, ignored

        host_answered = host_ws.receive_json()
        assert host_answered["answered"] == 1
        assert host_answered["total_connected"] == 2  # not yet revealed — p2 hasn't answered

        p2_ws.send_json({"type": "submit_answer", "round": q2["round"], "selected": [1]})
        host_answered_2 = host_ws.receive_json()
        assert host_answered_2["answered"] == 2

        reveal = host_ws.receive_json()
        assert reveal["type"] == "answer_reveal"
        assert len(reveal["results"]) == 2  # exactly 2 — the duplicate was never recorded


def test_answer_submission_for_wrong_round_is_ignored():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        host_ws.receive_json()
        player_ws.receive_json()
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()
        question = player_ws.receive_json()
        player_ws.send_json({"type": "submit_answer", "round": question["round"] + 1, "selected": [1]})
        player_ws.send_json({"type": "submit_answer", "round": question["round"], "selected": [1]})
        host_answered = host_ws.receive_json()
        assert host_answered["answered"] == 1  # only the correctly-addressed submission counted


def _play_round_one(host_ws, player_ws, selected):
    host_ws.receive_json()  # player_joined
    player_ws.receive_json()  # player_joined
    host_ws.send_json({"type": "advance"})
    host_ws.receive_json()  # round 1 question_start
    q1 = player_ws.receive_json()
    player_ws.send_json({"type": "submit_answer", "round": q1["round"], "selected": selected})
    host_ws.receive_json()  # answered_count
    host_ws.receive_json()  # answer_reveal
    player_ws.receive_json()  # answered_count
    player_ws.receive_json()  # answer_reveal
    host_ws.send_json({"type": "advance"})  # host must advance out of answer_reveal
    host_ws.receive_json()  # leaderboard
    player_ws.receive_json()  # leaderboard (also broadcast to the player)
    host_ws.send_json({"type": "advance"})  # -> round 2
    host_q2 = host_ws.receive_json()
    player_q2 = player_ws.receive_json()
    return host_q2, player_q2


def test_select_all_exact_match_scores_full_points(monkeypatch):
    client, pin = _create_deterministic_room_and_host_client(monkeypatch)
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        _, player_q2 = _play_round_one(host_ws, player_ws, [1])
        assert player_q2["is_select_all"] is True
        correct_answers = DIGESTIVE_SYSTEM_QUESTION_SET.questions[1].correct_answers

        player_ws.send_json({"type": "submit_answer", "round": player_q2["round"], "selected": correct_answers})
        host_ws.receive_json()  # answered_count
        reveal = host_ws.receive_json()
        assert reveal["results"][player_id]["correct"] is True
        assert reveal["results"][player_id]["points"] > 0


def test_select_all_partial_selection_scores_zero_points_no_partial_credit(monkeypatch):
    client, pin = _create_deterministic_room_and_host_client(monkeypatch)
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        _, player_q2 = _play_round_one(host_ws, player_ws, [1])
        assert player_q2["is_select_all"] is True
        full_correct = DIGESTIVE_SYSTEM_QUESTION_SET.questions[1].correct_answers
        partial_subset = full_correct[:1]
        assert len(partial_subset) < len(full_correct)

        player_ws.send_json({"type": "submit_answer", "round": player_q2["round"], "selected": partial_subset})
        host_ws.receive_json()  # answered_count
        reveal = host_ws.receive_json()
        assert reveal["results"][player_id]["correct"] is False
        assert reveal["results"][player_id]["points"] == 0


def test_duplicate_player_connection_closes_old_socket_and_replaces_it():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as old_ws:
        old_ws.receive_json()  # player_joined (old connection's own broadcast)
        with client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as new_ws:
            # old socket is server-closed (4409) before the new one's player_joined
            # broadcasts — old_ws never sees that broadcast, only its own close
            with pytest.raises(WebSocketDisconnect):
                old_ws.receive_json()
            new_ws.receive_json()  # player_joined (new connection's own broadcast)

            # the new connection is the sole live one — a host advance reaches it
            with client.websocket_connect(f"/ws/room/{pin}") as host_ws:
                host_ws.send_json({"type": "advance"})
                host_ws.receive_json()  # question_start
                question = new_ws.receive_json()
                assert question["type"] == "question_start"


def test_mid_game_player_disconnect_is_not_removed_and_score_stays():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws:
        with client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
            host_ws.receive_json()  # player_joined
            player_ws.receive_json()  # player_joined
            host_ws.send_json({"type": "advance"})
            host_ws.receive_json()  # question_start
            player_ws.receive_json()  # question_start
        # player_ws closes here — mid QUESTION_ACTIVE, not lobby
        response = client.get(f"/rooms/{pin}")
        assert response.json()["player_count"] == 1  # still in the roster, not removed


def test_full_game_all_rounds_reaches_finished_with_natural_end():
    client, pin = _create_room_and_host_client()
    player_id = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    total_rounds = len(DIGESTIVE_SYSTEM_QUESTION_SET.questions)
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={player_id}") as player_ws:
        host_ws.receive_json()  # player_joined
        player_ws.receive_json()  # player_joined

        for round_number in range(1, total_rounds + 1):
            host_ws.send_json({"type": "advance"})
            host_q = host_ws.receive_json()
            assert host_q["type"] == "question_start"
            assert host_q["round"] == round_number
            player_q = player_ws.receive_json()
            assert player_q["type"] == "question_start"
            assert player_q["round"] == round_number
            player_ws.send_json({"type": "submit_answer", "round": player_q["round"], "selected": [1]})
            host_ws.receive_json()  # answered_count
            host_ws.receive_json()  # answer_reveal
            player_ws.receive_json()  # answered_count
            player_ws.receive_json()  # answer_reveal
            host_ws.send_json({"type": "advance"})  # host must advance out of answer_reveal
            leaderboard = host_ws.receive_json()
            assert leaderboard["type"] == "leaderboard"
            assert leaderboard["is_final"] == (round_number == total_rounds)
            player_ws.receive_json()  # leaderboard (also broadcast to the player)

        host_ws.send_json({"type": "advance"})
        game_over = host_ws.receive_json()
        assert game_over["type"] == "game_over"
        assert game_over["reason"] == "natural_end"
        assert len(game_over["final_standings"]) == 1


def test_three_player_leaderboard_ranking_with_tie(monkeypatch):
    client, pin = _create_deterministic_room_and_host_client(monkeypatch)
    p1 = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"}).json()["player_id"]
    p2 = client.post(f"/rooms/{pin}/join", json={"nickname": "Bob"}).json()["player_id"]
    p3 = client.post(f"/rooms/{pin}/join", json={"nickname": "Carol"}).json()["player_id"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={p1}") as p1_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={p2}") as p2_ws, \
         client.websocket_connect(f"/ws/room/{pin}?player_id={p3}") as p3_ws:
        for _ in range(3):
            host_ws.receive_json()
        for _ in range(3):
            p1_ws.receive_json()
        for _ in range(2):
            p2_ws.receive_json()
        p3_ws.receive_json()

        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # question_start
        q1 = p1_ws.receive_json()
        q2 = p2_ws.receive_json()
        q3 = p3_ws.receive_json()

        # deterministic order: round 1 is the "teeth during ingestion" MC question, correct_answers == [1]
        p1_ws.send_json({"type": "submit_answer", "round": q1["round"], "selected": [1]})
        p2_ws.send_json({"type": "submit_answer", "round": q2["round"], "selected": [1]})
        p3_ws.send_json({"type": "submit_answer", "round": q3["round"], "selected": [2]})

        for _ in range(3):
            host_ws.receive_json()  # answered_count x3
        reveal = host_ws.receive_json()
        assert reveal["type"] == "answer_reveal"
        host_ws.send_json({"type": "advance"})  # host must advance out of answer_reveal
        leaderboard = host_ws.receive_json()
        assert leaderboard["type"] == "leaderboard"

        standings_by_id = {s["player_id"]: s for s in leaderboard["standings"]}
        assert standings_by_id[p1]["score"] == standings_by_id[p2]["score"]
        assert standings_by_id[p1]["rank"] == 1
        assert standings_by_id[p2]["rank"] == 1
        assert standings_by_id[p3]["rank"] == 3  # skips rank 2
