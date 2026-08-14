import os
import uuid

from fastapi import Request, Response

SESSION_COOKIE_NAME = "session_id"

# Render sets RENDER=true on deployed services; secure cookies require https, which
# only exists there, not in local dev over plain http.
_SECURE = bool(os.environ.get("RENDER"))


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
        secure=_SECURE,
    )
    return new_session_id
