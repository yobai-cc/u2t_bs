from __future__ import annotations

from app.services.client_runtime import ClientRuntimeConfig, ClientRuntimeService
from app.services.tcp_server import TCPServerConfig, TCPServerService
from app.services.udp_server import UDPServerConfig, UDPServerService


class RuntimeManager:
    """Owns in-process runtime services and their observable state."""

    def __init__(self) -> None:
        self.udp_server = UDPServerService()
        self.tcp_server = TCPServerService()
        self.client_runtime = ClientRuntimeService()

    def udp_snapshot(self) -> dict[str, object]:
        config = self.udp_server.config
        return {
            "running": self.udp_server.running,
            "bind_ip": config.bind_ip,
            "bind_port": config.bind_port,
            "custom_reply_data": config.custom_reply_data,
            "hex_mode": config.hex_mode,
            "tx_count": self.udp_server.tx_count,
            "rx_count": self.udp_server.rx_count,
            "last_client_addr": self.udp_server.last_client_addr,
        }

    def apply_udp_config(self, payload: dict[str, object]) -> UDPServerConfig:
        config = UDPServerConfig(
            bind_ip=str(payload.get("bind_ip") or "0.0.0.0"),
            bind_port=int(payload.get("bind_port") or 9000),
            custom_reply_data=str(payload.get("custom_reply_data") or ""),
            hex_mode=bool(payload.get("hex_mode")),
        )
        self.udp_server.update_config(config)
        return config

    def tcp_snapshot(self) -> dict[str, object]:
        return self.tcp_server.snapshot()

    def apply_tcp_config(self, payload: dict[str, object]) -> TCPServerConfig:
        config = TCPServerConfig(
            bind_ip=str(payload.get("bind_ip") or "0.0.0.0"),
            bind_port=int(payload.get("bind_port") or 9100),
            hex_mode=bool(payload.get("hex_mode")),
        )
        self.tcp_server.update_config(config)
        return config

    def client_snapshot(self) -> dict[str, object]:
        return self.client_runtime.snapshot()

    def apply_client_config(self, payload: dict[str, object]) -> ClientRuntimeConfig:
        config = ClientRuntimeConfig(
            protocol=str(payload.get("protocol") or "TCP").upper(),
            target_ip=str(payload.get("target_ip") or "127.0.0.1"),
            target_port=int(payload.get("target_port") or 9001),
            hex_mode=bool(payload.get("hex_mode")),
        )
        self.client_runtime.update_config(config)
        return config


runtime_manager = RuntimeManager()
