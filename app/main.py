from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import auth, pages, ws
from app.services.logging_service import system_log_service


def create_app() -> FastAPI:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="U2T Web Platform")
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie=settings.session_cookie_name,
        https_only=settings.session_secure,
        same_site="lax",
    )

    static_dir = Path("app/static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(ws.router)

    @app.on_event("startup")
    async def on_startup() -> None:
        init_db()
        system_log_service.logger.info("Application startup complete")

    return app


app = create_app()
