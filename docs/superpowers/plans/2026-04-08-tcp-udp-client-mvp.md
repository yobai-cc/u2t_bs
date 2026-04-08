# TCP/UDP Client MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal but usable TCP/UDP Client feature to the existing FastAPI monolith so authenticated users can configure a single outbound client target, connect or disconnect it from the web UI, send manual payloads, inspect received payloads, and view packet/system logs in the current web interface.

**Architecture:** Reuse the existing monolith runtime pattern already used by the UDP relay and TCP server. Add one new in-process runtime service owned by `RuntimeManager`, expose it through server-rendered Jinja2 routes in `app/routers/pages.py`, persist config and counters through `service_configs`, and reuse `packet_logs` plus `system_logs` for traffic and audit events. Keep this phase intentionally minimal: one active client runtime, connect/disconnect, manual send, RX/TX counters, TCP/UDP mode switch, and page-refresh-based visibility.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, SQLAlchemy, SQLite, asyncio streams, UDP transport, bcrypt, WebSocket, systemd, Caddy.

---

## Current Project Context

This repository now contains a working MVP for authentication, dashboard visibility, UDP relay runtime, TCP server runtime, packet logging, system logging, and Ubuntu-oriented deployment assets.

### Verified Current State

- FastAPI app import succeeds through `app.main:app`
- `scripts/preflight.py` returns `preflight ok`
- Focused tests currently pass:
  - `tests/test_codec.py`
  - `tests/test_udp_relay.py`
  - `tests/test_tcp_server.py`
- Admin bootstrap works via `scripts/init_db.py`
- Web service starts on `127.0.0.1:8080`
- `/tcp-server` is now a working SSR page instead of a placeholder

### Existing Files You Must Read First

- `app/services/tcp_server.py`
  Why: this is the newest runtime service pattern and the closest shape to follow for connection-oriented client runtime work.
- `app/services/udp_server.py`
  Why: this already shows UDP transport lifecycle, packet logging, and manual send behavior.
- `app/services/runtime_manager.py`
  Why: client runtime ownership should be added here next to UDP relay and TCP server.
- `app/routers/pages.py`
  Why: existing page route, role guard, config persistence, and template response patterns live here.
- `app/services/packet_logger.py`
  Why: all client RX/TX traffic must reuse the same packet logging model.
- `app/services/logging_service.py`
  Why: connect/disconnect/send/errors should emit system logs through the existing helper.
- `app/templates/tcp_server.html`
  Why: this page now represents the current UI density and action layout expected for runtime pages.
- `app/templates/placeholder.html`
  Why: `/client` still points here and should be replaced in this phase.

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

## MVP Scope For TCP/UDP Client

### In Scope

- Single client config with:
  - `protocol` (`TCP` or `UDP`)
  - `target_ip`
  - `target_port`
  - `hex_mode`
- Connect outbound runtime for TCP mode
- Disconnect outbound runtime for TCP mode
- Manual send for TCP mode
- Manual send for UDP mode
- Receive inbound payloads from TCP target
- Receive inbound payloads from UDP replies on the same socket
- Count TX/RX bytes
- Show current client runtime status on `/client`
- Record packet logs for:
  - `client -> remote`
  - `remote -> client`
- Record system logs for:
  - connect
  - disconnect
  - manual send
  - receive
  - network errors
- Persist client config into `service_configs`

### Out Of Scope For This Phase

- Multiple saved client profiles
- Auto reconnect and heartbeat logic
- Timed send or scheduled traffic
- TCP server enhancements beyond what already ships
- Protocol parsing, sticky-packet splitting, or framing helpers
- Binary file upload/download
- Live push updates beyond page refresh behavior

---

## Proposed Runtime Design

Create a new service in `app/services/client_runtime.py`.

### Suggested Types

