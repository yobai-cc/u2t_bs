# U2T Web Platform

轻量级 Web 版 TCP/UDP 调试与转发平台，使用 FastAPI + Jinja2 + HTMX + SQLite 构建。

## 当前阶段

第一阶段 MVP 已包含：

- 用户名密码登录与 Session 会话
- Dashboard
- UDP Relay 服务骨架与固定规则
- 协议包日志页
- 系统日志页
- Caddy 与 systemd 示例配置

第二阶段当前已完成：

- TCP Server MVP
  - 监听配置保存
  - 启动/停止 TCP listener
  - 在线客户端列表
  - 面向指定客户端的手动发送
  - 客户端断开
  - TCP TX/RX 计数
  - TCP packet/system log 落库

第二阶段待补：

- TCP/UDP Client
- 用户管理页面
- 更完整的筛选与运行态审计

## 本地运行

以下命令主要用于开发机验证。项目最终部署目标是 Ubuntu 服务器。

1. 创建虚拟环境

```bash
python -m venv .venv
```

2. 安装依赖

```bash
.venv\Scripts\pip install -r requirements.txt
```

3. 初始化数据库和管理员

```bash
.venv\Scripts\python scripts/init_db.py
```

4. 启动预检查

```bash
.venv\Scripts\python scripts/preflight.py
```

5. 启动服务

```bash
.venv\Scripts\python scripts/run.py
```

默认登录账号来自 `.env` 或 `.env.example` 中的 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD`。

## TCP Server MVP 说明

- 页面入口：`/tcp-server`
- 默认监听配置：`0.0.0.0:9100`
- 支持保存 `bind_ip`、`bind_port`、`hex_mode`
- `admin` 和 `operator` 可执行启动、停止、发送、断开操作
- `viewer` 仅可查看状态和客户端列表
- TCP 流量会写入 `packet_logs`，可在 `/packets?protocol=TCP` 查看
- TCP 运行事件会写入 `system_logs`，可在 `/logs` 查看

## Linux 部署

以下步骤以 Ubuntu 22.04/24.04 为目标环境。

1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip caddy
```

2. 部署项目到目标目录

```bash
sudo mkdir -p /opt/u2t_web
sudo chown -R $USER:$USER /opt/u2t_web
```

3. 上传项目文件并进入目录

```bash
cd /opt/u2t_web
```

4. 初始化 Python 虚拟环境并安装依赖

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

5. 配置环境变量

```bash
cp .env.example .env
```

建议至少修改：

- `APP_ENV=production`
- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `SESSION_SECURE=true`

6. 初始化数据库与管理员

```bash
.venv/bin/python scripts/init_db.py
.venv/bin/python scripts/preflight.py
```

7. 安装 systemd 服务

```bash
sudo cp systemd/app.service /etc/systemd/system/u2t-web.service
sudo systemctl daemon-reload
sudo systemctl enable --now u2t-web.service
sudo systemctl status u2t-web.service
```

8. 配置 Caddy 反代 Web

将 `Caddyfile.example` 内容改成你的域名后写入 `/etc/caddy/Caddyfile`：

```bash
sudo systemctl reload caddy
```

9. 放行端口

- 80/443 由 Caddy 使用
- TCP/UDP 业务端口由本应用直接监听，需要在 Ubuntu 防火墙和云安全组中放行

可直接使用：

```bash
sudo bash scripts/bootstrap_ubuntu.sh
```

该脚本会完成虚拟环境、依赖安装、`.env` 初始化、数据库初始化与预检查。

## Ubuntu 运行说明

- Web 页面通过 Caddy 反代到 `127.0.0.1:8080`
- TCP/UDP 业务端口不经过 Caddy，由应用自身监听
- 建议生产环境使用独立域名，并将 `SESSION_SECURE=true`
- 若后续需要监听公网 UDP/TCP，请确保 `bind_ip` 配置为服务器实际可监听地址或 `0.0.0.0`

## 说明

- Web 由 Caddy 反向代理
- TCP/UDP 业务端口由应用自身监听
- 日志写入 `logs/app.log` 与 `logs/packets.log`
