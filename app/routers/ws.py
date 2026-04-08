from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.logging_service import system_log_service
from app.services.runtime_manager import runtime_manager


router = APIRouter(tags=["ws"])


@router.websocket("/ws/runtime")
async def runtime_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    system_log_service.subscribe(websocket)
    try:
        while True:
            await websocket.send_json({"type": "snapshot", "udp": runtime_manager.udp_snapshot()})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        system_log_service.unsubscribe(websocket)
    except Exception:
        system_log_service.unsubscribe(websocket)
        raise
