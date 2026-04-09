# Delivery Test Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the minimum gaps between the current MVP and a stable handoff for internal delivery testing by adding real HTTP integration coverage, key end-to-end page flows, and a concise tester-facing verification guide.

**Architecture:** Keep the existing FastAPI + Jinja2 SSR monolith unchanged. Add tests around the real ASGI app with `fastapi.testclient.TestClient`, using isolated SQLite databases and dependency-safe setup so authentication, session middleware, redirects, role checks, and page workflows are validated through actual HTTP requests rather than direct function calls alone.

**Tech Stack:** FastAPI, Starlette `TestClient`, Pytest, SQLite, SQLAlchemy ORM, Jinja2 SSR.

---

## File Map

**Existing files to modify**
- `tests/conftest.py`
  Purpose: shared pytest fixtures for app-level integration tests and isolated database setup.
- `tests/test_client_page.py`
  Purpose: keep direct route tests; may gain one or two assertions only if needed for consistency.
- `tests/test_tcp_server.py`
  Purpose: keep direct route and service tests; may gain one or two assertions only if needed for consistency.
- `README.md`
  Purpose: if the new tester guide reveals a missing run note, keep any README adjustment minimal.

**New files to create**
- `tests/test_auth_integration.py`
  Purpose: verify login, failed login, logout, and unauthenticated redirects through the real app.
- `tests/test_pages_integration.py`
  Purpose: verify protected pages, role restrictions, and at least one real POST workflow using session cookies.
- `tests/test_ws_runtime.py`
  Purpose: smoke-test `/ws/runtime` connection, first snapshot payload, and disconnect cleanup behavior.
- `docs/2026-04-09-delivery-test-guide.md`
  Purpose: concise tester-facing guide covering scope, accounts, recommended flows, and known limits.

**Reference files to read before coding**
- `app/main.py`
- `app/routers/auth.py`
- `app/auth/deps.py`
- `app/routers/pages.py`
- `app/routers/ws.py`
- `app/db.py`
- `app/config.py`
- Existing tests under `tests/`

---

### Task 1: Build Reusable App-Level Test Fixtures

**Files:**
- Modify: `tests/conftest.py`
- Reference: `app/main.py`, `app/db.py`, `app/config.py`
- Test: `tests/test_auth_integration.py`, `tests/test_pages_integration.py`, `tests/test_ws_runtime.py`

- [ ] **Step 1: Write the failing fixture-driven integration test skeleton**

Create `tests/test_auth_integration.py` with a minimal test that assumes a `client` fixture exists:

```python
def test_login_page_loads(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "登录" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.\.venv\Scripts\pytest tests/test_auth_integration.py::test_login_page_loads -v
```

Expected:
- FAIL because fixture `client` does not exist yet.

- [ ] **Step 3: Write minimal shared fixtures in `tests/conftest.py`**

Add fixtures for:
- a temporary SQLite database path
- a SQLAlchemy engine/session factory bound to that database
- database schema creation via `Base.metadata.create_all(...)`
- a real FastAPI app from `create_app()`
- dependency override for `get_db`
- a `TestClient`

Target shape:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import create_app


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def db_engine(tmp_path):
    db_path = tmp_path / "test-app.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session_local(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture
def app(db_session_local):
    app = create_app()

    def override_get_db():
        db = db_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client
```

- [ ] **Step 4: Run the skeleton test to verify it passes**

Run:

```bash
.\.venv\Scripts\pytest tests/test_auth_integration.py::test_login_page_loads -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_auth_integration.py
git commit -m "test: add app integration fixtures"
```

---

### Task 2: Add Authentication And Session Integration Coverage

**Files:**
- Create: `tests/test_auth_integration.py`
- Reference: `app/routers/auth.py`, `app/auth/deps.py`, `app/models/user.py`, `app/auth/security.py`
- Test: `tests/test_auth_integration.py`

- [ ] **Step 1: Write the failing tests**

Expand `tests/test_auth_integration.py` with these tests:

```python
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models.user import User