```python
from dataclasses import dataclass


@dataclass(slots=True)
class ClientRuntimeConfig:
    protocol: str = "TCP"
    target_ip: str = "127.0.0.1"
    target_port: int = 9001
    hex_mode: bool = False


@dataclass(slots=True)
class ClientRuntimeSnapshot:
    protocol: str
    target_ip: str
    target_port: int
    hex_mode: bool
    running: bool
    connected: bool
    tx_count: int
    rx_count: int
    peer_label: str
```

### Suggested Service Shape

```python
class ClientRuntimeService:
    def __init__(self, db_factory: Callable[[], Session] = SessionLocal) -> None: ...
    def update_config(self, config: ClientRuntimeConfig) -> None: ...
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def send_manual(self, payload_text: str) -> None: ...
    def snapshot(self) -> dict[str, object]: ...
```

### Internal State To Keep

- `config`
- `running: bool`
- `connected: bool`
- `tcp_reader: asyncio.StreamReader | None`
- `tcp_writer: asyncio.StreamWriter | None`
- `udp_transport: asyncio.DatagramTransport | None`
- `udp_protocol: ClientUDPProtocol | None`
- `tx_count: int`
- `rx_count: int`
- `peer_label: str`
- `receive_task: asyncio.Task[None] | None`

### Minimal Protocol Rules

- For `TCP`:
  - `connect()` opens one TCP connection to `target_ip:target_port`
  - `disconnect()` closes writer and receive task
  - `send_manual()` writes to the active writer
  - a background receive loop reads data and records `remote -> client`
- For `UDP`:
  - `connect()` prepares one bound UDP transport for outbound and reply traffic
  - `disconnect()` closes the transport
  - `send_manual()` sends one datagram to `target_ip:target_port`
  - `datagram_received()` records `remote -> client`

Keep protocol branching inside the runtime service. Do not split into multiple page flows yet.

---

## Data And Logging Rules

### Packet Logging

For every manual send:

- service_type: `client`
- protocol: selected protocol (`TCP` or `UDP`)
- direction: `client -> remote`
- source: local runtime side
- target: configured target ip/port
- payload: raw bytes

For every received payload:

- service_type: `client`
- protocol: selected protocol (`TCP` or `UDP`)
- direction: `remote -> client`
- source: remote ip/port
- target: local runtime side
- payload: raw bytes

### System Logging

Emit through `system_log_service.log_to_db()` for:

- client connected
- client disconnected
- manual send
- payload received
- socket read/write failures

### Config Persistence

Store client config in `service_configs` with:

- `name="client_runtime"`
- `service_type="client"`
- `target_ip`
- `target_port`
- `enabled`
- `config_json={"protocol": str, "hex_mode": bool, "tx_count": int, "rx_count": int, "peer_label": str}`

Mirror the current UDP/TCP persistence pattern already in `app/routers/pages.py`.

---

## UI Requirements For `/client`

Replace the placeholder page with a real template.

### Page Sections

1. Client config card
- protocol select (`TCP`, `UDP`)
- target ip input
- target port input
- hex mode checkbox
- save config button

2. Runtime status card
- running yes/no
- connected yes/no
- peer label
- total TX bytes
- total RX bytes
- connect button
- disconnect button

3. Manual send card
- payload textarea
- send button

4. Recent runtime note card
- page refresh is acceptable for MVP

### Role Rules

- `admin`: full access
- `operator`: full client operations access
- `viewer`: read-only page access, no connect/disconnect/send

---

## File Plan

### Create

- `app/services/client_runtime.py`
- `app/templates/client.html`
- `tests/test_client_runtime.py`

### Modify

- `app/services/runtime_manager.py`
- `app/routers/pages.py`
- `README.md`
- `docs/superpowers/plans/2026-04-08-web-tcp-udp-platform.md`

Optional only if needed after implementation starts:

- `app/static/app.css`
- `app/static/app.js`

---

## Task 1: Write Client Runtime Tests First

**Files:**
- Create: `tests/test_client_runtime.py`

