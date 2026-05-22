# WxPusher 消息监控技术方案

## 目标

在用户本人授权的 WxPusher 登录态下，监控当前账号收到的新消息，并把消息交给 `kol-monitor-trade` 做后续处理，例如写日志、入库、转发、触发交易辅助流程或通知前端。

本方案同时覆盖两种实现：

- 方案一：REST 轮询消息列表，稳定补偿为主。
- 方案二：WebSocket 实时监听，低延迟提醒为主。

推荐落地顺序：先实现 REST 轮询，再接入 WebSocket，最后用 REST 做 WebSocket 漏消息补偿。

## 前提与边界

- 仅用于监控自己的 WxPusher 账号消息。
- 依赖 WxPusher 客户端内部接口，不属于官方公开稳定 API，后续可能变更。
- `deviceToken` 和 `pushToken` 都是敏感凭证，不写入代码、不提交仓库、不打印完整日志。
- 轮询间隔不要过短，建议 30 到 120 秒，避免触发风控或影响服务。

## 凭证说明

| 凭证 | 用途 | 推荐用途 |
| --- | --- | --- |
| `deviceToken` | 登录态 REST 接口鉴权 | 拉取消息列表、补偿漏消息 |
| `pushToken` | WebSocket 推送通道标识 | 实时接收新消息通知 |
| `deviceUuid` | 设备绑定标识 | 仅在后续重新注册设备时需要 |

Chrome 扩展里通常可以在扩展调试控制台读取：

```js
chrome.storage.local.get(['pushToken', 'deviceToken', 'deviceUuid'], console.log)
```

## 配置设计

建议放在项目 `.env` 中：

```env
WXPUSHER_DEVICE_TOKEN=
WXPUSHER_PUSH_TOKEN=
WXPUSHER_DEVICE_UUID=
WXPUSHER_PLATFORM=Chrome-Windows
WXPUSHER_VERSION=1.0.0
WXPUSHER_POLL_INTERVAL_SECONDS=60
WXPUSHER_ENABLE_POLLING=true
WXPUSHER_ENABLE_WEBSOCKET=false
```

安全建议：

- `.env` 必须在 `.gitignore` 中。
- 日志只显示 token 前后 4 位。
- Web 管理页不要展示完整 token。
- 发生 `1002 需要登陆` 时提示用户重新获取 token。

## 方案一：REST 轮询消息列表

### 接口

```text
GET https://wxpusher.zjiecode.com/api/need-login/device/message/list-v2
```

请求头：

```text
deviceToken: ${WXPUSHER_DEVICE_TOKEN}
version: ${WXPUSHER_VERSION}
platform: ${WXPUSHER_PLATFORM}
Content-Type: application/json;charset=UTF-8
```

查询参数：

```text
messageId=9223372036854775807
scene=1
key=
```

加载更多时，把 `messageId` 换成当前列表最后一条消息的 `messageId`。

常见返回字段：

```json
{
  "messageId": 123,
  "url": "https://wxpusher.zjiecode.com/api/message/xxx",
  "sourceUrl": "https://example.com",
  "summary": "消息摘要",
  "name": "消息来源",
  "read": false,
  "createTime": 1710000000000
}
```

未登录或 token 失效：

```json
{
  "code": 1002,
  "msg": "需要登陆",
  "data": null,
  "success": false
}
```

### 流程

1. 启动时读取 `.env`。
2. 检查 `WXPUSHER_DEVICE_TOKEN` 是否存在。
3. 每隔 `WXPUSHER_POLL_INTERVAL_SECONDS` 拉取最新消息列表。
4. 按 `messageId` 去重。
5. 对新消息执行统一处理。
6. 保存最后处理时间和消息 ID。
7. 如果接口返回 `1002`，暂停轮询并提示登录态失效。

### 去重与状态

建议新增本地存储表或 JSON 状态文件，最小字段：

```text
message_id
summary
name
url
source_url
read
create_time
processed_at
raw_payload
```

去重规则：

```text
messageId 已存在：跳过
messageId 不存在：保存并处理
```

### 优点

- 实现简单。
- 容易补偿漏消息。
- 进程重启后仍可从服务端拉取近期消息。
- 适合做第一版 MVP。

### 缺点

- 有轮询延迟。
- 依赖内部接口，返回结构可能变化。
- 轮询太频繁可能被限制。

## 方案二：WebSocket 实时监听

### 连接地址

```text
wss://wxpusher.zjiecode.com/ws?version=${WXPUSHER_VERSION}&platform=${WXPUSHER_PLATFORM}&pushToken=${WXPUSHER_PUSH_TOKEN}
```