def test_login_succeeds_and_redirects_to_dashboard(client, db_engine):
    with Session(db_engine) as db:
        db.add(User(username="admin", password_hash=hash_password("secret123"), role="admin", is_active=True))
        db.commit()

    response = client.post(
        "/login",
        data={"username": "admin", "password": "secret123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_login_failure_returns_400_and_error_message(client, db_engine):
    with Session(db_engine) as db:
        db.add(User(username="admin", password_hash=hash_password("secret123"), role="admin", is_active=True))
        db.commit()

    response = client.post("/login", data={"username": "admin", "password": "wrong"})

    assert response.status_code == 400
    assert "用户名或密码错误" in response.text


def test_inactive_user_cannot_log_in(client, db_engine):
    with Session(db_engine) as db:
        db.add(User(username="disabled", password_hash=hash_password("secret123"), role="viewer", is_active=False))
        db.commit()

    response = client.post("/login", data={"username": "disabled", "password": "secret123"})

    assert response.status_code == 400
    assert "用户名或密码错误" in response.text


def test_logout_clears_session_and_redirects(client, db_engine):
    with Session(db_engine) as db:
        user = User(username="admin", password_hash=hash_password("secret123"), role="admin", is_active=True)
        db.add(user)
        db.commit()

    login_response = client.post(
        "/login",
        data={"username": "admin", "password": "secret123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303

    logout_response = client.post("/logout", follow_redirects=False)

    assert logout_response.status_code == 303
    assert logout_response.headers["location"] == "/login"

    redirected = client.get("/dashboard", follow_redirects=False)
    assert redirected.status_code == 303
    assert redirected.headers["location"] == "/login"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.\.venv\Scripts\pytest tests/test_auth_integration.py -v
```

Expected:
- At least one FAIL caused by missing fixture details, response mismatch, or redirect/session behavior not yet aligned in tests.

- [ ] **Step 3: Write minimal fixture or setup corrections**

If the tests fail because the app startup or database override is incomplete, fix only the minimum in `tests/conftest.py`. Typical minimal fix:

```python
@pytest.fixture
def app(db_session_local):
    app = create_app()

    def override_get_db():
        db = db_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()
```

Do not change production auth logic unless a real app-level defect is proven by the failing test.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.\.venv\Scripts\pytest tests/test_auth_integration.py -v
```

Expected:
- PASS for all auth integration tests.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_auth_integration.py
git commit -m "test: cover auth session flows"
```

---

### Task 3: Add Protected Page And Role Integration Coverage

**Files:**
- Create: `tests/test_pages_integration.py`
- Reference: `app/routers/pages.py`, `app/auth/deps.py`, `app/models/user.py`, `app/auth/security.py`
- Test: `tests/test_pages_integration.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pages_integration.py` with these tests:

```python
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models.user import User


def login_as(client, username: str, password: str) -> None:
    response = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert response.status_code == 303


def test_unauthenticated_requests_redirect_to_login(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_viewer_can_open_client_page_but_cannot_see_mutation_forms(client, db_engine):
    with Session(db_engine) as db:
        db.add(User(username="viewer", password_hash=hash_password("secret123"), role="viewer", is_active=True))
        db.commit()

    login_as(client, "viewer", "secret123")
    response = client.get("/client")

    assert response.status_code == 200
    assert "Viewer 角色仅可查看 Client 运行状态。" in response.text
    assert "/client/connect" not in response.text


def test_operator_cannot_open_users_page(client, db_engine):
    with Session(db_engine) as db:
        db.add(User(username="operator", password_hash=hash_password("secret123"), role="operator", is_active=True))
        db.commit()

    login_as(client, "operator", "secret123")
    response = client.get("/users", follow_redirects=False)

    assert response.status_code == 403


def test_admin_can_open_users_page(client, db_engine):
    with Session(db_engine) as db:
        db.add(User(username="admin", password_hash=hash_password("secret123"), role="admin", is_active=True))
        db.commit()

    login_as(client, "admin", "secret123")
    response = client.get("/users")

    assert response.status_code == 200
    assert "用户管理" in response.text


def test_operator_can_update_client_config_through_real_post(client, db_engine):
    with Session(db_engine) as db:
        db.add(User(username="operator", password_hash=hash_password("secret123"), role="operator", is_active=True))
        db.commit()

    login_as(client, "operator", "secret123")
    response = client.post(
        "/client/config",
        data={"protocol": "UDP", "target_ip": "127.0.0.1", "target_port": "9201", "hex_mode": "on"},
    )

    assert response.status_code == 200
    assert "Client 配置已更新" in response.text
    assert "9201" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.\.venv\Scripts\pytest tests/test_pages_integration.py -v
```

Expected:
- At least one FAIL revealing real app integration gaps or fixture/setup gaps.

- [ ] **Step 3: Write minimal implementation or fixture fixes**

Only if a test proves a real defect, make the smallest fix in one of these files:
- `tests/conftest.py`
- `app/auth/deps.py`
- `app/routers/pages.py`

Acceptable minimal production fix example if redirect handling is wrong under real requests:

```python
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
```

Do not broaden scope into new features.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.\.venv\Scripts\pytest tests/test_pages_integration.py -v
```

Expected:
- PASS for all page integration tests.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_pages_integration.py app/auth/deps.py app/routers/pages.py
git commit -m "test: add protected page integration coverage"
```

---

### Task 4: Add WebSocket Runtime Smoke Coverage

**Files:**
- Create: `tests/test_ws_runtime.py`
- Reference: `app/routers/ws.py`, `app/services/logging_service.py`, `app/services/runtime_manager.py`
- Test: `tests/test_ws_runtime.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ws_runtime.py` with these tests:

```python
from app.services.logging_service import system_log_service


def test_runtime_ws_sends_initial_snapshot(client):
    with client.websocket_connect("/ws/runtime") as websocket:
        payload = websocket.receive_json()

    assert payload["type"] == "snapshot"
    assert "udp" in payload
    assert isinstance(payload["udp"], dict)


def test_runtime_ws_unsubscribes_on_disconnect(client):
    before = len(system_log_service.subscribers)

    with client.websocket_connect("/ws/runtime") as websocket:
        _ = websocket.receive_json()
        during = len(system_log_service.subscribers)
        assert during == before + 1

    after = len(system_log_service.subscribers)
    assert after == before
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.\.venv\Scripts\pytest tests/test_ws_runtime.py -v
```

Expected:
- FAIL if the websocket route does not behave as the test assumes or if subscriber cleanup is incomplete.

- [ ] **Step 3: Write minimal implementation fixes if a real defect is proven**

Only modify `app/routers/ws.py` if the tests expose an actual cleanup problem. Minimal acceptable fix shape:

```python
@router.websocket("/ws/runtime")
async def runtime_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    system_log_service.subscribe(websocket)
    try:
        while True:
            await websocket.send_json({"type": "snapshot", "udp": runtime_manager.udp_snapshot()})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        system_log_service.unsubscribe(websocket)
    except Exception:
        system_log_service.unsubscribe(websocket)
        raise
```

If the existing code already passes, do not change production code.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.\.venv\Scripts\pytest tests/test_ws_runtime.py -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_ws_runtime.py app/routers/ws.py
git commit -m "test: cover runtime websocket smoke flow"
```

---

### Task 5: Add Tester-Facing Delivery Guide

**Files:**
- Create: `docs/2026-04-09-delivery-test-guide.md`
- Optional Modify: `README.md`
- Reference: `README.md`, `docs/2026-04-08-phase-2-handoff.md`, `docs/2026-04-08-phase-2-release-notes.md`
- Test: manual doc sanity check only

- [ ] **Step 1: Write the guide content**

Create `docs/2026-04-09-delivery-test-guide.md` with this structure:

```md
# 2026-04-09 Delivery Test Guide

## Scope In This Build
- 登录与 Session
- Dashboard
- UDP Server
- TCP Server
- TCP/UDP Client
- Users 页面
- Packets / Logs 最小筛选

## Recommended Accounts
- admin: full access
- operator: runtime operations only
- viewer: read-only

## Environment Preparation
1. Create venv and install requirements.
2. Run `python scripts/init_db.py`.
3. Run `python scripts/preflight.py`.
4. Run `python scripts/run.py`.

## Suggested Test Flow
1. Verify login success/failure.
2. Verify `/users` is admin-only.
3. Verify viewer cannot mutate `/client` and `/tcp-server`.
4. Verify TCP server start/send/disconnect.
5. Verify client connect/send/disconnect in TCP mode.
6. Verify UDP server start/send/stop.
7. Verify failed runtime actions show inline error and appear in `/logs`.
8. Verify `/packets` and `/logs` filters return expected rows.

## Known Limits
- Client is single-profile only.
- Pages are SSR refresh-based, not SPA.
- Runtime audit is intentionally minimal.
- No advanced scheduling, auto-reconnect, or profile management.
```

- [ ] **Step 2: Review the guide for accuracy against current code**

Check that the guide does not claim unsupported behavior. In particular verify:
- `/users` is admin-only
- viewer is read-only on runtime pages
- runtime action failures now render inline error messages

- [ ] **Step 3: If README is missing one critical pointer, add one minimal link**

Only if useful, add a short line under the local run section:

```md
- 交付测试流程可参考 `docs/2026-04-09-delivery-test-guide.md`
```

Do not rewrite the README.

- [ ] **Step 4: Manual verification**

No code test here. Verify by reading the file and checking the paths and command names are exact.

- [ ] **Step 5: Commit**

```bash
git add docs/2026-04-09-delivery-test-guide.md README.md
git commit -m "docs: add delivery test guide"
```

---

### Task 6: Run Final Delivery-Readiness Verification

**Files:**
- No code changes required unless verification exposes a real defect
- Test: all relevant test files and startup checks

- [ ] **Step 1: Run the targeted suite**

Run:

```bash
.\.venv\Scripts\pytest tests/test_auth_integration.py tests/test_pages_integration.py tests/test_ws_runtime.py tests/test_client_page.py tests/test_tcp_server.py tests/test_udp_server_page.py tests/test_client_runtime.py tests/test_udp_relay.py tests/test_users_page.py tests/test_filters_pages.py tests/test_codec.py -q
```

Expected:
- All tests PASS.

- [ ] **Step 2: Run the full suite**

Run:

```bash
.\.venv\Scripts\pytest -q
```

Expected:
- All tests PASS.

- [ ] **Step 3: Run preflight**

Run:

```bash
.\.venv\Scripts\python scripts/preflight.py
```

Expected:
- `preflight ok`

- [ ] **Step 4: Run startup smoke verification**

Run:

```bash
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "scripts/run.py" -PassThru; Start-Sleep -Seconds 5
```

Then verify at least these pages return `200` or the expected redirect:

```bash
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8080/login"
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8080/client" -MaximumRedirection 0
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8080/tcp-server" -MaximumRedirection 0
```

Expected:
- `/login` returns `200`
- protected pages return redirect to `/login` when unauthenticated

Stop the started process after verification.

- [ ] **Step 5: Commit or stop and fix**

If verification is green:

```bash
git add tests docs README.md
git commit -m "test: close delivery-readiness gaps"
```

If any verification fails, do not commit. Fix the failure with TDD first.

---

## Self-Review Notes

- Spec coverage: this plan closes the three largest delivery gaps currently visible in the repo: real auth/session integration coverage, protected page workflow coverage, and a tester-facing execution guide.
- Placeholder scan: no TODO/TBD placeholders remain.
- Type consistency: all referenced functions and files exist in the current repo (`create_app`, `get_db`, `runtime_ws`, `require_role`, route paths, and current test filenames).