- [ ] **Step 1: Write a failing test for config update and snapshot shape**

```python
from app.services.client_runtime import ClientRuntimeConfig, ClientRuntimeService


def test_update_config_changes_snapshot_values() -> None:
    service = ClientRuntimeService()
    service.update_config(ClientRuntimeConfig(protocol="TCP", target_ip="127.0.0.1", target_port=9200, hex_mode=True))

    snapshot = service.snapshot()

    assert snapshot["protocol"] == "TCP"
    assert snapshot["target_ip"] == "127.0.0.1"
    assert snapshot["target_port"] == 9200
    assert snapshot["hex_mode"] is True
    assert snapshot["connected"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_client_runtime.py::test_update_config_changes_snapshot_values -v
```

Expected: FAIL with `ModuleNotFoundError` because `app.services.client_runtime` does not exist yet.

- [ ] **Step 3: Write a failing test for disconnect being a safe no-op when idle**

```python
import pytest

from app.services.client_runtime import ClientRuntimeService


@pytest.mark.anyio
async def test_disconnect_when_idle_is_safe() -> None:
    service = ClientRuntimeService()
    await service.disconnect()
    assert service.snapshot()["connected"] is False
```

- [ ] **Step 4: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_client_runtime.py::test_disconnect_when_idle_is_safe -v
```

Expected: FAIL because the service implementation does not exist yet.

- [ ] **Step 5: Write a failing test for TCP connect, send, receive, and disconnect**

```python
import asyncio
import pytest

from app.services.client_runtime import ClientRuntimeConfig, ClientRuntimeService


@pytest.mark.anyio
async def test_tcp_mode_connect_send_receive_and_disconnect() -> None:
    received = []

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.read(4096)
        received.append(data)
        writer.write(b"reply")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    sockname = server.sockets[0].getsockname()

    service = ClientRuntimeService()
    service.update_config(ClientRuntimeConfig(protocol="TCP", target_ip="127.0.0.1", target_port=sockname[1], hex_mode=False))

    await service.connect()
    await service.send_manual("hello")

    for _ in range(20):
        if service.snapshot()["rx_count"] == 5:
            break
        await asyncio.sleep(0.01)

    assert received == [b"hello"]
    assert service.snapshot()["tx_count"] == 5
    assert service.snapshot()["rx_count"] == 5

    await service.disconnect()
    assert service.snapshot()["connected"] is False

    server.close()
    await server.wait_closed()
```

- [ ] **Step 6: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_client_runtime.py::test_tcp_mode_connect_send_receive_and_disconnect -v
```

Expected: FAIL because connect/send/receive behavior is not implemented yet.

---

## Task 2: Implement Minimal Client Runtime

**Files:**
- Create: `app/services/client_runtime.py`
- Modify: `app/services/runtime_manager.py`

- [ ] **Step 1: Implement `ClientRuntimeConfig` and `ClientRuntimeService`**

Implementation requirements:

- `update_config()` stores config only
- `snapshot()` returns plain JSON-friendly values
- `disconnect()` safely returns if idle
- `connect()` branches by protocol
- TCP mode uses `asyncio.open_connection()` and a receive loop
- UDP mode uses a datagram transport and a small protocol helper
- `send_manual()` uses `parse_payload()` and updates TX counters
- receive paths update RX counters and persist packet logs

- [ ] **Step 2: Extend `RuntimeManager`**

Add:

```python
from app.services.client_runtime import ClientRuntimeConfig, ClientRuntimeService
```

and runtime methods equivalent to the existing UDP/TCP shape:

- `self.client_runtime = ClientRuntimeService()`
- `client_snapshot()`
- `apply_client_config(payload)`

