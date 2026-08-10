from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from app.session import get_or_create_session_id, SESSION_COOKIE_NAME


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(request: Request, response: Response):
        session_id = get_or_create_session_id(request, response)
        return {"session_id": session_id}

    return app


def test_first_request_sets_a_session_cookie():
    client = TestClient(_build_test_app())
    response = client.get("/whoami")
    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies
    assert response.json()["session_id"] == response.cookies[SESSION_COOKIE_NAME]


def test_subsequent_request_reuses_existing_cookie():
    client = TestClient(_build_test_app())
    first = client.get("/whoami")
    session_id = first.json()["session_id"]
    second = client.get("/whoami")
    assert second.json()["session_id"] == session_id
