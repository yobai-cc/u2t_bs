from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_role
from app.db import get_db
from app.models.packet_log import PacketLog
from app.models.service_config import ServiceConfig
from app.models.system_log import SystemLog
from app.models.user import User
from app.services.logging_service import system_log_service
from app.services.runtime_manager import runtime_manager


router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def _base_context(request: Request, user: User) -> dict[str, object]:
    return {"request": request, "current_user": user}


def _save_udp_config(db: Session, snapshot: dict[str, object]) -> None:
    row = db.query(ServiceConfig).filter(ServiceConfig.name == "udp_relay").first()
    payload = {
        "custom_reply_data": snapshot["custom_reply_data"],
        "hex_mode": snapshot["hex_mode"],
        "last_client_addr": snapshot["last_client_addr"],
        "tx_count": snapshot["tx_count"],
        "rx_count": snapshot["rx_count"],
    }
    if row is None:
        row = ServiceConfig(name="udp_relay", service_type="udp_server")
        db.add(row)

    row.bind_ip = str(snapshot["bind_ip"])
    row.bind_port = int(snapshot["bind_port"])
    row.target_ip = str(snapshot["cloud_ip"])
    row.target_port = int(snapshot["cloud_port"])
    row.enabled = bool(snapshot["running"])
    row.config_json = payload
    db.commit()


def _save_tcp_config(db: Session, snapshot: dict[str, object]) -> None:
    row = db.query(ServiceConfig).filter(ServiceConfig.name == "tcp_server").first()
    payload = {
        "hex_mode": snapshot["hex_mode"],
        "tx_count": snapshot["tx_count"],
        "rx_count": snapshot["rx_count"],
    }
    if row is None:
        row = ServiceConfig(name="tcp_server", service_type="tcp_server")
        db.add(row)

    row.bind_ip = str(snapshot["bind_ip"])
    row.bind_port = int(snapshot["bind_port"])
    row.target_ip = None
    row.target_port = None
    row.enabled = bool(snapshot["running"])
    row.config_json = payload
    db.commit()


def _save_client_config(db: Session, snapshot: dict[str, object]) -> None:
    row = db.query(ServiceConfig).filter(ServiceConfig.name == "client_runtime").first()
    payload = {
        "protocol": snapshot["protocol"],
        "hex_mode": snapshot["hex_mode"],
        "tx_count": snapshot["tx_count"],
        "rx_count": snapshot["rx_count"],
        "peer_label": snapshot["peer_label"],
    }
    if row is None:
        row = ServiceConfig(name="client_runtime", service_type="client")
        db.add(row)

    row.bind_ip = "0.0.0.0"
    row.bind_port = 0
    row.target_ip = str(snapshot["target_ip"])
    row.target_port = int(snapshot["target_port"])
    row.enabled = bool(snapshot["connected"])
    row.config_json = payload
    db.commit()


@router.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    context = _base_context(request, user)
    context.update(
        {
            "udp": runtime_manager.udp_snapshot(),
            "packet_count": db.query(PacketLog).count(),
            "system_log_count": db.query(SystemLog).count(),
        }
    )
    return templates.TemplateResponse(request, "dashboard.html", context)


@router.get("/udp-server", response_class=HTMLResponse)
def udp_server_page(request: Request, user: User = Depends(get_current_user)):
    context = _base_context(request, user)
    context["udp"] = runtime_manager.udp_snapshot()
    return templates.TemplateResponse(request, "udp_server.html", context)


@router.post("/udp-server/config", response_class=HTMLResponse)
def update_udp_config(
    request: Request,
    bind_ip: str = Form(...),
    bind_port: int = Form(...),
    cloud_ip: str = Form(...),
    cloud_port: int = Form(...),
    custom_reply_data: str = Form(""),
    hex_mode: str | None = Form(default=None),
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
 ):
    runtime_manager.apply_udp_config(
        {
            "bind_ip": bind_ip,
            "bind_port": bind_port,
            "cloud_ip": cloud_ip,
            "cloud_port": cloud_port,
            "custom_reply_data": custom_reply_data,
            "hex_mode": hex_mode == "on",
        }
    )
    snapshot = runtime_manager.udp_snapshot()
    _save_udp_config(db, snapshot)
    system_log_service.log_to_db("info", "config", f"UDP config updated by {user.username}", db=db)
    context = _base_context(request, user)
    context["udp"] = snapshot
    context["message"] = "UDP 配置已更新"
    return templates.TemplateResponse(request, "udp_server.html", context)


