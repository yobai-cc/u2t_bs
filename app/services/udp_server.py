from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services.logging_service import system_log_service
from app.services.packet_logger import packet_logger
from app.utils.codec import parse_payload


@dataclass(slots=True)
class UDPRelayConfig:
    bind_ip: str = "0.0.0.0"
    bind_port: int = 9000
    custom_reply_data: str = ""
    hex_mode: bool = False


class UDPRelayProtocol(asyncio.DatagramProtocol):
    def __init__(self, service: "UDPRelayService") -> None:
        self.service = service

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.service.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        asyncio.create_task(self.service.handle_datagram(data, addr))

    def error_received(self, exc: Exception) -> None:
        self.service.emit_system_log("error", "network", "UDP transport error", str(exc))

    def connection_lost(self, exc: Exception | None) -> None:
        if exc:
            self.service.emit_system_log("error", "network", "UDP transport closed unexpectedly", str(exc))


class UDPRelayService:
    """Async UDP service that replies fixed configured payloads to devices."""

    def __init__(self, db_factory: Callable[[], Session] = SessionLocal) -> None:
        self.db_factory = db_factory
        self.config = UDPRelayConfig()
        self.transport: asyncio.DatagramTransport | None = None
        self.protocol: UDPRelayProtocol | None = None
        self.running = False
        self.tx_count = 0
        self.rx_count = 0
        self.last_client_addr: tuple[str, int] | None = None

    def update_config(self, config: UDPRelayConfig) -> None:
        self.config = config

    def record_client_addr(self, addr: tuple[str, int]) -> None:
        self.last_client_addr = addr

    async def start(self) -> None:
        if self.running:
            return
        loop = asyncio.get_running_loop()
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: UDPRelayProtocol(self),
            local_addr=(self.config.bind_ip, self.config.bind_port),
        )
        self.running = True
        self.emit_system_log("info", "service", f"UDP server started on {self.config.bind_ip}:{self.config.bind_port}")

    async def stop(self) -> None:
        if self.transport:
            self.transport.close()
            self.transport = None
        self.running = False
        self.emit_system_log("info", "service", "UDP server stopped")

    async def send_manual(self, payload_text: str, target_addr: tuple[str, int] | None = None) -> None:
        payload = parse_payload(payload_text, self.config.hex_mode)
        target = target_addr or self.last_client_addr
        if not target:
            raise RuntimeError("no device address available")
        await self._send_payload(payload, target, "manual")

    async def handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        self.rx_count += len(data)
        self.record_client_addr(addr)
        self.emit_system_log("info", "rule", f"device -> server {addr[0]}:{addr[1]}")
        self._persist_packet("device -> server", addr, (self.config.bind_ip, self.config.bind_port), data)

        if not self.config.custom_reply_data.strip():
            self.emit_system_log("warning", "rule", "UDP packet received but custom reply payload is empty")
            return

        reply_payload = parse_payload(self.config.custom_reply_data, self.config.hex_mode)
        await self._send_payload(reply_payload, addr, "server -> device", source=addr)

    async def _send_payload(
        self,
        payload: bytes,
        target: tuple[str, int],
        direction: str,
        source: tuple[str, int] | None = None,
    ) -> None:
        if not self.transport:
            raise RuntimeError("UDP server is not running")

        self.transport.sendto(payload, target)
        self.tx_count += len(payload)
        src = source or (self.config.bind_ip, self.config.bind_port)
        self.emit_system_log("info", "network", f"{direction} {src[0]}:{src[1]} -> {target[0]}:{target[1]}")
        self._persist_packet(direction, src, target, payload)

    def _persist_packet(self, direction: str, src: tuple[str, int], dst: tuple[str, int], payload: bytes) -> None:
        db = self.db_factory()
        try:
            packet_logger.log_packet(
                db=db,
                service_type="udp_server",
                protocol="UDP",
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
