import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.db import Base
from app.models.user import User
from app.services.runtime_manager import runtime_manager
from app.services.udp_server import UDPRelayConfig


@pytest.mark.anyio
async def test_udp_route_failures_render_error_and_write_system_log(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers.pages import send_udp_manual, start_udp_server, stop_udp_server

    db_path = tmp_path / "udp-route-failures.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    user = User(username="operator-user", password_hash="x", role="operator", is_active=True)
    request = Request({"type": "http", "method": "POST", "path": "/udp-server/start", "headers": [], "query_string": b""})
    logs: list[tuple[str, str, str, str]] = []

    monkeypatch.setattr(
        "app.routers.pages.system_log_service.log_to_db",
        lambda level, category, message, detail="", db=None: logs.append((level, category, message, detail)),
    )

    async def boom_start() -> None:
        raise RuntimeError("bind failed")

    async def boom_stop() -> None:
        raise RuntimeError("close failed")

    async def boom_send(payload: str) -> None:
        raise RuntimeError("UDP server is not running")

    monkeypatch.setattr(runtime_manager.udp_relay, "start", boom_start)
    monkeypatch.setattr(runtime_manager.udp_relay, "stop", boom_stop)
    monkeypatch.setattr(runtime_manager.udp_relay, "send_manual", boom_send)

    try:
        runtime_manager.udp_relay.update_config(
            UDPRelayConfig(
                bind_ip="127.0.0.1",
                bind_port=9000,
                custom_reply_data="",
                hex_mode=False,
            )
        )

        with testing_session_local() as db:
            start_response = await start_udp_server(request, user=user, db=db)
            start_body = start_response.body.decode("utf-8")
            assert "alert error" in start_body
            assert "UDP 服务启动失败：bind failed" in start_body

        assert logs[-1] == ("error", "service", "UDP server start failed by operator-user", "bind failed")

        with testing_session_local() as db:
            send_response = await send_udp_manual(request, payload="ping", user=user, db=db)
            send_body = send_response.body.decode("utf-8")
            assert "alert error" in send_body
            assert "UDP 手动发送失败：UDP server is not running" in send_body

        assert logs[-1] == (
            "error",
            "network",
            "Manual UDP payload send failed by operator-user",
            "UDP server is not running",
        )

        with testing_session_local() as db:
            stop_response = await stop_udp_server(request, user=user, db=db)
            stop_body = stop_response.body.decode("utf-8")
            assert "alert error" in stop_body
            assert "UDP 服务停止失败：close failed" in stop_body

        assert logs[-1] == ("error", "service", "UDP server stop failed by operator-user", "close failed")
    finally:
        runtime_manager.udp_relay.running = False
        runtime_manager.udp_relay.transport = None
        runtime_manager.udp_relay.protocol = None
        runtime_manager.udp_relay.last_client_addr = None
        runtime_manager.udp_relay.update_config(UDPRelayConfig())


def test_update_udp_config_accepts_bind_and_reply_fields_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers.pages import update_udp_config

    user = User(username="operator-user", password_hash="x", role="operator", is_active=True)
    request = Request({"type": "http", "method": "POST", "path": "/udp-server/config", "headers": [], "query_string": b""})

    captured_payload: list[dict[str, object]] = []
    snapshots: list[dict[str, object]] = [
        {
            "running": False,
            "bind_ip": "127.0.0.1",
            "bind_port": 9000,
            "custom_reply_data": "reply",
            "hex_mode": True,
            "tx_count": 0,
            "rx_count": 0,
            "last_client_addr": None,
        }
    ]
    logs: list[tuple[str, str, str, str]] = []

    monkeypatch.setattr(runtime_manager, "apply_udp_config", lambda payload: captured_payload.append(payload) or UDPRelayConfig(**payload))
    monkeypatch.setattr(runtime_manager, "udp_snapshot", lambda: snapshots[-1])
    monkeypatch.setattr("app.routers.pages._save_udp_config", lambda db, snapshot: None)
    monkeypatch.setattr(
        "app.routers.pages.system_log_service.log_to_db",
        lambda level, category, message, detail="", db=None: logs.append((level, category, message, detail)),
    )

    response = update_udp_config(
        request,
        bind_ip="127.0.0.1",
        bind_port=9000,
        custom_reply_data="reply",
        hex_mode="on",
        user=user,
        db=None,
    )

    body = response.body.decode("utf-8")
    assert captured_payload == [
        {
            "bind_ip": "127.0.0.1",
            "bind_port": 9000,
            "custom_reply_data": "reply",
            "hex_mode": True,
        }
    ]
    assert "自动回复数据" in body
    assert "云端 IP" not in body
    assert "UDP 配置已更新" in body
    assert logs[-1] == ("info", "config", "UDP config updated by operator-user", "")
