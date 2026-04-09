from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.db import Base
from app.models.packet_log import PacketLog
from app.models.system_log import SystemLog
from app.models.user import User


def test_packets_page_filters_by_service_and_direction(tmp_path) -> None:
    from app.routers.pages import packets

    db_path = tmp_path / "packets-filters.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        db.add_all(
            [
                PacketLog(
                    service_type="client",
                    protocol="TCP",
                    direction="client -> remote",
                    src_ip="127.0.0.1",
                    src_port=10001,
                    dst_ip="127.0.0.1",
                    dst_port=9001,
                    data_hex="70 69 6e 67",
                    data_text="ping",
                    length=4,
                ),
                PacketLog(
                    service_type="tcp_server",
                    protocol="TCP",
                    direction="remote -> server",
                    src_ip="10.0.0.2",
                    src_port=12345,
                    dst_ip="10.0.0.1",
                    dst_port=9100,
                    data_hex="70 6f 6e 67",
                    data_text="pong",
                    length=4,
                ),
            ]
        )
        db.commit()

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/packets",
            "headers": [],
            "query_string": b"protocol=TCP&service=client&direction=client+-%3E+remote&limit=50",
        }
    )
    user = User(username="viewer-user", password_hash="x", role="viewer", is_active=True)

    with testing_session_local() as db:
        response = packets(
            request,
            protocol="TCP",
            service="client",
            direction="client -> remote",
            limit=50,
            user=user,
            db=db,
        )

    body = response.body.decode("utf-8")
    assert "client" in body
    assert "ping" in body
    assert "<td>tcp_server</td>" not in body
    assert "pong" not in body


def test_packets_page_keyword_matches_text_and_ip(tmp_path) -> None:
    from app.routers.pages import packets

    db_path = tmp_path / "packets-keyword.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        db.add_all(
            [
                PacketLog(
                    service_type="client",
                    protocol="UDP",
                    direction="client -> remote",
                    src_ip="192.168.1.10",
                    src_port=5000,
                    dst_ip="8.8.8.8",
                    dst_port=53,
                    data_hex="71 75 65 72 79",
                    data_text="query dns",
                    length=9,
                ),
                PacketLog(
                    service_type="udp_server",
                    protocol="UDP",
                    direction="remote -> server",
                    src_ip="10.10.10.10",
                    src_port=2000,
                    dst_ip="10.0.0.1",
                    dst_port=9000,
                    data_hex="72 65 70 6c 79",
                    data_text="pong",
                    length=5,
                ),
            ]
        )
        db.commit()

    request = Request({"type": "http", "method": "GET", "path": "/packets", "headers": [], "query_string": b"q=192.168&limit=50"})
    user = User(username="viewer-user", password_hash="x", role="viewer", is_active=True)

    with testing_session_local() as db:
        response = packets(
            request,
            protocol=None,
            service=None,
            direction=None,
            q="192.168",
            limit=50,
            user=user,
            db=db,
        )

    body = response.body.decode("utf-8")
    assert "query dns" in body
    assert "pong" not in body


def test_packets_page_lists_udp_device_directions() -> None:
    from app.routers.pages import packets

    request = Request({"type": "http", "method": "GET", "path": "/packets", "headers": [], "query_string": b""})
    user = User(username="viewer-user", password_hash="x", role="viewer", is_active=True)

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as db:
        response = packets(request, protocol=None, service=None, direction=None, q=None, limit=50, user=user, db=db)

    body = response.body.decode("utf-8")
    assert "device -> server" in body
    assert "server -> device" in body
    assert "cloud -> server" not in body


def test_logs_page_filters_by_level_and_category(tmp_path) -> None:
    from app.routers.pages import logs

    db_path = tmp_path / "logs-filters.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        db.add_all(
            [
                SystemLog(level="warning", category="auth", message="Login failed", detail="bad password"),
                SystemLog(level="info", category="service", message="Client connected", detail="127.0.0.1:9001"),
            ]
        )
        db.commit()

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/logs",
            "headers": [],
            "query_string": b"level=warning&category=auth&limit=50",
        }
    )
    user = User(username="viewer-user", password_hash="x", role="viewer", is_active=True)

    with testing_session_local() as db:
        response = logs(request, level="warning", category="auth", q=None, limit=50, user=user, db=db)

    body = response.body.decode("utf-8")
    assert "Login failed" in body
    assert "Client connected" not in body


def test_logs_page_keyword_matches_message_and_detail(tmp_path) -> None:
    from app.routers.pages import logs

    db_path = tmp_path / "logs-keyword.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        db.add_all(
            [
                SystemLog(level="error", category="network", message="Connect failed", detail="target 10.0.0.8:9001 refused"),
                SystemLog(level="info", category="service", message="UDP server started", detail="bind 0.0.0.0:9000"),
            ]
        )
        db.commit()

    request = Request({"type": "http", "method": "GET", "path": "/logs", "headers": [], "query_string": b"q=refused&limit=50"})
    user = User(username="viewer-user", password_hash="x", role="viewer", is_active=True)

    with testing_session_local() as db:
        response = logs(request, level=None, category=None, q="refused", limit=50, user=user, db=db)

    body = response.body.decode("utf-8")
    assert "Connect failed" in body
    assert "UDP server started" not in body
