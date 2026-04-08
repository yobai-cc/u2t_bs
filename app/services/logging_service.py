from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.system_log import SystemLog


class SystemLogService:
    """Handles file logging, database logging, and in-memory event fanout."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("u2t.app")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if not self.logger.handlers:
            handler = RotatingFileHandler(self.settings.app_log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self.logger.addHandler(handler)
        self._subscribers: set[Any] = set()

    async def broadcast(self, event: dict[str, str]) -> None:
        stale = []
        for subscriber in self._subscribers:
            try:
                await subscriber.send_json(event)
            except Exception:
                stale.append(subscriber)
        for subscriber in stale:
            self._subscribers.discard(subscriber)

    def subscribe(self, websocket: Any) -> None:
        self._subscribers.add(websocket)

    def unsubscribe(self, websocket: Any) -> None:
        self._subscribers.discard(websocket)

    def log_to_db(self, level: str, category: str, message: str, detail: str = "", db: Session | None = None) -> None:
        self.logger.log(getattr(logging, level.upper(), logging.INFO), "%s | %s", category, message)
        if db is not None:
            db.add(SystemLog(level=level.upper(), category=category, message=message, detail=detail))
            db.commit()


system_log_service = SystemLogService()
