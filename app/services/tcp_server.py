from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services.logging_service import system_log_service
from app.services.packet_logger import packet_logger
from app.utils.codec import parse_payload


@dataclass(slots=True)
class TCPServerConfig:
    bind_ip: str = "0.0.0.0"
    bind_port: int = 9100
    hex_mode: bool = False


@dataclass(slots=True)
class TCPClientState:
    client_id: str
    peer_ip: str
    peer_port: int
    connected_at: str
    tx_count: int = 0
    rx_count: int = 0


@dataclass(slots=True)
class TCPClientConnection:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    state: TCPClientState
    task: asyncio.Task[None] | None = field(default=None)


class TCPServerService:
    def __init__(self, db_factory: Callable[[], Session] = SessionLocal) -> None:
        self.db_factory = db_factory
        self.config = TCPServerConfig()
        self.server: asyncio.AbstractServer | None = None
        self.running = False
        self.clients: dict[str, TCPClientConnection] = {}
        self.tx_count = 0
        self.rx_count = 0

    def update_config(self, config: TCPServerConfig) -> None:
        self.config = config

    def make_client_id(self, addr: tuple[str, int]) -> str:
        return f"{addr[0]}:{addr[1]}"

    def snapshot(self) -> dict[str, object]:
        return {
            "running": self.running,
            "bind_ip": self.config.bind_ip,
            "bind_port": self.config.bind_port,
            "hex_mode": self.config.hex_mode,
            "tx_count": self.tx_count,
            "rx_count": self.rx_count,
            "client_count": len(self.clients),
            "clients": [
                {
                    "client_id": connection.state.client_id,
                    "peer_ip": connection.state.peer_ip,
                    "peer_port": connection.state.peer_port,
                    "connected_at": connection.state.connected_at,
                    "tx_count": connection.state.tx_count,
                    "rx_count": connection.state.rx_count,
                }
                for connection in self.clients.values()
            ],
        }

    async def start(self) -> None:
        if self.running:
            return
        self.server = await asyncio.start_server(self._handle_client, self.config.bind_ip, self.config.bind_port)
        self.running = True
        self.emit_system_log("info", "service", f"TCP server started on {self.config.bind_ip}:{self.config.bind_port}")

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

        client_ids = list(self.clients.keys())
        for client_id in client_ids:
            await self.disconnect_client(client_id)

        self.running = False
        self.emit_system_log("info", "service", "TCP server stopped")

    async def send_manual(self, client_id: str, payload_text: str) -> None:
        connection = self.clients.get(client_id)
        if connection is None:
            raise RuntimeError(f"Unknown TCP client: {client_id}")

        payload = parse_payload(payload_text, self.config.hex_mode)
        connection.writer.write(payload)
        await connection.writer.drain()
        self.tx_count += len(payload)
        connection.state.tx_count += len(payload)
        self.emit_system_log("info", "network", f"server -> client {client_id}")
        self._persist_packet(
            "server -> client",
            (self.config.bind_ip, self.config.bind_port),
            (connection.state.peer_ip, connection.state.peer_port),
            payload,
        )

    async def disconnect_client(self, client_id: str) -> None:
        connection = self.clients.pop(client_id, None)
        if connection is None:
            return

        connection.writer.close()
        try:
            await connection.writer.wait_closed()
        except Exception as exc:
            self.emit_system_log("warning", "network", f"TCP client close failed {client_id}", str(exc))

        if connection.task and connection.task is not asyncio.current_task() and not connection.task.done():
            connection.task.cancel()

        self.emit_system_log("info", "service", f"TCP client disconnected {client_id}")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        if not isinstance(peer, tuple) or len(peer) < 2:
            writer.close()
            await writer.wait_closed()
            return

        peer_ip = str(peer[0])
        peer_port = int(peer[1])
        client_id = self.make_client_id((peer_ip, peer_port))
        state = TCPClientState(
            client_id=client_id,
            peer_ip=peer_ip,
            peer_port=peer_port,
            connected_at=datetime.now(timezone.utc).isoformat(),
        )
        connection = TCPClientConnection(reader=reader, writer=writer, state=state)
        connection.task = asyncio.current_task()
        self.clients[client_id] = connection
        self.emit_system_log("info", "service", f"TCP client connected {client_id}")

        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break

                self.rx_count += len(data)
                connection.state.rx_count += len(data)
                self._persist_packet(
                    "client -> server",
                    (peer_ip, peer_port),
                    (self.config.bind_ip, self.config.bind_port),
                    data,
                )
        except Exception as exc:
            self.emit_system_log("error", "network", f"TCP read failed {client_id}", str(exc))
        finally:
            self.clients.pop(client_id, None)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            self.emit_system_log("info", "service", f"TCP client disconnected {client_id}")

    def _persist_packet(self, direction: str, src: tuple[str, int], dst: tuple[str, int], payload: bytes) -> None:
        db = self.db_factory()
        try:
            packet_logger.log_packet(
                db=db,
                service_type="tcp_server",
                protocol="TCP",
                direction=direction,
                src_ip=src[0],
                src_port=src[1],
                dst_ip=dst[0],
                dst_port=dst[1],
                payload=payload,
            )
        finally:
            db.close()

    def emit_system_log(self, level: str, category: str, message: str, detail: str = "") -> None:
        db = self.db_factory()
        try:
            system_log_service.log_to_db(level, category, message, detail, db=db)
        finally:
            db.close()
