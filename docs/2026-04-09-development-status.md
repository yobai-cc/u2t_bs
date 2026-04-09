# 2026-04-09 Development Status

## Current State

- 当前仓库已完成 FastAPI + Jinja2 SSR 形态下的 Phase 2 主要功能闭环。
- TCP Server、TCP/UDP Client、Users 页面、Packets / Logs 最小筛选均已落地。
- 本轮已完成交付测试前收口和兼容性 warning 清理。
- `master` 上的 UDP 服务已收敛为固定自动回复单模式；旧 relay/cloud 语义仅保留在归档分支。

## Completed Scope

- 用户名密码登录与 Session 会话
- Dashboard
- UDP Server 页面与基础运行态操作
  - 当前行为为设备发包后立即回发 `custom_reply_data`
  - `custom_reply_data` 为空时仅记录 warning，不回包
- TCP Server 页面与基础运行态操作
- TCP/UDP Client 页面与基础运行态操作
- Users 页面：列表、创建用户、启用/禁用用户
- Packets / Logs 最小筛选
- client / tcp-server / udp-server 运行态失败 inline error 展示
- 失败事件写入 system logs

## This Round Closure

- 增加真实 HTTP 集成测试，覆盖：
  - login / failed login / logout
  - 未登录访问受保护页面跳转
  - admin / operator / viewer 真实权限行为
  - 一个真实 POST 页面流程
- 增加 `/ws/runtime` 最小 smoke 测试
- 新增 tester-facing 文档：`docs/2026-04-09-delivery-test-guide.md`
- 清理兼容性 warning：
  - `TemplateResponse` 旧签名 warning
  - `on_event("startup")` deprecation warning

## Latest Verification

- Full `pytest`: `52 passed`
- Focused UDP closure suite: `python -m pytest tests/test_udp_relay.py tests/test_udp_server_page.py tests/test_filters_pages.py -q`
- `preflight`: `preflight ok`
- Startup smoke: PASS

## Known Limits

- Client 仍为 single-profile only
- Pages 仍为 SSR refresh-based，不是 SPA
- 运行态审计为最小闭环，不包含更高级的审计分析能力
- 不包含 auto-reconnect、scheduler、multi-profile 等增强能力

## Document Guide

- 当前状态总览：`README.md`
- 文档导航：`docs/INDEX.md`
- 交付测试说明：`docs/2026-04-09-delivery-test-guide.md`
- `docs/2026-04-08-phase-2-handoff.md` 和 `docs/2026-04-08-phase-2-release-notes.md` 属于历史时点文档，不代表当前最新状态

## Pending Docs Classification

- `docs/2026-04-08-phase-2-handoff.md`
  - 历史交接记录，建议保留为历史快照。
- `docs/2026-04-08-phase-2-release-notes.md`
  - 历史发布记录，建议保留为历史快照。
- `docs/superpowers/plans/2026-04-09-delivery-test-closure.md`
  - 本轮收口执行计划，属于过程文档。
- `docs/superpowers/plans/2026-04-09-packets-logs-filters.md`
  - 功能计划文档，属于过程文档。
- `docs/superpowers/specs/2026-04-09-packets-logs-filters-design.md`
  - 设计文档，属于过程文档。

这些文件可以保留在仓库中，但不应承担“当前状态总览”职责。
