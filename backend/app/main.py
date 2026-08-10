from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Game Room Backend")

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    return app


app = create_app()
