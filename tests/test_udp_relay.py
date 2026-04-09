import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.packet_log import PacketLog
from app.services.udp_server import UDPServerConfig, UDPServerService


def test_update_config_changes_runtime_state() -> None:
    service = UDPServerService()
    config = UDPServerConfig(
        bind_ip="0.0.0.0",
        bind_port=9000,
        custom_reply_data="aa55",
        hex_mode=True,
    )

    service.update_config(config)

    assert service.config.bind_ip == "0.0.0.0"
    assert service.config.bind_port == 9000
    assert service.config.custom_reply_data == "aa55"
    assert service.config.hex_mode is True


def test_track_client_addr_stores_latest_peer() -> None:
    service = UDPServerService()
    service.update_config(
        UDPServerConfig(
            bind_ip="0.0.0.0",
            bind_port=9000,
            custom_reply_data="reply",
            hex_mode=False,
        )
    )

    service.record_client_addr(("127.0.0.1", 50123))

    assert service.last_client_addr == ("127.0.0.1", 50123)


@pytest.mark.anyio
async def test_handle_datagram_replies_immediately_to_device(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UDPServerService()
    service.update_config(
        UDPServerConfig(
            bind_ip="0.0.0.0",
            bind_port=9000,
            custom_reply_data="reply",
            hex_mode=False,
        )
    )

    sent_payloads: list[tuple[bytes, tuple[str, int], str, tuple[str, int] | None]] = []
    persisted: list[tuple[str, tuple[str, int], tuple[str, int], bytes]] = []
    logs: list[tuple[str, str, str, str]] = []

    async def fake_send_payload(
        payload: bytes,
        target: tuple[str, int],
        direction: str,
        source: tuple[str, int] | None = None,
    ) -> None:
        sent_payloads.append((payload, target, direction, source))

    monkeypatch.setattr(service, "_send_payload", fake_send_payload)
    monkeypatch.setattr(service, "_persist_packet", lambda direction, src, dst, payload: persisted.append((direction, src, dst, payload)))
    monkeypatch.setattr(service, "emit_system_log", lambda level, category, message, detail="": logs.append((level, category, message, detail)))

    await service.handle_datagram(b"ping", ("10.1.2.3", 4567))

    assert service.rx_count == 4
    assert service.last_client_addr == ("10.1.2.3", 4567)
    assert persisted == [
        ("device -> server", ("10.1.2.3", 4567), ("0.0.0.0", 9000), b"ping"),
    ]
    assert sent_payloads == [
        (b"reply", ("10.1.2.3", 4567), "server -> device", ("10.1.2.3", 4567)),
    ]
    assert logs[0][:3] == ("info", "rule", "device -> server 10.1.2.3:4567")


@pytest.mark.anyio
async def test_handle_datagram_warns_when_reply_payload_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UDPServerService()
    service.update_config(
        UDPServerConfig(
            bind_ip="0.0.0.0",
            bind_port=9000,
            custom_reply_data="",
            hex_mode=False,
        )
    )

    sent_payloads: list[tuple[bytes, tuple[str, int], str, tuple[str, int] | None]] = []
    logs: list[tuple[str, str, str, str]] = []

    async def fake_send_payload(
        payload: bytes,
        target: tuple[str, int],
        direction: str,
        source: tuple[str, int] | None = None,
    ) -> None:
        sent_payloads.append((payload, target, direction, source))

    monkeypatch.setattr(service, "_send_payload", fake_send_payload)
    monkeypatch.setattr(service, "_persist_packet", lambda direction, src, dst, payload: None)
    monkeypatch.setattr(service, "emit_system_log", lambda level, category, message, detail="": logs.append((level, category, message, detail)))

    await service.handle_datagram(b"ping", ("10.1.2.3", 4567))

    assert sent_payloads == []
    assert logs[-1][:3] == ("warning", "rule", "UDP packet received but custom reply payload is empty")


@pytest.mark.anyio
async def test_udp_service_replies_over_real_socket(tmp_path) -> None:
    db_path = tmp_path / "udp-service.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    service = UDPServerService(db_factory=testing_session_local)
    service.update_config(
        UDPServerConfig(
            bind_ip="127.0.0.1",
            bind_port=0,
            custom_reply_data="pong",
            hex_mode=False,
        )
    )

    import socket

    await service.start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.setblocking(False)

    try:
        loop = __import__("asyncio").get_running_loop()
        server_addr = service.transport.get_extra_info("sockname")
        sock.sendto(b"ping", server_addr)
        data, _ = await loop.sock_recvfrom(sock, 1024)

        assert data == b"pong"
        assert service.last_client_addr is not None
        assert service.rx_count == 4
        assert service.tx_count == 4

        with testing_session_local() as db:
            packet_rows = db.query(PacketLog).order_by(PacketLog.id.asc()).all()

        assert [row.direction for row in packet_rows] == ["device -> server", "server -> device"]
        assert packet_rows[0].data_text == "ping"
        assert packet_rows[1].data_text == "pong"
    finally:
        sock.close()
        await service.stop()
