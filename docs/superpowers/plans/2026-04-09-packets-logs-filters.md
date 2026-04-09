# Packets And Logs Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add minimal, practical filtering to the SSR `/packets` and `/logs` pages so operators can narrow records by enum fields and core text content without changing the current page-refresh architecture.

**Architecture:** Extend the existing page query handlers in `app/routers/pages.py` with additional GET parameters and SQLAlchemy filters, then update the Jinja2 templates to render the new filter controls and reflect selected values. Keep all filtering logic inline with current route patterns and verify behavior with focused route-function tests against a temporary SQLite database.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, SQLAlchemy, SQLite, pytest

---

## File Map

- Modify: `app/routers/pages.py`
  Responsibility: add query-parameter filtering for `/packets` and `/logs`.
- Modify: `app/templates/packets.html`
  Responsibility: render additional packets filters and a visible `service_type` column.
- Modify: `app/templates/logs.html`
  Responsibility: add logs filter form and preserve selected filter values.
- Create: `tests/test_filters_pages.py`
  Responsibility: focused TDD coverage for packets/logs enum filters and keyword search.

### Task 1: Add failing coverage for packets enum filters

**Files:**
- Create: `tests/test_filters_pages.py`
- Modify: `app/routers/pages.py`
- Modify: `app/templates/packets.html`

- [ ] **Step 1: Write the failing test**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.db import Base
from app.models.packet_log import PacketLog
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
            q=None,
            limit=50,
            user=user,
            db=db,
        )

    body = response.body.decode("utf-8")
    assert "client" in body
    assert "ping" in body
    assert "tcp_server" not in body
    assert "pong" not in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_filters_pages.py::test_packets_page_filters_by_service_and_direction -v`
Expected: FAIL because the `packets()` route does not yet accept `service`, `direction`, or render the service column.

- [ ] **Step 3: Write minimal implementation**

Update the route signature in `app/routers/pages.py` to:

```python
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
```

Update `app/templates/packets.html` form and table header/body to include:

```html
<label>服务
  <select name="service">
    <option value="" {% if not selected_service %}selected{% endif %}>全部</option>
    <option value="udp_server" {% if selected_service == 'udp_server' %}selected{% endif %}>udp_server</option>
    <option value="tcp_server" {% if selected_service == 'tcp_server' %}selected{% endif %}>tcp_server</option>
    <option value="client" {% if selected_service == 'client' %}selected{% endif %}>client</option>
  </select>
</label>
<label>方向
  <select name="direction">
    <option value="" {% if not selected_direction %}selected{% endif %}>全部</option>
    <option value="client -> remote" {% if selected_direction == 'client -> remote' %}selected{% endif %}>client -> remote</option>
    <option value="remote -> client" {% if selected_direction == 'remote -> client' %}selected{% endif %}>remote -> client</option>
    <option value="server -> client" {% if selected_direction == 'server -> client' %}selected{% endif %}>server -> client</option>
    <option value="remote -> server" {% if selected_direction == 'remote -> server' %}selected{% endif %}>remote -> server</option>
  </select>
</label>
```

And change the table columns to:

```html
<tr><th>时间</th><th>服务</th><th>协议</th><th>方向</th><th>源</th><th>目标</th><th>长度</th><th>HEX</th><th>文本</th></tr>
```

```html
<td>{{ row.service_type }}</td>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_filters_pages.py::test_packets_page_filters_by_service_and_direction -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_filters_pages.py app/routers/pages.py app/templates/packets.html
git commit -m "feat: add packets enum filters"
```

### Task 2: Add failing coverage for packets keyword search

**Files:**
- Modify: `tests/test_filters_pages.py`
- Modify: `app/routers/pages.py`
- Modify: `app/templates/packets.html`

- [ ] **Step 1: Write the failing test**

```python
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
                    data_text="reply",
                    length=5,
                ),
            ]
        )
        db.commit()

    request = Request({"type": "http", "method": "GET", "path": "/packets", "headers": [], "query_string": b"q=192.168&limit=50"})
    user = User(username="viewer-user", password_hash="x", role="viewer", is_active=True)

    with testing_session_local() as db:
        response = packets(request, protocol=None, service=None, direction=None, q="192.168", limit=50, user=user, db=db)

    body = response.body.decode("utf-8")
    assert "query dns" in body
    assert "reply" not in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_filters_pages.py::test_packets_page_keyword_matches_text_and_ip -v`
Expected: FAIL because the keyword filter does not yet change the query.

- [ ] **Step 3: Write minimal implementation**

Add imports and keyword filter to `app/routers/pages.py`:

```python
from sqlalchemy import or_
```

```python
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                PacketLog.data_text.ilike(like),
                PacketLog.data_hex.ilike(like),
                PacketLog.src_ip.ilike(like),
                PacketLog.dst_ip.ilike(like),
            )
        )
