"""Shared test helpers. room_test_client() exists because POST /rooms now
requires the caller's session to already hold a real generated QuestionSet
(see app/rooms_http.py's create_room) — Room tests need a ready session
seeded without going through a live Analyzer/Generator/Verifier pipeline
run, so this seeds SessionStore directly with DIGESTIVE_SYSTEM_QUESTION_SET
(the same fixture Room used as its hardcoded default before this reconnect)
and pre-establishes the session cookie via GET /session."""

from fastapi.testclient import TestClient

from app.fixture import DIGESTIVE_SYSTEM_QUESTION_SET
from app.main import create_app
from app.models import SessionState


def room_test_client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    session_id = client.get("/session").cookies["session_id"]
    app.state.session_store._sessions[session_id] = SessionState(
        status="ready", question_set=DIGESTIVE_SYSTEM_QUESTION_SET
    )
    return client
