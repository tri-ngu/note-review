import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.rooms_http import rooms_router
from app.rooms_ws import rooms_websocket_endpoint
from app.store import RoomStore


async def start_cleanup_sweep(store: RoomStore, interval_seconds: float = 30.0, ttl_seconds: float = 300.0) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        await store.sweep_expired(ttl_seconds=ttl_seconds)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cleanup_task = asyncio.create_task(start_cleanup_sweep(app.state.room_store))
        yield
        cleanup_task.cancel()

    app = FastAPI(title="Game Room Backend", lifespan=lifespan)
    app.state.room_store = RoomStore()

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    app.include_router(rooms_router)
    app.add_api_websocket_route("/ws/room/{pin}", rooms_websocket_endpoint)

    return app


app = create_app()
