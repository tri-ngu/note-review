from fastapi import FastAPI

from app.rooms_http import rooms_router
from app.store import RoomStore


def create_app() -> FastAPI:
    app = FastAPI(title="Game Room Backend")
    app.state.room_store = RoomStore()

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    app.include_router(rooms_router)

    return app


app = create_app()
