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
class ClientRuntimeConfig:
    protocol: str = "TCP"
    target_ip: str = "127.0.0.1"
    target_port: int = 9001
    hex_mode: bool = False


class ClientUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, service: "ClientRuntimeService") -> None:
        self.service = service

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.service.udp_transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        asyncio.create_task(self.service.handle_udp_datagram(data, addr))

    def error_received(self, exc: Exception) -> None:
        self.service.emit_system_log("error", "network", "Client UDP transport error", str(exc))

    def connection_lost(self, exc: Exception | None) -> None:
        if exc:
            self.service.emit_system_log("error", "network", "Client UDP transport closed unexpectedly", str(exc))


class ClientRuntimeService:
    def __init__(self, db_factory: Callable[[], Session] = SessionLocal) -> None:
        self.db_factory = db_factory
        self.config = ClientRuntimeConfig()
        self.running = False
        self.connected = False
        self.tcp_reader: asyncio.StreamReader | None = None
        self.tcp_writer: asyncio.StreamWriter | None = None
        self.udp_transport: asyncio.DatagramTransport | None = None
        self.udp_protocol: ClientUDPProtocol | None = None
        self.tx_count = 0
        self.rx_count = 0
        self.peer_label = "-"
        self.receive_task: asyncio.Task[None] | None = None

    def update_config(self, config: ClientRuntimeConfig) -> None:
        self.config = config

    def snapshot(self) -> dict[str, object]:
        return {
            "protocol": self.config.protocol,
            "target_ip": self.config.target_ip,
            "target_port": self.config.target_port,
            "hex_mode": self.config.hex_mode,
            "running": self.running,
            "connected": self.connected,
            "tx_count": self.tx_count,
            "rx_count": self.rx_count,
            "peer_label": self.peer_label,
        }

    async def connect(self) -> None:
        if self.connected:
            return

        if self.config.protocol == "UDP":
            await self._connect_udp()
            return

        self.tcp_reader, self.tcp_writer = await asyncio.open_connection(self.config.target_ip, self.config.target_port)
        self.running = True
        self.connected = True
        self.peer_label = f"{self.config.target_ip}:{self.config.target_port}"
        self.receive_task = asyncio.create_task(self._receive_tcp_loop())
        self.emit_system_log("info", "service", f"Client connected {self.peer_label}")

    async def _connect_udp(self) -> None:
        loop = asyncio.get_running_loop()
        self.udp_transport, self.udp_protocol = await loop.create_datagram_endpoint(
            lambda: ClientUDPProtocol(self),
            local_addr=("0.0.0.0", 0),
        )
        self.running = True
        self.connected = True
        self.peer_label = f"{self.config.target_ip}:{self.config.target_port}"
        self.emit_system_log("info", "service", f"Client connected {self.peer_label}")

    async def disconnect(self) -> None:
        if self.tcp_writer:
            self.tcp_writer.close()
            try:
                await self.tcp_writer.wait_closed()
            except Exception as exc:
                self.emit_system_log("warning", "network", "Client TCP close failed", str(exc))
            self.tcp_writer = None
            self.tcp_reader = None

        if self.udp_transport:
            self.udp_transport.close()
            self.udp_transport = None
            self.udp_protocol = None

        if self.receive_task and self.receive_task is not asyncio.current_task() and not self.receive_task.done():
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass
        self.receive_task = None

        was_connected = self.connected
        self.running = False
        self.connected = False
        self.peer_label = "-"
        if was_connected:
            self.emit_system_log("info", "service", "Client disconnected")

    async def send_manual(self, payload_text: str) -> None:
        payload = parse_payload(payload_text, self.config.hex_mode)

        if self.config.protocol == "UDP":
            if not self.udp_transport:
                raise RuntimeError("Client is not connected")
            self.udp_transport.sendto(payload, (self.config.target_ip, self.config.target_port))
        else:
            if not self.tcp_writer:
                raise RuntimeError("Client is not connected")
            self.tcp_writer.write(payload)
            await self.tcp_writer.drain()

        self.tx_count += len(payload)
        self.emit_system_log("info", "network", f"client -> remote {self.peer_label}")
        self._persist_packet(
            self.config.protocol,
            "client -> remote",
            ("0.0.0.0", 0),
            (self.config.target_ip, self.config.target_port),
            payload,
        )

    async def handle_udp_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        self.rx_count += len(data)
        self.peer_label = f"{addr[0]}:{addr[1]}"
        self.emit_system_log("info", "network", f"remote -> client {self.peer_label}")
        self._persist_packet(self.config.protocol, "remote -> client", addr, ("0.0.0.0", 0), data)

    async def _receive_tcp_loop(self) -> None:
        assert self.tcp_reader is not None
        try:
            while True:
                data = await self.tcp_reader.read(4096)
                if not data:
                    break
                self.rx_count += len(data)
                self.emit_system_log("info", "network", f"remote -> client {self.peer_label}")
                self._persist_packet(
                    self.config.protocol,
                    "remote -> client",
                    (self.config.target_ip, self.config.target_port),
                    ("0.0.0.0", 0),
                    data,
                )
        except Exception as exc:
            self.emit_system_log("error", "network", "Client TCP read failed", str(exc))
        finally:
            self.connected = False
            self.running = False
            self.tcp_reader = None
            self.tcp_writer = None

    def _persist_packet(
        self,
        protocol: str,
        direction: str,
        src: tuple[str, int],
        dst: tuple[str, int],
        payload: bytes,
    ) -> None:
        db = self.db_factory()
        try:
            packet_logger.log_packet(
                db=db,
                service_type="client",
                protocol=protocol,
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