@router.post("/udp-server/start", response_class=HTMLResponse)
async def start_udp_server(
    request: Request,
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    await runtime_manager.udp_relay.start()
    snapshot = runtime_manager.udp_snapshot()
    _save_udp_config(db, snapshot)
    system_log_service.log_to_db("info", "service", f"UDP relay started by {user.username}", db=db)
    context = _base_context(request, user)
    context["udp"] = snapshot
    context["message"] = "UDP 服务已启动"
    return templates.TemplateResponse(request, "udp_server.html", context)


@router.post("/udp-server/stop", response_class=HTMLResponse)
async def stop_udp_server(
    request: Request,
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    await runtime_manager.udp_relay.stop()
    snapshot = runtime_manager.udp_snapshot()
    _save_udp_config(db, snapshot)
    system_log_service.log_to_db("info", "service", f"UDP relay stopped by {user.username}", db=db)
    context = _base_context(request, user)
    context["udp"] = snapshot
    context["message"] = "UDP 服务已停止"
    return templates.TemplateResponse(request, "udp_server.html", context)


@router.post("/udp-server/send", response_class=HTMLResponse)
async def send_udp_manual(
    request: Request,
    payload: str = Form(""),
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    await runtime_manager.udp_relay.send_manual(payload)
    system_log_service.log_to_db("info", "network", f"Manual UDP payload sent by {user.username}", db=db)
    context = _base_context(request, user)
    context["udp"] = runtime_manager.udp_snapshot()
    context["message"] = "手动发送已触发"
    return templates.TemplateResponse(request, "udp_server.html", context)


@router.get("/packets", response_class=HTMLResponse)
def packets(
    request: Request,
    protocol: str | None = None,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(PacketLog)
    if protocol:
        query = query.filter(PacketLog.protocol == protocol)
    rows = query.order_by(PacketLog.created_at.desc()).limit(limit).all()
    context = _base_context(request, user)
    context.update({"packets": rows, "selected_protocol": protocol or "", "limit": limit})
    return templates.TemplateResponse(request, "packets.html", context)


@router.get("/logs", response_class=HTMLResponse)
def logs(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(SystemLog).order_by(SystemLog.created_at.desc()).limit(200).all()
    context = _base_context(request, user)
    context["logs"] = rows
    return templates.TemplateResponse(request, "logs.html", context)


@router.get("/tcp-server", response_class=HTMLResponse)
def tcp_server_page(request: Request, user: User = Depends(get_current_user)):
    context = _base_context(request, user)
    context["tcp"] = runtime_manager.tcp_snapshot()
    return templates.TemplateResponse(request, "tcp_server.html", context)


@router.post("/tcp-server/config", response_class=HTMLResponse)
def update_tcp_config(
    request: Request,
    bind_ip: str = Form(...),
    bind_port: int = Form(...),
    hex_mode: str | None = Form(default=None),
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    runtime_manager.apply_tcp_config(
        {
            "bind_ip": bind_ip,
            "bind_port": bind_port,
            "hex_mode": hex_mode == "on",
        }
    )
    snapshot = runtime_manager.tcp_snapshot()
    _save_tcp_config(db, snapshot)
    system_log_service.log_to_db("info", "config", f"TCP config updated by {user.username}", db=db)
    context = _base_context(request, user)
    context["tcp"] = snapshot
    context["message"] = "TCP 配置已更新"
    return templates.TemplateResponse(request, "tcp_server.html", context)


@router.post("/tcp-server/start", response_class=HTMLResponse)
async def start_tcp_server(
    request: Request,
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    await runtime_manager.tcp_server.start()
    snapshot = runtime_manager.tcp_snapshot()
    _save_tcp_config(db, snapshot)
    system_log_service.log_to_db("info", "service", f"TCP server started by {user.username}", db=db)
    context = _base_context(request, user)
    context["tcp"] = snapshot
    context["message"] = "TCP 服务已启动"
    return templates.TemplateResponse(request, "tcp_server.html", context)


@router.post("/tcp-server/stop", response_class=HTMLResponse)
async def stop_tcp_server(
    request: Request,
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    await runtime_manager.tcp_server.stop()
    snapshot = runtime_manager.tcp_snapshot()
    _save_tcp_config(db, snapshot)
    system_log_service.log_to_db("info", "service", f"TCP server stopped by {user.username}", db=db)
    context = _base_context(request, user)
    context["tcp"] = snapshot
    context["message"] = "TCP 服务已停止"
    return templates.TemplateResponse(request, "tcp_server.html", context)


@router.post("/tcp-server/send", response_class=HTMLResponse)
async def send_tcp_manual(
    request: Request,
    client_id: str = Form(...),
    payload: str = Form(""),
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    await runtime_manager.tcp_server.send_manual(client_id, payload)
    snapshot = runtime_manager.tcp_snapshot()
    _save_tcp_config(db, snapshot)
    system_log_service.log_to_db("info", "network", f"Manual TCP payload sent by {user.username} to {client_id}", db=db)
    context = _base_context(request, user)
    context["tcp"] = snapshot
    context["message"] = "TCP 手动发送已触发"
    return templates.TemplateResponse(request, "tcp_server.html", context)


@router.post("/tcp-server/disconnect", response_class=HTMLResponse)
async def disconnect_tcp_client(
    request: Request,
    client_id: str = Form(...),
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    await runtime_manager.tcp_server.disconnect_client(client_id)
    snapshot = runtime_manager.tcp_snapshot()
    _save_tcp_config(db, snapshot)
    system_log_service.log_to_db("info", "service", f"TCP client disconnected {client_id} by {user.username}", db=db)
    context = _base_context(request, user)
    context["tcp"] = snapshot
    context["message"] = "TCP 客户端已断开"
    return templates.TemplateResponse(request, "tcp_server.html", context)


@router.get("/client", response_class=HTMLResponse)
def client_page(request: Request, user: User = Depends(get_current_user)):
    context = _base_context(request, user)
    context["client"] = runtime_manager.client_snapshot()
    return templates.TemplateResponse(request, "client.html", context)


@router.post("/client/config", response_class=HTMLResponse)
def update_client_config(
    request: Request,
    protocol: str = Form(...),
    target_ip: str = Form(...),
    target_port: int = Form(...),
    hex_mode: str | None = Form(default=None),
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    runtime_manager.apply_client_config(
        {
            "protocol": protocol,
            "target_ip": target_ip,
            "target_port": target_port,
            "hex_mode": hex_mode == "on",
        }
    )
    snapshot = runtime_manager.client_snapshot()
    _save_client_config(db, snapshot)
    system_log_service.log_to_db("info", "config", f"Client config updated by {user.username}", db=db)
    context = _base_context(request, user)
    context["client"] = snapshot
    context["message"] = "Client 配置已更新"
    return templates.TemplateResponse(request, "client.html", context)


@router.post("/client/connect", response_class=HTMLResponse)
async def connect_client(
    request: Request,
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    await runtime_manager.client_runtime.connect()
    snapshot = runtime_manager.client_snapshot()
    _save_client_config(db, snapshot)
    system_log_service.log_to_db("info", "service", f"Client connected by {user.username}", db=db)
    context = _base_context(request, user)
    context["client"] = snapshot
    context["message"] = "Client 已连接"
    return templates.TemplateResponse(request, "client.html", context)


@router.post("/client/disconnect", response_class=HTMLResponse)
async def disconnect_client(
    request: Request,
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    await runtime_manager.client_runtime.disconnect()
    snapshot = runtime_manager.client_snapshot()
    _save_client_config(db, snapshot)
    system_log_service.log_to_db("info", "service", f"Client disconnected by {user.username}", db=db)
    context = _base_context(request, user)
    context["client"] = snapshot
    context["message"] = "Client 已断开"
    return templates.TemplateResponse(request, "client.html", context)


@router.post("/client/send", response_class=HTMLResponse)
async def send_client_manual(
    request: Request,
    payload: str = Form(""),
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    await runtime_manager.client_runtime.send_manual(payload)
    snapshot = runtime_manager.client_snapshot()
    _save_client_config(db, snapshot)
    system_log_service.log_to_db("info", "network", f"Manual client payload sent by {user.username}", db=db)
    context = _base_context(request, user)
    context["client"] = snapshot
    context["message"] = "Client 手动发送已触发"
    return templates.TemplateResponse(request, "client.html", context)


@router.get("/users", response_class=HTMLResponse)
def users_placeholder(request: Request, user: User = Depends(require_role("admin"))):
    return templates.TemplateResponse(request, "placeholder.html", {**_base_context(request, user), "title": "用户管理", "message": "第二阶段实现"})
