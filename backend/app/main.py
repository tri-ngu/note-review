import asyncio
import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.generation_http import generation_router
from app.rooms_http import rooms_router
from app.rooms_ws import notify_and_close_evicted_room, rooms_websocket_endpoint
from app.session_store import SessionStore
from app.store import RoomStore


async def start_cleanup_sweep(store: RoomStore, interval_seconds: float = 30.0, ttl_seconds: float = 300.0) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        evicted = await store.sweep_expired(ttl_seconds=ttl_seconds)
        for room in evicted:
            await notify_and_close_evicted_room(room.pin, was_abandoned_lobby=room.status == "lobby")


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cleanup_task = asyncio.create_task(start_cleanup_sweep(app.state.room_store))
        yield
        cleanup_task.cancel()

    app = FastAPI(title="Note Review Backend", lifespan=lifespan)
    app.state.room_store = RoomStore()
    app.state.session_store = SessionStore()

    frontend_origin = os.environ.get("FRONTEND_ORIGIN")
    if frontend_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[frontend_origin],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    @app.get("/health/db")
    def health_check_db():
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            return {"status": "unconfigured"}
        try:
            with psycopg.connect(database_url, connect_timeout=5) as conn:
                conn.execute("SELECT 1")
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}
        return {"status": "ok"}

    app.include_router(rooms_router)
    app.include_router(generation_router)
    app.add_api_websocket_route("/ws/room/{pin}", rooms_websocket_endpoint)

    return app


app = create_app()
