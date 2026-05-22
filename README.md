# KOL Monitor Trade

实时接入 Telegram、Discord 和 WxPusher 消息，并在本系统仪表盘查看连接状态、实时日志和运行统计。消息会先进入统一事件流并写入本地 MySQL；如配置了 `FORWARD_RULES`，再执行跨平台转发。

## 启动

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m app.telegram_monitor login
python run.py
```

启动前请确认本机 MySQL 已运行，`.env` 中的 `MYSQL_USER` 和 `MYSQL_PASSWORD` 有创建数据库和表的权限。系统启动时会自动创建 `MYSQL_DATABASE` 和 `log_entries` 表。
首次使用 Telegram 用户账号监听时，需要先执行一次登录命令，按提示输入手机号、验证码和两步验证密码。登录成功后会在 `TELEGRAM_SESSION_PATH` 保存本地会话，后续启动无需重复登录。

打开 `http://localhost:8000` 查看仪表盘。

## 配置

- `MYSQL_HOST` / `MYSQL_PORT`：本地 MySQL 地址，默认 `127.0.0.1:3306`。
- `MYSQL_USER` / `MYSQL_PASSWORD`：MySQL 登录用户和密码。
- `MYSQL_DATABASE`：日志库名，默认 `kol_monitor_trade`。
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`：Telegram 用户客户端 API 凭证。
- `TELEGRAM_SESSION_PATH`：本地用户会话文件路径，默认 `data/telegram_user`。
- `TELEGRAM_PROXY_URL`：可选，Telegram 连接代理，例如 `socks5://127.0.0.1:7897`。
- `TELEGRAM_MONITOR_CHANNELS`：可选，逗号分隔的群组或频道 ID。
- `DISCORD_MODE`：Discord 接入模式，`bot` 为官方 Bot 模式，`self` 为用户账号监听模式。
- `DISCORD_BOT_TOKEN`：Discord Bot Token，`DISCORD_MODE=bot` 时使用。
- `DISCORD_USER_TOKEN`：Discord 用户账号 Token，`DISCORD_MODE=self` 时使用。
- `DISCORD_SELF_ALLOW_SEND`：self 模式是否允许发送消息，默认 `false`，避免误用用户账号自动发言。
- `DISCORD_MONITOR_CHANNELS`：可选，逗号分隔的频道 ID。
- `WXPUSHER_DEVICE_TOKEN`：WxPusher 扩展登录态 Token，用于 REST 轮询补偿。
- `WXPUSHER_PUSH_TOKEN`：WxPusher WebSocket 推送 Token，用于实时监听。
- `WXPUSHER_ENABLE_POLLING`：是否开启 REST 轮询，建议先开启。
- `WXPUSHER_ENABLE_WEBSOCKET`：是否开启 WebSocket 实时通道。
- `WXPUSHER_POLL_INTERVAL_SECONDS`：轮询间隔，程序会限制最低 30 秒。
- `FORWARD_RULES`：可选 JSON 数组，用于 Telegram/Discord 到目标频道的转发。

Discord Bot 需要开启 Message Content Intent，并具备读取频道消息和发送消息权限。Telegram 用户客户端会监听该账号可见的群组或频道，可用频道 ID 或 `@username` 限制 `TELEGRAM_MONITOR_CHANNELS`。

如无法邀请 Discord Bot，可设置 `DISCORD_MODE=self` 并配置 `DISCORD_USER_TOKEN`，程序会使用用户账号能看到的频道进行监听。该模式依赖 `selfcord.py`，来自 `dolfies/discord.py-self` 的 renamed 分支；这类用户账号自动化不属于 Discord 官方推荐接入方式，存在账号风控和服务条款风险，请只在你明确接受风险时启用。

## 外部接入

```bash
curl -X POST http://localhost:8000/api/ingest ^
  -H "Content-Type: application/json" ^
  -d "{\"platform\":\"system\",\"content\":\"外部消息\",\"source_channel\":\"script\"}"
```

常用接口：

- `GET /api/status`：连接状态和运行状态。
- `GET /api/discord/channels`：列出当前 Discord 连接可见的服务器频道 ID，用于挑选 `DISCORD_MONITOR_CHANNELS`。
- `GET /api/logs?limit=50&platform=telegram&level=info`：查询历史日志。
- `GET /api/stats`：统计摘要。
- `GET /api/health`：健康检查。
