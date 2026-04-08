# TCP Server MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal but usable TCP Server feature to the existing FastAPI monolith so authenticated users can start a TCP listener, inspect connected clients, send payloads to a selected client, disconnect clients, and view packet/system logs in the current web UI.

**Architecture:** Reuse the existing monolith pattern already established by the UDP relay: an in-process asyncio runtime service owned by `RuntimeManager`, server-rendered Jinja2 pages in `app/routers/pages.py`, persistence via `packet_logs` and `system_logs`, and role-guarded form actions. Keep the TCP implementation intentionally minimal for this phase: one listener, tracked active clients, manual send, disconnect, counters, and logging; do not add rule engines, timed send, or protocol parsing yet.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, SQLAlchemy, SQLite, asyncio streams, bcrypt, WebSocket, systemd, Caddy.

---

## Current Project Context

This repository already contains a working MVP for the web shell, authentication, UDP relay, packet logging, system logging, and Ubuntu-oriented deployment assets.

### Verified Current State

- FastAPI app import succeeds through `app.main:app`
- `scripts/preflight.py` returns `preflight ok`
- Focused tests currently pass:
  - `tests/test_codec.py`
  - `tests/test_udp_relay.py`
- Admin bootstrap works via `scripts/init_db.py`
- Web service starts on `127.0.0.1:8080`

### Existing Files You Must Read First

- `app/services/udp_server.py`
  Why: this is the runtime service pattern to mirror for TCP.
- `app/services/runtime_manager.py`
  Why: TCP runtime ownership should be added here next to UDP.
- `app/routers/pages.py`
  Why: existing page route and form handling patterns live here.
- `app/services/packet_logger.py`
  Why: TCP traffic must reuse the same application-level packet logging model.
- `app/services/logging_service.py`
  Why: startup/stop/send/disconnect/errors should emit system logs through the existing helper.
- `app/templates/udp_server.html`
  Why: this page establishes the current admin UI density and interaction pattern.
- `app/templates/placeholder.html`
  Why: `/tcp-server` currently points here and must be replaced.

### Existing Constraints To Preserve

- Keep a single-process monolith
- Do not add Redis, Celery, Docker-only deployment, or frontend build tooling
- Keep page rendering server-side with Jinja2
- Use plain forms or lightweight HTMX, not SPA patterns
- Persist configuration in `service_configs`
- Persist traffic in `packet_logs`
- Persist audit/error events in `system_logs`
- Keep deployment compatible with Ubuntu + systemd + Caddy

---

## MVP Scope For TCP Server

### In Scope

- Listener config: `bind_ip`, `bind_port`, `hex_mode`
- Start TCP listener
- Stop TCP listener
- Track connected clients in memory
- Show connected client list on `/tcp-server`
- Send manual payload to a selected client
- Disconnect a selected client
- Count TX/RX bytes
- Record packet logs for:
  - client -> server
  - server -> client
- Record system logs for:
  - start
  - stop
  - connect
  - disconnect
  - send
  - network errors
- Persist TCP config into `service_configs`

### Out Of Scope For This Phase

- Automatic reply rules
- Timed send
- Multi-listener management
- TCP client mode
- Per-client custom protocol decoding
- Binary framing or sticky-packet splitting logic
- WebSocket live client event stream beyond basic page refresh behavior

---

## Proposed Runtime Design

Create a new service in `app/services/tcp_server.py`.

### Suggested Types

```python
from dataclasses import dataclass


@dataclass(slots=True)
class TCPServerConfig:
    bind_ip: str = "0.0.0.0"
    bind_port: int = 9100
    hex_mode: bool = False


@dataclass(slots=True)
class TCPClientState:
    client_id: str
    peer_ip: str
    peer_port: int
    connected_at: str
    tx_count: int = 0
    rx_count: int = 0
```
```

### Suggested Service Shape

```python
class TCPServerService:
    def __init__(self, db_factory: Callable[[], Session] = SessionLocal) -> None: ...
    def update_config(self, config: TCPServerConfig) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send_manual(self, client_id: str, payload_text: str) -> None: ...
    async def disconnect_client(self, client_id: str) -> None: ...
    def snapshot(self) -> dict[str, object]: ...
```
```

### Internal State To Keep

- `config`
- `server: asyncio.AbstractServer | None`
- `running: bool`
- `clients: dict[str, TCPClientConnection]`
- `tx_count: int`
- `rx_count: int`

Where `TCPClientConnection` can remain an internal helper object holding:

- `StreamReader`
- `StreamWriter`
- peer address info
- per-client byte counters
- connected time

### Client Identity Rule

Use a deterministic string identifier for the UI and form submissions:

```python
client_id = f"{peer_ip}:{peer_port}"
```

That is enough for MVP. Do not add UUIDs unless later collisions become a real issue.