```

Add the packets keyword input to `app/templates/packets.html`:

```html
<label>关键字<input name="q" value="{{ query_text }}"></label>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_filters_pages.py::test_packets_page_keyword_matches_text_and_ip -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_filters_pages.py app/routers/pages.py app/templates/packets.html
git commit -m "feat: add packets keyword filter"
```

### Task 3: Add failing coverage for logs enum filters

**Files:**
- Modify: `tests/test_filters_pages.py`
- Modify: `app/routers/pages.py`
- Modify: `app/templates/logs.html`

- [ ] **Step 1: Write the failing test**

```python
from app.models.system_log import SystemLog


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_filters_pages.py::test_logs_page_filters_by_level_and_category -v`
Expected: FAIL because the `logs()` route does not yet accept `level`, `category`, or `limit` arguments.

- [ ] **Step 3: Write minimal implementation**

Update the `logs()` route in `app/routers/pages.py` to:

```python
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
```

Add the logs filter form to `app/templates/logs.html`:

```html
<form method="get" action="/logs" class="filter-row">
  <label>级别
    <select name="level">
      <option value="" {% if not selected_level %}selected{% endif %}>全部</option>
      <option value="info" {% if selected_level == 'info' %}selected{% endif %}>info</option>
      <option value="warning" {% if selected_level == 'warning' %}selected{% endif %}>warning</option>
      <option value="error" {% if selected_level == 'error' %}selected{% endif %}>error</option>
    </select>
  </label>
  <label>分类
    <select name="category">
      <option value="" {% if not selected_category %}selected{% endif %}>全部</option>
      <option value="auth" {% if selected_category == 'auth' %}selected{% endif %}>auth</option>
      <option value="service" {% if selected_category == 'service' %}selected{% endif %}>service</option>
      <option value="config" {% if selected_category == 'config' %}selected{% endif %}>config</option>
      <option value="network" {% if selected_category == 'network' %}selected{% endif %}>network</option>
    </select>
  </label>
  <label>最近 N 条<input type="number" name="limit" value="{{ limit }}"></label>
  <button type="submit">筛选</button>
</form>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_filters_pages.py::test_logs_page_filters_by_level_and_category -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_filters_pages.py app/routers/pages.py app/templates/logs.html
git commit -m "feat: add logs enum filters"
```

### Task 4: Add failing coverage for logs keyword search

**Files:**
- Modify: `tests/test_filters_pages.py`
- Modify: `app/routers/pages.py`
- Modify: `app/templates/logs.html`

- [ ] **Step 1: Write the failing test**

```python
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
                SystemLog(level="info", category="service", message="UDP relay started", detail="bind 0.0.0.0:9000"),
            ]
        )
        db.commit()

    request = Request({"type": "http", "method": "GET", "path": "/logs", "headers": [], "query_string": b"q=refused&limit=50"})
    user = User(username="viewer-user", password_hash="x", role="viewer", is_active=True)

    with testing_session_local() as db:
        response = logs(request, level=None, category=None, q="refused", limit=50, user=user, db=db)

    body = response.body.decode("utf-8")
    assert "Connect failed" in body
    assert "UDP relay started" not in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_filters_pages.py::test_logs_page_keyword_matches_message_and_detail -v`
Expected: FAIL because the keyword filter is not yet applied to the logs query.

- [ ] **Step 3: Write minimal implementation**

Add the logs keyword filter to `app/routers/pages.py`:

```python
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                SystemLog.message.ilike(like),
                SystemLog.detail.ilike(like),
            )
        )
```

Add the keyword input to the logs filter form in `app/templates/logs.html`:

```html
<label>关键字<input name="q" value="{{ query_text }}"></label>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_filters_pages.py::test_logs_page_keyword_matches_message_and_detail -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_filters_pages.py app/routers/pages.py app/templates/logs.html
git commit -m "feat: add logs keyword filter"
```

### Task 5: Final focused verification

**Files:**
- Modify: `tests/test_filters_pages.py`
- Modify: `app/routers/pages.py`
- Modify: `app/templates/packets.html`
- Modify: `app/templates/logs.html`

- [ ] **Step 1: Run the filters test suite**

Run: `.venv\Scripts\pytest tests/test_filters_pages.py -v`
Expected: all filter page tests PASS.

- [ ] **Step 2: Run related existing page tests**

Run: `.venv\Scripts\pytest tests/test_client_page.py tests/test_users_page.py -v`
Expected: PASS, confirming changes in `pages.py` did not regress existing page routes.

- [ ] **Step 3: Run broader regression tests**

Run: `.venv\Scripts\pytest tests/test_codec.py tests/test_udp_relay.py tests/test_tcp_server.py tests/test_client_runtime.py tests/test_client_page.py tests/test_users_page.py tests/test_filters_pages.py -v`
Expected: PASS

- [ ] **Step 4: Run preflight**

Run: `.venv\Scripts\python scripts/preflight.py`
Expected: `preflight ok`

- [ ] **Step 5: Run startup verification**

Run: `.venv\Scripts\python scripts/run.py`
Expected: application starts without import errors and serves the existing app locally. Stop it after confirming startup.

- [ ] **Step 6: Commit**

```bash
git add tests/test_filters_pages.py app/routers/pages.py app/templates/packets.html app/templates/logs.html
git commit -m "feat: add packets and logs filters"
```