Chrome 扩展源码里使用的核心消息类型：

| 类型 | 含义 |
| --- | --- |
| `201` | 服务端心跳 |
| `202` | 初始化消息，可能返回新的 `pushToken` |
| `204` | 升级提示 |
| `20001` | 推送通知消息 |

客户端心跳上行：

```json
{
  "msgType": 101
}
```

推送通知常见字段：

```json
{
  "msgType": 20001,
  "title": "标题",
  "summary": "摘要",
  "qid": "详情查询 ID",
  "url": "详情链接",
  "contentType": 1,
  "createTime": 1710000000000
}
```

### 流程

1. 启动时读取 `WXPUSHER_PUSH_TOKEN`。
2. 建立 WebSocket 连接。
3. 收到 `202` 初始化消息时，若包含新 `pushToken`，更新本地配置或提示用户更新。
4. 定时发送 `101` 心跳。
5. 收到 `20001` 时，把消息交给统一处理器。
6. 连接断开后指数退避重连。
7. 定期触发 REST 轮询补偿，防止实时通道漏消息。

### 重连策略

建议重连间隔：

```text
5s, 10s, 15s, 30s, 60s, 120s
```

达到最大间隔后保持 120 秒重试一次。连续失败时记录告警，但不要刷屏。

### 优点

- 延迟低。
- 适合实时提醒和前端状态刷新。
- 不需要高频轮询。

### 缺点

- 连接状态处理复杂。
- 可能因为网络、服务端策略、token 变化导致断线。
- 收到的通常是通知摘要，完整内容仍可能需要访问 `url` 或用 REST 补偿。

## 统一消息处理器

两种方案都不要直接写业务逻辑，而是进入同一个处理器：

```text
WxPusherCollector
  -> normalize_message
  -> deduplicate
  -> persist
  -> dispatch
```

标准化后的内部消息结构：

```json
{
  "source": "wxpusher",
  "channel": "polling 或 websocket",
  "message_id": "123 或 qid",
  "title": "标题",
  "summary": "摘要",
  "sender": "来源名称",
  "url": "详情链接",
  "source_url": "原文链接",
  "read": false,
  "created_at": "ISO 时间",
  "raw": {}
}
```

## 正文解析

第一版只保存 `summary` 和 `url`。如果后续需要全文识别，再增加详情页解析：

1. 请求消息里的 `url`。
2. 判断返回内容是 HTML、Markdown 还是跳转链接。
3. 清理 HTML 标签，提取正文。
4. 失败时保留摘要，不影响主流程。

注意：详情页可能依赖服务端策略，解析失败属于可接受情况。

## 与现有项目集成建议

建议新增模块：

```text
app/services/wxpusher/
  __init__.py
  client.py
  polling.py
  websocket.py
  normalizer.py
  store.py
```

但当前 `app` 目录文件数量已经较多，建议用子目录承载，避免继续扩大单个目录复杂度。

配置放入现有 `app/config.py`，运行入口由现有 `run.py` 或后台任务管理器启动。

前端可以只展示：

- WxPusher 连接状态
- 最近拉取时间
- 最近消息摘要
- token 是否配置
- REST / WebSocket 是否启用

## MVP 范围

第一阶段：

- REST 轮询
- `messageId` 去重
- 写入日志或本地存储
- token 失效提示

第二阶段：

- WebSocket 实时监听
- 断线重连
- REST 周期性补偿
- 状态展示

第三阶段：

- 详情页正文解析
- 关键词过滤
- Webhook 转发
- 与交易监控流程联动

## 风险与控制

| 风险 | 控制方式 |
| --- | --- |
| 内部接口变更 | 封装客户端层，集中处理响应变化 |
| token 泄露 | 本地 `.env` 保存，日志脱敏 |
| 轮询过频 | 默认 60 秒，允许配置但设置下限 |
| WebSocket 漏消息 | REST 定期补偿 |
| 详情页解析失败 | 摘要和链接仍入库 |
| 重复处理 | `messageId` / `qid` 去重 |

## 推荐结论

落地时采用“双通道，一主一辅”：

- REST 轮询作为可靠来源，负责消息列表同步和漏消息补偿。
- WebSocket 作为实时来源，负责降低新消息感知延迟。

第一版先完成 REST 轮询，确认 `deviceToken` 可用、消息结构稳定后，再增加 WebSocket。这样能更快接入现有项目，也能把凭证、去重、存储这些关键基础打稳。