---

## Data And Logging Rules

### Packet Logging

For every TCP payload received from a client:

- service_type: `tcp_server`
- protocol: `TCP`
- direction: `client -> server`
- source: peer ip/port
- target: bind ip/port
- payload: raw bytes

For every manual send to a client:

- service_type: `tcp_server`
- protocol: `TCP`
- direction: `server -> client`
- source: bind ip/port
- target: peer ip/port
- payload: raw bytes

### System Logging

Emit through `system_log_service.log_to_db()` for:

- listener started
- listener stopped
- client connected
- client disconnected
- manual send
- socket read/write failures

### Config Persistence

Store TCP service config in `service_configs` with:

- `name="tcp_server"`
- `service_type="tcp_server"`
- `bind_ip`
- `bind_port`
- `enabled`
- `config_json={"hex_mode": bool, "tx_count": int, "rx_count": int}`

Mirror the existing UDP persistence pattern already in `app/routers/pages.py`.

---

## UI Requirements For `/tcp-server`

Replace the placeholder page with a real template.

### Page Sections

1. Listener config card
- bind ip input
- bind port input
- hex mode checkbox
- save config button

2. Runtime status card
- running yes/no
- total connected clients
- total TX bytes
- total RX bytes
- start button
- stop button

3. Client list table
- client id
- connected at
- per-client TX/RX
- send button target
- disconnect button

4. Manual send card
- selected client dropdown or hidden field via button action
- payload textarea
- send button

5. Recent runtime/log card
- keep minimal for MVP; page refresh is acceptable

### Role Rules

- `admin`: full access
- `operator`: full TCP operations access
- `viewer`: read-only page access, no start/stop/send/disconnect

---

## File Plan

### Create

- `app/services/tcp_server.py`
- `app/templates/tcp_server.html`
- `tests/test_tcp_server.py`

### Modify

- `app/services/runtime_manager.py`
- `app/routers/pages.py`
- `README.md`
- `docs/superpowers/plans/2026-04-08-web-tcp-udp-platform.md`

Optional only if needed after implementation starts:

- `app/static/app.js`
- `app/static/app.css`

---

## Task 1: Write TCP Runtime Tests First

**Files:**
- Create: `tests/test_tcp_server.py`

- [ ] **Step 1: Write a failing test for config update and snapshot shape**

```python
from app.services.tcp_server import TCPServerConfig, TCPServerService


def test_update_config_changes_snapshot_values() -> None:
    service = TCPServerService()
    service.update_config(TCPServerConfig(bind_ip="0.0.0.0", bind_port=9101, hex_mode=True))

    snapshot = service.snapshot()

    assert snapshot["bind_ip"] == "0.0.0.0"
    assert snapshot["bind_port"] == 9101
    assert snapshot["hex_mode"] is True
    assert snapshot["running"] is False
    assert snapshot["clients"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_tcp_server.py::test_update_config_changes_snapshot_values -v
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` because `app.services.tcp_server` does not exist yet.

- [ ] **Step 3: Write a failing test for deterministic client id formatting**

```python
from app.services.tcp_server import TCPServerService


def test_make_client_id_uses_ip_and_port() -> None:
    service = TCPServerService()
    assert service.make_client_id(("127.0.0.1", 6000)) == "127.0.0.1:6000"
```
```

- [ ] **Step 4: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_tcp_server.py::test_make_client_id_uses_ip_and_port -v
```

Expected: FAIL because the method is missing.

- [ ] **Step 5: Write a failing test for disconnecting an unknown client to be a safe no-op**

```python
import pytest

from app.services.tcp_server import TCPServerService


@pytest.mark.anyio
async def test_disconnect_unknown_client_is_safe() -> None:
    service = TCPServerService()
    await service.disconnect_client("127.0.0.1:6000")
    assert service.snapshot()["clients"] == []
```
```

- [ ] **Step 6: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_tcp_server.py::test_disconnect_unknown_client_is_safe -v
```

Expected: FAIL because service implementation does not exist yet.

---

## Task 2: Implement Minimal TCP Runtime

**Files:**
- Create: `app/services/tcp_server.py`
- Modify: `app/services/runtime_manager.py`

- [ ] **Step 1: Implement `TCPServerConfig`, `TCPClientState`, and `TCPServerService`**

Implementation requirements:

- `update_config()` stores config only
- `make_client_id()` returns `ip:port`
- `snapshot()` returns plain JSON-friendly values
- `disconnect_client()` safely returns if client id is unknown
- `start()` uses `asyncio.start_server()`
- `stop()` closes listener and all active writers
- per-client reader loop updates RX counters and logs packets

- [ ] **Step 2: Extend `RuntimeManager`**

Add:

```python
from app.services.tcp_server import TCPServerConfig, TCPServerService
```

