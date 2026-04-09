# Packets And Logs Filters Design

## Goal

在保持当前 FastAPI + Jinja2 SSR 模式不变的前提下，为 `/packets` 和 `/logs` 页面补充最小但实用的筛选能力，方便按协议、服务、方向、级别、分类和核心文本内容快速定位记录。

## Current Context

- 当前 `GET /packets` 已支持两个查询参数：`protocol` 和 `limit`。
- 当前 `GET /logs` 仅展示最近 200 条系统日志，不支持筛选。
- 页面模板为服务端渲染，使用 GET 表单刷新页面，现有 `packets.html` 已有基础筛选表单。
- 本轮目标是“更完整的 packets/logs 筛选”，不引入运行态错误处理、SPA、WebSocket 新行为或额外前端构建。

## In Scope

### `/packets`

- 保留现有 `protocol` 与 `limit`
- 新增 `service` 筛选
- 新增 `direction` 筛选
- 新增关键字 `q` 搜索
- 页面表格新增 `service_type` 列，避免筛选后信息不可见

### `/logs`

- 新增 `level` 筛选
- 新增 `category` 筛选
- 新增关键字 `q` 搜索
- 新增 `limit` 控制

### 搜索策略

- 关键字搜索只匹配核心文本字段，不做全字段模糊搜索
- 所有筛选继续通过 GET query string 完成
- 所有结果仍按 `created_at DESC` 排序

## Out Of Scope

- 时间范围筛选
- 排序方式切换
- 关键字高亮
- 分页
- 统计视图
- 运行态错误提示统一化
- packet/local endpoint 展示改造

## Data Model Context

### `PacketLog`

当前可用字段：

- `service_type`
- `protocol`
- `direction`
- `src_ip`
- `src_port`
- `dst_ip`
- `dst_port`
- `data_hex`
- `data_text`
- `length`
- `created_at`

### `SystemLog`

当前可用字段：

- `level`
- `category`
- `message`
- `detail`
- `created_at`

## Route Design

### GET `/packets`

新增查询参数：

- `protocol: str | None`
- `service: str | None`
- `direction: str | None`
- `q: str | None`
- `limit: int`

筛选逻辑：

- `protocol` 精确匹配 `PacketLog.protocol`
- `service` 精确匹配 `PacketLog.service_type`
- `direction` 精确匹配 `PacketLog.direction`
- `q` 对以下字段做模糊匹配：
  - `PacketLog.data_text`
  - `PacketLog.data_hex`
  - `PacketLog.src_ip`
  - `PacketLog.dst_ip`

返回模板上下文新增：

- `selected_protocol`
- `selected_service`
- `selected_direction`
- `query_text`
- `limit`

### GET `/logs`

新增查询参数：

- `level: str | None`
- `category: str | None`
- `q: str | None`
- `limit: int`

筛选逻辑：

- `level` 精确匹配 `SystemLog.level`
- `category` 精确匹配 `SystemLog.category`
- `q` 对以下字段做模糊匹配：
  - `SystemLog.message`
  - `SystemLog.detail`

返回模板上下文新增：

- `selected_level`
- `selected_category`
- `query_text`
- `limit`

## Template Design

### `app/templates/packets.html`

在现有表单基础上新增：

- `service` 下拉框
- `direction` 下拉框
- `q` 文本输入框

表格新增一列：

- `服务`

列内容显示 `row.service_type`

### `app/templates/logs.html`

新增与 `packets` 风格一致的 GET 筛选表单，包含：

- `level` 下拉框
- `category` 下拉框
- `q` 文本输入框
- `limit` 数字输入框

保留现有日志表格展示。

## Query Behavior

### `packets` 关键字搜索范围

本轮只搜这些核心字段：

- `data_text`
- `data_hex`
- `src_ip`
- `dst_ip`

不搜索：

- 端口
- `service_type`
- `direction`
- `protocol`

因为这些字段已有独立枚举筛选，没必要在本轮重复混入关键字逻辑。

### `logs` 关键字搜索范围

本轮只搜：

- `message`
- `detail`

不搜索：

- `level`
- `category`

因为这两个字段同样已有独立枚举筛选。

## UX Behavior

- 提交筛选后整页刷新
- 已选筛选条件在表单中回显
- 没有结果时允许显示空表格，不额外新增“空状态设计”复杂度
- 与现有页面一致，优先保持朴素、稳定、可维护

## Implementation Strategy

- 仅修改 `app/routers/pages.py`
- 仅修改 `app/templates/packets.html`
- 仅修改 `app/templates/logs.html`
- 新增 focused tests 文件覆盖筛选行为

本轮不新增 repository/service 层抽象，避免为简单筛选引入不必要结构。

## TDD Plan

建议新增：

- `tests/test_filters_pages.py`

测试点：

1. `/packets` 可按 `service_type` 筛选
2. `/packets` 可按 `direction` 筛选
3. `/packets` 关键字可匹配 `data_text`
4. `/packets` 关键字可匹配 `src_ip` 或 `dst_ip`
5. `/logs` 可按 `level` 筛选
6. `/logs` 可按 `category` 筛选
7. `/logs` 关键字可匹配 `message`
8. `/logs` 关键字可匹配 `detail`

## Verification

完成后执行：

- `tests/test_filters_pages.py`
- 与 `pages.py` 相关的已有 focused 页面测试
- `scripts/preflight.py`
- 必要的启动验证

## Risks And Limits

- `pages.py` 会继续增长，但本轮遵循现有仓库结构，不额外拆分。
- `q` 搜索基于简单模糊匹配，适合当前 SQLite MVP，不追求复杂检索能力。
- `service`、`direction`、`level`、`category` 的下拉项先按当前已知值静态提供，不额外做动态 distinct 查询。
- 若后续要支持更细的排障体验，应单独规划“运行态审计与错误展示”阶段，不应在本轮顺手混入。
