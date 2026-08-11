from fastapi.testclient import TestClient
from app.main import create_app


def test_create_room_sets_cookie_and_returns_pin():
    client = TestClient(create_app())
    response = client.post("/rooms")
    assert response.status_code == 200
    body = response.json()
    assert len(body["pin"]) == 4
    assert body["pin"].isdigit()
    assert "session_id" in response.cookies


def test_join_room_returns_player_id():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    assert response.status_code == 200
    body = response.json()
    assert body["nickname"] == "Alice"
    assert body["player_id"]


def test_join_room_auto_suffixes_duplicate_nicknames():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    assert response.json()["nickname"] == "Alice (1)"


def test_join_room_auto_suffixes_a_third_duplicate_nickname():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    assert response.json()["nickname"] == "Alice (2)"


def test_join_room_missing_nickname_field_returns_422():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    response = client.post(f"/rooms/{pin}/join", json={})
    assert response.status_code == 422


def test_create_room_reuses_session_cookie_across_calls():
    client = TestClient(create_app())
    first = client.post("/rooms")
    session_id = first.cookies["session_id"]
    second = client.post("/rooms")
    # TestClient persists cookies across requests like a browser; the second
    # response has no Set-Cookie header of its own since it reused the existing one.
    assert client.cookies["session_id"] == session_id
    assert "session_id" not in second.cookies
    assert second.json()["pin"] != first.json()["pin"]


def test_join_nonexistent_room_returns_404():
    client = TestClient(create_app())
    response = client.post("/rooms/0000/join", json={"nickname": "Alice"})
    assert response.status_code == 404
    assert response.json()["detail"] == "room_not_found"


def test_join_full_room_returns_409():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    for i in range(10):
        response = client.post(f"/rooms/{pin}/join", json={"nickname": f"Player{i}"})
        assert response.status_code == 200
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "OneTooMany"})
    assert response.status_code == 409
    assert response.json()["detail"] == "room_full"


def test_get_room_status_lobby():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    client.post(f"/rooms/{pin}/join", json={"nickname": "Alice"})
    response = client.get(f"/rooms/{pin}")
    assert response.status_code == 200
    assert response.json() == {"status": "lobby", "player_count": 1}


def test_get_nonexistent_room_returns_404():
    client = TestClient(create_app())
    response = client.get("/rooms/0000")
    assert response.status_code == 404
    assert response.json()["detail"] == "room_not_found"


def test_join_after_game_started_returns_409_already_started():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws:
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # question_start
    response = client.post(f"/rooms/{pin}/join", json={"nickname": "TooLate"})
    assert response.status_code == 409
    assert response.json()["detail"] == "already_started"


def test_get_room_status_reports_in_progress_once_started():
    client = TestClient(create_app())
    pin = client.post("/rooms").json()["pin"]
    with client.websocket_connect(f"/ws/room/{pin}") as host_ws:
        host_ws.send_json({"type": "advance"})
        host_ws.receive_json()  # question_start
        response = client.get(f"/rooms/{pin}")
    assert response.json()["status"] == "in_progress"
