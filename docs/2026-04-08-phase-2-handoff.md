# 2026-04-08 Phase 2 Handoff

## Current Repository State

- Branch: `master`
- Working tree: clean
- Phase 2 TCP Server MVP: complete
- Phase 2 TCP/UDP Client MVP: complete

## What Was Just Finished

### Client Runtime

- Added `app/services/client_runtime.py`
- Supports one active outbound runtime only
- TCP mode:
  - connect
  - disconnect
  - manual send
  - background receive loop
- UDP mode:
  - bind one transport
  - manual send
  - receive reply datagrams

### Runtime Manager

- `app/services/runtime_manager.py` now owns:
  - `udp_relay`
  - `tcp_server`
  - `client_runtime`

### Routes And UI

- `/client` is now a real page in `app/templates/client.html`
- Added routes in `app/routers/pages.py`:
  - `GET /client`
  - `POST /client/config`
  - `POST /client/connect`
  - `POST /client/disconnect`
  - `POST /client/send`
- Viewer role stays read-only
- Config changes are blocked while the client runtime is running

### Tests

- Added `tests/test_client_runtime.py`
- Added `tests/test_client_page.py`
- Focused suite currently passes:

```bash
.venv\Scripts\pytest tests/test_codec.py tests/test_udp_relay.py tests/test_tcp_server.py tests/test_client_runtime.py tests/test_client_page.py -v
```

## Important Behavior To Remember Tomorrow

### 1. Client Config Is Single-Profile Only

- There is only one saved client config
- It persists in `service_configs` as `name="client_runtime"`
- This phase does not support multiple presets or saved profiles

### 2. Running Client Cannot Be Reconfigured

- This was an intentional small fix after review
- UI disables the config form while running
- Route-level guard also blocks updates and returns message:
  - `Client 正在运行，请先断开再修改配置`

### 3. Error Handling Is Still Minimal

- Connect/send failures still bubble up in some cases
- There is not yet a unified route-level error rendering pattern
- If continuing Phase 2, a good next improvement is consistent runtime action error handling across:
  - UDP server
  - TCP server
  - Client

### 4. DB Bootstrap Behavior Changed

- `app/db.py` now creates the SQLite data directory if needed
- `app/db.py` also calls `init_db()` on import
- This made clean test/worktree startup reliable
- If this pattern is reconsidered later, re-check tests and startup assumptions first

## Recommended Next Development Order

### Option A: Finish Remaining Phase 2 Scope

Recommended if you want to close the phase cleanly.

1. 用户管理页面
2. packets/logs 更完整筛选
3. 统一运行态错误提示和审计展示

### Option B: Strengthen Runtime UX Before New Features

Recommended if you want to harden the current MVP first.

1. Add route-level error handling for connect/send/disconnect actions
2. Show runtime error messages inline on TCP/UDP/Client pages
3. Improve local endpoint visibility in packet logs
4. Add tests for failed connect, failed send, invalid hex input

## Suggested First Task Tomorrow

If you want the most practical next step, start here:

1. Add a real `/users` page instead of the placeholder
2. Keep it admin-only
3. Scope it to list users + create user + enable/disable user
4. Do not add password reset complexity unless needed

## Files Most Relevant For Next Session

- `app/routers/pages.py`
- `app/templates/client.html`
- `app/templates/tcp_server.html`
- `app/templates/udp_server.html`
- `app/models/user.py`
- `app/routers/auth.py`
- `docs/superpowers/plans/2026-04-08-web-tcp-udp-platform.md`
- `docs/superpowers/plans/2026-04-08-tcp-udp-client-mvp.md`

## Last Verified Commands

```bash
.venv\Scripts\pytest tests/test_codec.py tests/test_udp_relay.py tests/test_tcp_server.py tests/test_client_runtime.py tests/test_client_page.py -v
.venv\Scripts\python scripts/preflight.py
```

Expected last known results:

- `22 passed`
- `preflight ok`
