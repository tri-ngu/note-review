from tests.conftest import room_test_client


def test_create_room_returns_a_valid_pin():
    # Cookie-setting on the very first request is already covered by
    # test_session.py; room_test_client() pre-establishes the session (needed
    # to seed a ready QuestionSet) so that assertion isn't repeatable here.
    client = room_test_client()
    response = client.post("/rooms")
    assert response.status_code == 200
    body = response.json()
    assert len(body["pin"]) == 4
    assert body["pin"].isdigit()


def test_create_room_without_a_ready_question_set_returns_404():
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    response = client.post("/rooms")
    assert response.status_code == 404
    assert response.json()["detail"] == "no_question_set"


def test_join_room_returns_player_id():
    client = room_test_client()
    pin = client.post("/rooms").json()["pin"]
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    assert response.status_code == 200
    body = response.json()
    assert body["nickname"] == "Alice"
    assert body["player_id"]


def test_join_room_auto_suffixes_duplicate_nicknames():
    client = room_test_client()
    pin = client.post("/rooms").json()["pin"]
    client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    assert response.json()["nickname"] == "Alice (1)"


def test_join_room_auto_suffixes_a_third_duplicate_nickname():
    client = room_test_client()
    pin = client.post("/rooms").json()["pin"]
    client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    assert response.json()["nickname"] == "Alice (2)"


def test_join_room_missing_nickname_field_returns_422():
    client = room_test_client()
    pin = client.post("/rooms").json()["pin"]
    response = client.post(f"/rooms/{pin}/join", json={})
    assert response.status_code == 422


def test_create_room_reuses_session_cookie_across_calls():
    client = room_test_client()
    session_id = client.cookies["session_id"]
    first = client.post("/rooms")
    # TestClient persists cookies across requests like a browser; neither call
    # sets a new one since room_test_client() already established the session.
    second = client.post("/rooms")
    assert client.cookies["session_id"] == session_id
    assert "session_id" not in first.cookies
    assert "session_id" not in second.cookies
    assert second.json()["pin"] != first.json()["pin"]


def test_join_nonexistent_room_returns_404():
    client = room_test_client()
    response = client.post("/rooms/0000/join", json={"nickname": "Alice"})
    assert response.status_code == 404
    assert response.json()["detail"] == "room_not_found"


def test_join_full_room_returns_409():
    client = room_test_client()
    pin = client.post("/rooms").json()["pin"]
    for i in range(10):
        response = client.post(f"/rooms/{pin}/join", json={"nickname": f"Player{i}"})
        assert response.status_code == 200
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "OneTooMany"})
    assert response.status_code == 409
    assert response.json()["detail"] == "room_full"


def test_get_room_status_lobby():
    client = room_test_client()
    pin = client.post("/rooms").json()["pin"]
    client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    response = client.get(f"/rooms/{pin}")
    assert response.status_code == 200
    assert response.json() == {"status": "lobby", "player_count": 1}


def test_get_nonexistent_room_returns_404():
    client = room_test_client()
    response = client.get("/rooms/0000")
    assert response.status_code == 404
    assert response.json()["detail"] == "room_not_found"


def test_join_after_game_started_returns_409_already_started():
    client = room_test_client()
    pin = client.post("/rooms").json()["pin"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws:
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # question_start
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "TooLate"})
    assert response.status_code == 409
    assert response.json()["detail"] == "already_started"


def test_get_room_status_reports_in_progress_once_started():
    client = room_test_client()
    pin = client.post("/rooms").json()["pin"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws:
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # question_start
        response = client.get(f"/rooms/{pin}")
    assert response.json()["status"] == "in_progress"