- [ ] **Step 3: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_client_runtime.py -v
```

Expected: PASS for the new client runtime tests.

---

## Task 3: Wire Client Page Routes

**Files:**
- Modify: `app/routers/pages.py`

- [ ] **Step 1: Replace `/client` placeholder route with a real page route**

The route should render `client.html` with:

- `client=runtime_manager.client_snapshot()`
- `current_user`
- optional `message`

- [ ] **Step 2: Add POST handlers**

Add these endpoints:

- `POST /client/config`
- `POST /client/connect`
- `POST /client/disconnect`
- `POST /client/send`

Each should:

- enforce `admin` or `operator` where mutating
- update runtime state
- persist config into `service_configs`
- emit system logs
- return `client.html`

- [ ] **Step 3: Keep TCP and UDP pages untouched except for tiny shared helper extraction if strictly necessary**

---

## Task 4: Build The Client Template

**Files:**
- Create: `app/templates/client.html`

- [ ] **Step 1: Replace placeholder with a real template**

The template must include:

- config form
- runtime status card
- manual send card
- connect/disconnect actions

- [ ] **Step 2: Respect role restrictions in UI**

Hide mutating buttons if `current_user.role == "viewer"`.

- [ ] **Step 3: Keep the look aligned with `udp_server.html` and `tcp_server.html`**

Do not redesign the whole admin shell. Follow the current visual language.

---

## Task 5: Persistence And Audit

**Files:**
- Modify: `app/routers/pages.py`

- [ ] **Step 1: Persist client config to `service_configs`**

Use:

- `name="client_runtime"`
- `service_type="client"`

- [ ] **Step 2: Emit audit and network logs for client actions**

Examples:

- `Client connected by <username>`
- `Client disconnected by <username>`
- `Manual client payload sent by <username>`

- [ ] **Step 3: Verify packets show up on `/packets?protocol=TCP` and `/packets?protocol=UDP` after runtime traffic**

---

## Task 6: Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-04-08-web-tcp-udp-platform.md`

- [ ] **Step 1: Run all focused tests**

Run:

```bash
.venv/bin/pytest tests/test_codec.py tests/test_udp_relay.py tests/test_tcp_server.py tests/test_client_runtime.py -v
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
- `/client` renders without template errors

- [ ] **Step 4: Manual runtime check**

For TCP mode, verify with a tiny local echo server that connect/send/receive works.

For UDP mode, verify with a tiny local UDP responder that send/receive works.

Then verify:

- `/packets` contains client runtime rows for both protocols tested
- `/logs` contains client connect/disconnect/send events

---

## Acceptance Criteria

- `/client` no longer renders the placeholder page
- authenticated users can view client runtime status
- `admin` and `operator` can connect and disconnect the runtime
- manual payload can be sent in both TCP and UDP modes
- inbound replies are visible via counters and packet logs
- client traffic is written to `packet_logs`
- client operational events are written to `system_logs`
- existing UDP relay and TCP server functionality remain intact
- `scripts/preflight.py` still passes

---

## Known Risks To Watch

- UDP reply handling may silently break if local bind behavior is inconsistent across platforms
- TCP receive task cleanup may leave stale connected state if exception handling is incomplete
- Shared persistence helpers in `pages.py` may become repetitive and drift
- Viewer role may accidentally retain connect/send button visibility if template conditions diverge

---

## Suggested New-Thread Kickoff Prompt

Use this in the next session:

```text
继续开发当前仓库的第二阶段功能，下一步实现 TCP/UDP Client MVP。
先阅读以下文件建立上下文：
- docs/superpowers/plans/2026-04-08-tcp-udp-client-mvp.md
- app/services/tcp_server.py
- app/services/udp_server.py
- app/services/runtime_manager.py
- app/routers/pages.py
- README.md

分析 Client 与现有 TCP Server / UDP Server 代码有什么不同，有哪些可以复用。
严格按 docs/superpowers/plans/2026-04-08-tcp-udp-client-mvp.md 执行，使用 TDD，小步提交，先写测试再实现。
本轮只做 TCP/UDP Client，不要顺带实现用户管理。
完成后运行相关测试、preflight 和启动验证，再汇报结果。
```
