# Web TCP/UDP Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight FastAPI-based web platform that preserves the core behavior of the original TCP/UDP desktop tool, starting with an MVP that includes authentication, dashboard visibility, UDP relay, TCP server runtime, packet logging, system logging, and Linux deployment assets.

**Architecture:** Use a monolithic FastAPI application with server-rendered Jinja2 templates, HTMX form submissions, WebSocket-based live log streaming, SQLAlchemy models over SQLite, and in-process asyncio services for UDP/TCP runtime engines. Persist configuration and audit data in the database while keeping active socket runtime state in a dedicated runtime manager.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, HTMX, WebSocket, SQLAlchemy, SQLite, asyncio, bcrypt/passlib, systemd, Caddy.

---

### Task 1: Project Skeleton And Core Configuration

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/db.py`
- Create: `app/main.py`
- Create: `app/models/__init__.py`
- Create: `app/routers/__init__.py`
- Create: `app/services/__init__.py`

- [ ] Define the minimal dependency set required for the MVP.
- [ ] Add application settings for environment, database path, secret key, admin bootstrap, logging paths, and web bind host/port.
- [ ] Add SQLAlchemy engine/session/bootstrap helpers.
- [ ] Add FastAPI app bootstrap with startup initialization and router registration.

### Task 2: Authentication And Authorization

**Files:**
- Create: `app/auth/__init__.py`
- Create: `app/auth/security.py`
- Create: `app/auth/deps.py`
- Create: `app/models/user.py`
- Create: `app/routers/auth.py`

- [ ] Add user model with role and audit timestamps.
- [ ] Add password hashing and session-based current-user resolution.
- [ ] Add login/logout handlers and role-protected dependencies.

### Task 3: Logging And Persistence

**Files:**
- Create: `app/models/service_config.py`
- Create: `app/models/packet_log.py`
- Create: `app/models/system_log.py`
- Create: `app/services/logging_service.py`
- Create: `app/services/packet_logger.py`

- [ ] Add service, packet, and system log models.
- [ ] Configure rotating file handlers for application and packet logs.
- [ ] Add helpers to persist system logs and packet logs safely.

### Task 4: UDP Relay MVP Runtime

**Files:**
- Create: `app/services/runtime_manager.py`
- Create: `app/services/udp_server.py`
- Create: `app/utils/__init__.py`
- Create: `app/utils/codec.py`
- Test: `tests/test_codec.py`
- Test: `tests/test_udp_relay.py`

- [ ] Add codec helpers for hex/text conversion and safe decoding.
- [ ] Write failing tests for codec behavior and relay state update behavior.
- [ ] Implement `UDPRelayService` with config update, start/stop, manual send, RX/TX counters, last client tracking, and packet/system logging hooks.
- [ ] Add runtime manager ownership for the singleton UDP relay service.

### Task 5: Web UI Routes And Templates

**Files:**
- Create: `app/routers/pages.py`
- Create: `app/routers/ws.py`
- Create: `app/templates/base.html`
- Create: `app/templates/login.html`
- Create: `app/templates/dashboard.html`
- Create: `app/templates/udp_server.html`
- Create: `app/templates/packets.html`
- Create: `app/templates/logs.html`
- Create: `app/static/app.css`
- Create: `app/static/app.js`

- [ ] Add SSR routes for login, dashboard, UDP server, packets, and logs pages.
- [ ] Add HTMX form endpoints for updating UDP config and runtime actions.
- [ ] Add WebSocket log streaming for recent runtime events.

### Task 6: Deployment And Operations Assets

**Files:**
- Create: `scripts/init_db.py`
- Create: `scripts/preflight.py`
- Create: `scripts/run.py`
- Create: `Caddyfile.example`
- Create: `systemd/app.service`
- Create: `README.md`

- [ ] Add database bootstrap and admin initialization script.
- [ ] Add preflight checks for environment, directories, and imports.
- [ ] Add Linux deployment examples for Caddy and systemd.
- [ ] Document local and production startup.

### Task 7: Verification

**Files:**
- Modify: `tests/test_codec.py`
- Modify: `tests/test_udp_relay.py`

- [ ] Run focused pytest for codec and relay tests.
- [ ] Run import verification for the FastAPI app.
- [ ] Run startup preflight successfully.
- [ ] Capture remaining gaps for next phase: TCP/UDP client, users admin page, richer filters.

---

## Phase 2 Progress Update

Completed after the initial stage plan:

- TCP Server MVP runtime added under `app/services/tcp_server.py`
- `RuntimeManager` now owns both UDP relay and TCP server runtimes
- `/tcp-server` now renders a real SSR page instead of the placeholder
- TCP listener config persists into `service_configs` as `name="tcp_server"`
- Manual TCP send, client disconnect, TX/RX counters, packet logs, and system logs are wired
- Focused TCP tests added in `tests/test_tcp_server.py`
- TCP/UDP Client MVP runtime added under `app/services/client_runtime.py`
- `RuntimeManager` now also owns the single client runtime
- `/client` now renders a real SSR page instead of the placeholder
- Client config persists into `service_configs` as `name="client_runtime"`
- TCP connect/disconnect and TCP/UDP manual send are wired through `/client`
- Client packet logs and system logs are written for runtime traffic and actions
- Focused Client tests added in `tests/test_client_runtime.py` and `tests/test_client_page.py`

Still intentionally out of scope for the next phase:

- 用户管理页面
- 更完整的筛选与运行态审计
