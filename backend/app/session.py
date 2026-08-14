import os
import uuid

from fastapi import Request, Response

SESSION_COOKIE_NAME = "session_id"

# Frontend (Vercel) and backend (Render) are different origins in production, so the
# session cookie must be SameSite=None + Secure to be sent cross-site at all. Locally
# (FRONTEND_ORIGIN unset) both run same-origin via the Vite dev proxy, where
# SameSite=None without Secure is rejected by browsers over plain http — samesite="lax"
# still works there since there's no cross-site request to begin with.
_CROSS_SITE = bool(os.environ.get("FRONTEND_ORIGIN"))


def get_or_create_session_id(request: Request, response: Response) -> str:
    existing = request.cookies.get(SESSION_COOKIE_NAME)
    if existing:
        return existing
    new_session_id = uuid.uuid4().hex
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=new_session_id,
        httponly=True,
        samesite="none" if _CROSS_SITE else "lax",
        secure=_CROSS_SITE,
    )
    return new_session_id
