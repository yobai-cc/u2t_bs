from __future__ import annotations

from app.services.tcp_server import TCPServerConfig, TCPServerService
from app.services.udp_server import UDPRelayConfig, UDPRelayService


class RuntimeManager:
    """Owns in-process runtime services and their observable state."""

    def __init__(self) -> None:
        self.udp_relay = UDPRelayService()
        self.tcp_server = TCPServerService()

    def udp_snapshot(self) -> dict[str, object]:
        config = self.udp_relay.config
        return {
            "running": self.udp_relay.running,
            "bind_ip": config.bind_ip,
            "bind_port": config.bind_port,
            "cloud_ip": config.cloud_ip,
            "cloud_port": config.cloud_port,
            "custom_reply_data": config.custom_reply_data,
            "hex_mode": config.hex_mode,
            "tx_count": self.udp_relay.tx_count,
            "rx_count": self.udp_relay.rx_count,
            "last_client_addr": self.udp_relay.last_client_addr,
        }

    def apply_udp_config(self, payload: dict[str, object]) -> UDPRelayConfig:
        config = UDPRelayConfig(
            bind_ip=str(payload.get("bind_ip") or "0.0.0.0"),
            bind_port=int(payload.get("bind_port") or 9000),
            cloud_ip=str(payload.get("cloud_ip") or "127.0.0.1"),
            cloud_port=int(payload.get("cloud_port") or 9001),
            custom_reply_data=str(payload.get("custom_reply_data") or ""),
            hex_mode=bool(payload.get("hex_mode")),
        )
        self.udp_relay.update_config(config)
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


runtime_manager = RuntimeManager()
