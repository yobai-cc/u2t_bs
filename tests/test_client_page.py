import warnings

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.db import Base
from app.models.service_config import ServiceConfig
from app.models.user import User
from app.services.client_runtime import ClientRuntimeConfig
from app.services.runtime_manager import runtime_manager


def test_client_page_replaces_placeholder_and_persists_config(tmp_path) -> None:
    from app.routers.pages import client_page, update_client_config

    db_path = tmp_path / "client-page.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    request = Request({"type": "http", "method": "GET", "path": "/client", "headers": [], "query_string": b""})
    user = User(username="client-admin", password_hash="x", role="admin", is_active=True)

    try:
        response = client_page(request, user)
        body = response.body.decode("utf-8")
        assert "TCP/UDP Client" in body
        assert "第二阶段实现" not in body

        with testing_session_local() as db:
            post_response = update_client_config(
                request,
                protocol="UDP",
                target_ip="127.0.0.1",
                target_port=9201,
                hex_mode="on",
                user=user,
                db=db,
            )
            post_body = post_response.body.decode("utf-8")
            assert "UDP" in post_body
            assert "9201" in post_body

        with Session(engine) as db:
            row = db.query(ServiceConfig).filter(ServiceConfig.name == "client_runtime").one()
            assert row.service_type == "client"
            assert row.target_ip == "127.0.0.1"
            assert row.target_port == 9201
            assert row.enabled is False
            assert row.config_json["protocol"] == "UDP"
            assert row.config_json["hex_mode"] is True
    finally:
        runtime_manager.client_runtime.update_config(ClientRuntimeConfig())


def test_client_page_hides_mutations_for_viewer() -> None:
    from app.routers.pages import client_page

    request = Request({"type": "http", "method": "GET", "path": "/client", "headers": [], "query_string": b""})
    viewer = User(username="viewer-user", password_hash="x", role="viewer", is_active=True)

    response = client_page(request, viewer)
    body = response.body.decode("utf-8")

    assert "Viewer 角色仅可查看 Client 运行状态。" in body
    assert "/client/config" not in body
    assert "/client/connect" not in body
    assert "/client/disconnect" not in body
    assert "/client/send" not in body


def test_client_routes_do_not_emit_template_deprecation_warning() -> None:
    from app.routers.pages import client_page

    user = User(username="admin-user", password_hash="x", role="admin", is_active=True)
    request = Request({"type": "http", "method": "GET", "path": "/client", "headers": [], "query_string": b""})

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response = client_page(request, user)
        _ = response.body.decode("utf-8")

    messages = [str(item.message) for item in caught]
    assert not any("The `name` is not the first parameter anymore" in message for message in messages)


@pytest.mark.anyio
async def test_client_connect_send_disconnect_routes_update_persisted_snapshot(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers.pages import connect_client, disconnect_client, send_client_manual

    db_path = tmp_path / "client-routes.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    user = User(username="operator-user", password_hash="x", role="operator", is_active=True)
    request = Request({"type": "http", "method": "POST", "path": "/client/send", "headers": [], "query_string": b""})
    packets: list[dict[str, object]] = []
    logs: list[tuple[str, str, str, str]] = []

    monkeypatch.setattr(
        "app.services.client_runtime.packet_logger.log_packet",
        lambda **kwargs: packets.append(kwargs),
    )
    monkeypatch.setattr(
        "app.services.client_runtime.system_log_service.log_to_db",
        lambda level, category, message, detail="", db=None: logs.append((level, category, message, detail)),
    )

    async def handle_client(reader, writer) -> None:
        data = await reader.read(4096)
        writer.write(data.upper())
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    import asyncio

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    sockname = server.sockets[0].getsockname()
    runtime_manager.apply_client_config(
        {"protocol": "TCP", "target_ip": "127.0.0.1", "target_port": sockname[1], "hex_mode": False}
    )

    try:
        with testing_session_local() as db:
            connect_response = await connect_client(request, user=user, db=db)
            assert "Client 已连接" in connect_response.body.decode("utf-8")

        with testing_session_local() as db:
            send_response = await send_client_manual(request, payload="ping", user=user, db=db)
            assert "Client 手动发送已触发" in send_response.body.decode("utf-8")

        for _ in range(20):
            if runtime_manager.client_snapshot()["rx_count"] == 4:
                break
            await asyncio.sleep(0.01)

        with testing_session_local() as db:
            row = db.query(ServiceConfig).filter(ServiceConfig.name == "client_runtime").one()
            assert row.enabled is True
            assert row.config_json["tx_count"] == 4
            assert row.config_json["rx_count"] == 0

        with testing_session_local() as db:
            disconnect_response = await disconnect_client(request, user=user, db=db)
            assert "Client 已断开" in disconnect_response.body.decode("utf-8")

        with testing_session_local() as db:
            row = db.query(ServiceConfig).filter(ServiceConfig.name == "client_runtime").one()
            assert row.enabled is False
            assert row.config_json["tx_count"] == 4
            assert row.config_json["rx_count"] == 4

        assert packets[0]["direction"] == "client -> remote"
        assert packets[-1]["direction"] == "remote -> client"
        assert any("Client connected by operator-user" in message for _, _, message, _ in logs)
    finally:
        await runtime_manager.client_runtime.disconnect()
        runtime_manager.client_runtime.update_config(ClientRuntimeConfig())
        server.close()
        await server.wait_closed()
