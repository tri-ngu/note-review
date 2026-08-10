from fastapi import FastAPI

from app.rooms_http import rooms_router
from app.rooms_ws import rooms_websocket_endpoint
from app.store import RoomStore


def create_app() -> FastAPI:
    app = FastAPI(title="Game Room Backend")
    app.state.room_store = RoomStore()

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    app.include_router(rooms_router)
    app.add_api_websocket_route("/ws/room/{pin}", rooms_websocket_endpoint)

    return app


app = create_app()
