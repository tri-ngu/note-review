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
