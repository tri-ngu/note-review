import uuid

from fastapi import Request, Response

SESSION_COOKIE_NAME = "session_id"


def get_or_create_session_id(request: Request, response: Response) -> str:
    existing = request.cookies.get(SESSION_COOKIE_NAME)
    if existing:
        return existing
    new_session_id = uuid.uuid4().hex
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=new_session_id,
        httponly=True,
        samesite="lax",
    )
    return new_session_id