and runtime methods equivalent to the UDP shape:

- `self.tcp_server = TCPServerService()`
- `tcp_snapshot()`
- `apply_tcp_config(payload)`

- [ ] **Step 3: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_tcp_server.py -v
```

Expected: PASS for the new TCP tests.

---

## Task 3: Wire TCP Page Routes

**Files:**
- Modify: `app/routers/pages.py`

- [ ] **Step 1: Replace `/tcp-server` placeholder route with a real page route**

The route should render `tcp_server.html` with:

- `tcp=runtime_manager.tcp_snapshot()`
- `current_user`
- optional `message`

- [ ] **Step 2: Add POST handlers**

Add these endpoints:

- `POST /tcp-server/config`
- `POST /tcp-server/start`
- `POST /tcp-server/stop`
- `POST /tcp-server/send`
- `POST /tcp-server/disconnect`

Each should:

- enforce `admin` or `operator` where mutating
- update runtime state
- persist config into `service_configs`
- emit system logs
- return `tcp_server.html`

- [ ] **Step 3: Keep UDP code untouched except for shared helper extraction if strictly necessary**

If you extract a generic `_save_service_config()` helper, keep it small and in `pages.py` unless duplication becomes confusing.

---

## Task 4: Build The TCP Server Template

**Files:**
- Create: `app/templates/tcp_server.html`

- [ ] **Step 1: Replace placeholder with a real template**

The template must include:

- config form
- runtime status card
- client list table
- send form
- disconnect actions

- [ ] **Step 2: Respect role restrictions in UI**

Hide mutating buttons if `current_user.role == "viewer"`.

- [ ] **Step 3: Keep the look aligned with `udp_server.html`**

Do not redesign the whole admin shell. Follow the current visual language.

---

## Task 5: Persistence And Audit

**Files:**
- Modify: `app/routers/pages.py`

- [ ] **Step 1: Persist TCP config to `service_configs`**

Use:

- `name="tcp_server"`
- `service_type="tcp_server"`

- [ ] **Step 2: Emit audit and network logs for TCP actions**

Examples:

- `TCP server started by <username>`
- `TCP server stopped by <username>`
- `TCP client disconnected <client_id>`
- `Manual TCP payload sent by <username> to <client_id>`

- [ ] **Step 3: Verify packets show up on `/packets?protocol=TCP` after runtime traffic**

---

## Task 6: Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-04-08-web-tcp-udp-platform.md`

- [ ] **Step 1: Run all focused tests**

Run:

```bash
.venv/bin/pytest tests/test_codec.py tests/test_udp_relay.py tests/test_tcp_server.py -v
```

Expected: all pass.

- [ ] **Step 2: Run application preflight**

Run:

```bash
.venv/bin/python scripts/preflight.py
```

Expected output:

```text
preflight ok
```

- [ ] **Step 3: Run application startup**

Run:

```bash
.venv/bin/python scripts/run.py
```

Expected:

- app starts on configured host/port
- `/tcp-server` renders without template errors

- [ ] **Step 4: Manual runtime check**

While app runs, test with a second terminal:

```bash
python - <<'PY'
import socket

sock = socket.create_connection(("127.0.0.1", 9100))
sock.sendall(b"hello tcp")
sock.close()
PY
```

Then verify:

- the client appears or appeared during connection
- `/packets` contains a TCP `client -> server` row
- `/logs` contains TCP connection events

---

## Acceptance Criteria

- `/tcp-server` no longer renders the placeholder page
- authenticated users can view TCP listener status
- `admin` and `operator` can start and stop the TCP listener
- connected clients are visible in the page
- manual payload can be sent to a selected client
- connected client can be disconnected from the UI
- TCP traffic is written to `packet_logs`
- TCP operational events are written to `system_logs`
- UDP functionality remains intact
- `scripts/preflight.py` still passes

---

## Known Risks To Watch

- Stale client entries if disconnect handling misses exception paths
- `StreamWriter` close sequencing on shutdown
- Blocking page actions if send/disconnect logic is not awaited carefully
- Duplicated service-config persistence code in `pages.py`
- Viewer role accidentally seeing operation buttons

---

## Suggested New-Thread Kickoff Prompt

Use this in the next session:

```text
继续开发当前仓库的第二阶段功能，先实现 TCP Server MVP。
先阅读以下文件建立上下文：
- docs/superpowers/plans/2026-04-08-tcp-server-mvp.md
- app/services/udp_server.py
- app/services/runtime_manager.py
- app/routers/pages.py
- README.md

严格按 docs/superpowers/plans/2026-04-08-tcp-server-mvp.md 执行，使用 TDD，小步提交，先写测试再实现。
本轮只做 TCP Server，不要顺带实现 TCP Client 或用户管理。
完成后运行相关测试、preflight 和启动验证，再汇报结果。
```
