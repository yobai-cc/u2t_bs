# 2026-04-08 Phase 2 Release Notes

## Summary

This update completes the Phase 2 TCP/UDP runtime expansion for the current MVP scope.
The web platform now supports both inbound TCP server workflows and outbound TCP/UDP client workflows under the existing FastAPI monolith.

## Included In This Phase

### TCP Server MVP

- Added `app/services/tcp_server.py` runtime
- Added `/tcp-server` SSR page
- Supports listener config persistence
- Supports server start/stop
- Supports connected client listing
- Supports manual send to a selected client
- Supports disconnecting a selected client
- Tracks TCP TX/RX byte counters
- Writes TCP packet logs and system logs

### TCP/UDP Client MVP

- Added `app/services/client_runtime.py`
- Extended `RuntimeManager` to own a single outbound client runtime
- Replaced `/client` placeholder with a real SSR page
- Supports client config persistence in `service_configs`
- Supports `TCP` and `UDP` protocol selection
- Supports connect/disconnect actions
- Supports manual send for TCP and UDP
- Supports TCP receive loop and UDP reply receive
- Tracks client TX/RX byte counters
- Writes client packet logs and system logs
- Enforces viewer read-only UI on `/client`
- Blocks client config updates while the runtime is running

## Persistence And Logging

- Client config is persisted as:
  - `name="client_runtime"`
  - `service_type="client"`
- TCP server config is persisted as:
  - `name="tcp_server"`
  - `service_type="tcp_server"`
- Runtime traffic continues to reuse:
  - `packet_logs`
  - `system_logs`

## Supporting Infrastructure Adjustment

- `app/db.py` now ensures the SQLite data directory exists before engine use
- `app/db.py` now initializes database tables on import

This was needed so clean worktrees, focused tests, and startup verification do not depend on a pre-created local database.

## Verification Performed

### Focused Tests

Command:

```bash
.venv\Scripts\pytest tests/test_codec.py tests/test_udp_relay.py tests/test_tcp_server.py tests/test_client_runtime.py tests/test_client_page.py -v
```

Result:

- `22 passed`

### Preflight

Command:

```bash
.venv\Scripts\python scripts/preflight.py
```

Result:

- `preflight ok`

### Startup Verification

- Verified `scripts/run.py` starts the application on `127.0.0.1:8080`

### Manual Runtime Verification

- TCP client manual send verified against a local echo-style server
- UDP client manual send verified against a local reply responder
- Verified packet logs contain both `client -> remote` and `remote -> client`
- Verified system logs contain client connect/send/receive/disconnect events

## Commits Included

- `e3a7b8e feat: add tcp/udp client runtime mvp`
- `b2fc2bf fix: block client config update while running`

## Known Remaining Scope

These items remain intentionally out of scope after this phase:

- 用户管理页面
- 更完整的 packets/logs 筛选
- 更完整的运行态审计与错误展示
- Client 多配置档案、自动重连、定时发送等增强能力

## Operator Notes

- `/client` is intentionally minimal and page-refresh based
- `admin` and `operator` can operate the client runtime
- `viewer` can only inspect state
- If the client is already running, config changes must wait until disconnect
