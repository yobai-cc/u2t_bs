from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_role
from app.auth.security import hash_password
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


def _users_context(request: Request, user: User, db: Session) -> dict[str, object]:
    context = _base_context(request, user)
    context["users"] = db.query(User).order_by(User.id.asc()).all()
    return context


def _runtime_error(
    request: Request,
    user: User,
    template_name: str,
    context_key: str,
    snapshot: dict[str, object],
    error_message: str,
):
    context = _base_context(request, user)
    context[context_key] = snapshot
    context["error"] = error_message
    return templates.TemplateResponse(request, template_name, context)


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
    row.target_ip = None
    row.target_port = None
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
    custom_reply_data: str = Form(""),
    hex_mode: str | None = Form(default=None),
    user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
 ):
    runtime_manager.apply_udp_config(
        {
            "bind_ip": bind_ip,
            "bind_port": bind_port,
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
    try:
        await runtime_manager.udp_relay.start()
    except Exception as exc:
        system_log_service.log_to_db("error", "service", f"UDP server start failed by {user.username}", str(exc), db=db)
        return _runtime_error(
            request,
            user,
            "udp_server.html",
            "udp",
            runtime_manager.udp_snapshot(),
            f"UDP 服务启动失败：{exc}",
        )

    snapshot = runtime_manager.udp_snapshot()
    _save_udp_config(db, snapshot)
    system_log_service.log_to_db("info", "service", f"UDP server started by {user.username}", db=db)
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
    try:
        await runtime_manager.udp_relay.stop()
    except Exception as exc:
        system_log_service.log_to_db("error", "service", f"UDP server stop failed by {user.username}", str(exc), db=db)
        return _runtime_error(
            request,
            user,
            "udp_server.html",
            "udp",
            runtime_manager.udp_snapshot(),
            f"UDP 服务停止失败：{exc}",
        )

    snapshot = runtime_manager.udp_snapshot()
    _save_udp_config(db, snapshot)
    system_log_service.log_to_db("info", "service", f"UDP server stopped by {user.username}", db=db)
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
    try:
        await runtime_manager.udp_relay.send_manual(payload)
    except Exception as exc:
        system_log_service.log_to_db(
            "error", "network", f"Manual UDP payload send failed by {user.username}", str(exc), db=db
        )
        return _runtime_error(
            request,
            user,
            "udp_server.html",
            "udp",
            runtime_manager.udp_snapshot(),
            f"UDP 手动发送失败：{exc}",
        )

    system_log_service.log_to_db("info", "network", f"Manual UDP payload sent by {user.username}", db=db)
    context = _base_context(request, user)
    context["udp"] = runtime_manager.udp_snapshot()
    context["message"] = "手动发送已触发"
    return templates.TemplateResponse(request, "udp_server.html", context)


@router.get("/packets", response_class=HTMLResponse)
def packets(
    request: Request,
    protocol: str | None = None,
    service: str | None = None,
    direction: str | None = None,
    q: str | None = None,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(PacketLog)
    if protocol:
        query = query.filter(PacketLog.protocol == protocol)
    if service:
        query = query.filter(PacketLog.service_type == service)
    if direction:
        query = query.filter(PacketLog.direction == direction)
    if q:
        search = f"%{q.strip()}%"
        query = query.filter(
            or_(
                PacketLog.data_text.ilike(search),
                PacketLog.data_hex.ilike(search),
                PacketLog.src_ip.ilike(search),
                PacketLog.dst_ip.ilike(search),
            )
        )
    rows = query.order_by(PacketLog.created_at.desc()).limit(limit).all()
    context = _base_context(request, user)
    context.update(
        {
            "packets": rows,
            "selected_protocol": protocol or "",
            "selected_service": service or "",
            "selected_direction": direction or "",
            "query_text": q or "",
            "limit": limit,
        }
    )
    return templates.TemplateResponse(request, "packets.html", context)


@router.get("/logs", response_class=HTMLResponse)
def logs(
    request: Request,
    level: str | None = None,
    category: str | None = None,
    q: str | None = None,
    limit: int = 200,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(SystemLog)
    if level:
        query = query.filter(SystemLog.level == level)
    if category:
        query = query.filter(SystemLog.category == category)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                SystemLog.message.ilike(like),
                SystemLog.detail.ilike(like),
            )
        )
    rows = query.order_by(SystemLog.created_at.desc()).limit(limit).all()
    context = _base_context(request, user)
    context.update(
        {
            "logs": rows,
            "selected_level": level or "",
            "selected_category": category or "",
            "query_text": q or "",
            "limit": limit,
        }
    )
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
    try:
        await runtime_manager.tcp_server.start()
    except Exception as exc:
        system_log_service.log_to_db("error", "service", f"TCP server start failed by {user.username}", str(exc), db=db)
        return _runtime_error(
            request,
            user,
            "tcp_server.html",
            "tcp",
            runtime_manager.tcp_snapshot(),
            f"TCP 服务启动失败：{exc}",
        )

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
    try:
        await runtime_manager.tcp_server.stop()
    except Exception as exc:
        system_log_service.log_to_db("error", "service", f"TCP server stop failed by {user.username}", str(exc), db=db)
        return _runtime_error(
            request,
            user,
            "tcp_server.html",
            "tcp",
            runtime_manager.tcp_snapshot(),
            f"TCP 服务停止失败：{exc}",
        )

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
    try:
        await runtime_manager.tcp_server.send_manual(client_id, payload)
    except Exception as exc:
        system_log_service.log_to_db(
            "error",
            "network",
            f"Manual TCP payload send failed by {user.username} to {client_id}",
            str(exc),
            db=db,
        )
        return _runtime_error(
            request,
            user,
            "tcp_server.html",
            "tcp",
            runtime_manager.tcp_snapshot(),
            f"TCP 发送失败：{exc}",
        )

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
    try:
        await runtime_manager.tcp_server.disconnect_client(client_id)
    except Exception as exc:
        system_log_service.log_to_db(
            "error", "service", f"TCP client disconnect failed {client_id} by {user.username}", str(exc), db=db
        )
        return _runtime_error(
            request,
            user,
            "tcp_server.html",
            "tcp",
            runtime_manager.tcp_snapshot(),
            f"TCP 客户端断开失败：{exc}",
        )

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
    if runtime_manager.client_runtime.running:
        return _runtime_error(
            request,
            user,
            "client.html",
            "client",
            runtime_manager.client_snapshot(),
            "Client 正在运行，请先断开再修改配置",
        )

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
    try:
        await runtime_manager.client_runtime.connect()
    except Exception as exc:
        system_log_service.log_to_db("error", "service", f"Client connect failed by {user.username}", str(exc), db=db)
        return _runtime_error(
            request,
            user,
            "client.html",
            "client",
            runtime_manager.client_snapshot(),
            f"Client 连接失败：{exc}",
        )

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
    try:
        await runtime_manager.client_runtime.disconnect()
    except Exception as exc:
        system_log_service.log_to_db("error", "service", f"Client disconnect failed by {user.username}", str(exc), db=db)
        return _runtime_error(
            request,
            user,
            "client.html",
            "client",
            runtime_manager.client_snapshot(),
            f"Client 断开失败：{exc}",
        )

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
    try:
        await runtime_manager.client_runtime.send_manual(payload)
    except Exception as exc:
        system_log_service.log_to_db(
            "error", "network", f"Manual client payload send failed by {user.username}", str(exc), db=db
        )
        return _runtime_error(
            request,
            user,
            "client.html",
            "client",
            runtime_manager.client_snapshot(),
            f"Client 发送失败：{exc}",
        )

    snapshot = runtime_manager.client_snapshot()
    _save_client_config(db, snapshot)
    system_log_service.log_to_db("info", "network", f"Manual client payload sent by {user.username}", db=db)
    context = _base_context(request, user)
    context["client"] = snapshot
    context["message"] = "Client 手动发送已触发"
    return templates.TemplateResponse(request, "client.html", context)


@router.get("/users", response_class=HTMLResponse)
def users_page(
    request: Request,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    context = _users_context(request, user, db)
    return templates.TemplateResponse(request, "users.html", context)


@router.post("/users/create", response_class=HTMLResponse)
def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    username = username.strip()
    allowed_roles = {"admin", "operator", "viewer"}

    context = _users_context(request, user, db)
    if not username or not password:
        context["error"] = "用户名和密码不能为空"
        return templates.TemplateResponse(request, "users.html", context)
    if role not in allowed_roles:
        context["error"] = "角色不合法"
        return templates.TemplateResponse(request, "users.html", context)
    if db.query(User).filter(User.username == username).first() is not None:
        context["error"] = "用户名已存在"
        return templates.TemplateResponse(request, "users.html", context)

    row = User(username=username, password_hash=hash_password(password), role=role, is_active=True)
    db.add(row)
    db.commit()
    system_log_service.log_to_db("info", "auth", f"User {username} created by {user.username}", db=db)

    context = _users_context(request, user, db)
    context["message"] = "用户已创建"
    return templates.TemplateResponse(request, "users.html", context)


@router.post("/users/toggle", response_class=HTMLResponse)
def toggle_user(
    request: Request,
    user_id: int = Form(...),
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    context = _users_context(request, user, db)
    target = db.get(User, user_id)
    if target is None:
        context["error"] = "用户不存在"
        return templates.TemplateResponse(request, "users.html", context)

    if target.is_active:
        if target.id == user.id:
            context["error"] = "不能禁用当前登录账号"
            return templates.TemplateResponse(request, "users.html", context)

        if target.role == "admin":
            active_admin_count = db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()
            if active_admin_count <= 1:
                context["error"] = "至少保留一个启用中的 admin"
                return templates.TemplateResponse(request, "users.html", context)

        target.is_active = False
        message = "用户已禁用"
        log_message = f"User {target.username} disabled by {user.username}"
    else:
        target.is_active = True
        message = "用户已启用"
        log_message = f"User {target.username} enabled by {user.username}"

    db.add(target)
    db.commit()
    system_log_service.log_to_db("info", "auth", log_message, db=db)

    context = _users_context(request, user, db)
    context["message"] = message
    return templates.TemplateResponse(request, "users.html", context)
