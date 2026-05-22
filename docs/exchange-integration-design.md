# 交易所与策略执行接入方案

## 目标

把当前 Telegram、Discord、WxPusher 收到的交易信息，从“日志和转发”升级为“信号解析、风控确认、交易执行、订单回报”的闭环系统。

第一阶段不建议直接全自动实盘。推荐顺序是：

1. 解析信号并入库。
2. 纸面交易，验证策略解析和风控。
3. 人工确认后下单。
4. 小额度实盘自动下单。
5. 增加多交易所、多账户和更复杂的仓位管理。

## 官方接口事实

- Binance Spot 下单接口是 `POST /api/v3/order`，交易接口需要签名、时间戳和有效 API Key；`POST /api/v3/order/test` 可以校验下单参数和签名但不进入撮合。
- Binance USD-M Futures 下单接口是 `POST /fapi/v1/order`，请求必须包含 `timestamp`，合约模式下要区分单向模式和双向持仓模式。
- Bitget Spot 下单接口是 `POST /api/v2/spot/trade/place-order`，请求头使用 `ACCESS-KEY`、`ACCESS-SIGN`、`ACCESS-PASSPHRASE` 和 `ACCESS-TIMESTAMP`。
- Bitget Futures 下单接口是 `POST /api/v2/mix/order/place-order`；官方最佳实践强调使用 `clientOid`，并说明下单响应只代表交易所已接收请求，最终状态要通过订单查询或私有 WebSocket 确认。

参考：

- Binance Spot Trading Endpoints: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints
- Binance Request Security: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/request-security
- Binance USD-M Futures New Order: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order
- Bitget Spot Place Order: https://www.bitget.com/zh-CN/api-doc/classic/spot/trade/Place-Order
- Bitget Best Practices: https://www.bitget.com/api-doc/classic/best-practices

## 总体架构

```mermaid
flowchart LR
    A["消息源"] --> B["统一消息服务"]
    B --> C["信号解析器"]
    C --> D["信号候选池"]
    D --> E["策略引擎"]
    E --> F["风控引擎"]
    F --> G["执行编排器"]
    G --> H["交易所适配器"]
    H --> I["Binance / Bitget"]
    I --> J["订单与成交回报"]
    J --> K["状态同步与审计"]
```

核心原则：

- 消息监听不直接下单，只产生日志和候选信号。
- 策略不直接调用交易所，只输出标准化交易意图。
- 风控是下单前的强制闸门。
- 交易所返回结果必须落库，不能只写日志。
- 使用 `clientOrderId` / `clientOid` 做幂等键，防止重复下单。
- 所有实盘动作必须能从原始消息追溯到最终订单。

## 模块拆分

建议新增 3 个子域，避免把交易逻辑塞进现有监控器：

```text
app/signals/
  __init__.py
  parser.py
  service.py
  profiles.py

app/trading/
  __init__.py
  models.py
  service.py
  risk.py
  repo.py
  config.py

app/exchanges/
  __init__.py
  base.py
  binance.py
  bitget.py
  factory.py
```

职责边界：

- `signals`：把原始文本解析成标准信号，不关心账户和下单。
- `trading`：把信号转为交易意图，执行风控、状态流转、审计落库。
- `exchanges`：封装交易所认证、签名、下单、撤单、订单查询、账户查询。

这样做可以避免僵化和循环依赖：交易所适配器不知道消息源，消息源也不知道交易所。

## 标准对象

`SignalCandidate`：

- `id`
- `source_log_id`
- `source_platform`
- `source_channel`
- `raw_text`
- `symbol`
- `market_type`: `spot` / `usdt_futures`
- `direction`: `long` / `short` / `buy` / `sell`
- `entry_price`
- `entry_range_low`
- `entry_range_high`
- `stop_loss`
- `take_profits_json`
- `leverage`
- `confidence`
- `status`: `parsed` / `needs_review` / `approved` / `rejected` / `expired`

`TradeIntent`：

- `id`
- `signal_id`
- `strategy_id`
- `exchange`
- `account_key`
- `symbol`
- `market_type`
- `side`
- `position_side`
- `order_type`
- `price`
- `quantity`
- `quote_amount`
- `leverage`
- `margin_mode`
- `reduce_only`
- `time_in_force`
- `dry_run`
- `status`: `pending_risk` / `blocked` / `ready` / `submitted` / `filled` / `failed`

`ExchangeOrder`：

- `id`
- `intent_id`
- `exchange`
- `client_order_id`
- `exchange_order_id`
- `symbol`
- `request_json`
- `response_json`
- `status`
- `error_message`
- `created_at`
- `updated_at`

数据库继续保持只用 ID 和索引，不加外键，避免后续迁移被交易执行状态绑死。

## 策略接入方式

第一版策略引擎建议做成规则链：

1. 来源白名单：只处理指定频道、指定作者、指定 WxPusher 来源。
2. 文本识别：解析币种、方向、入场、止损、止盈、杠杆。
3. 置信度判定：缺少止损、币种不明确、价格区间矛盾时进入人工审核。
4. 信号归一化：例如 `BTC` 归一到 `BTCUSDT`。
5. 风控计算：根据账户权益、单笔风险、最大杠杆、最大仓位生成订单数量。
6. 执行模式：`paper`、`manual_confirm`、`live` 三档。

不要让策略直接写死到某个交易所。策略输出的是 `TradeIntent`，交易所适配器负责把它翻译成 Binance 或 Bitget 参数。

## 风控闸门

强制检查：

- 是否启用真实交易。
- API Key 是否只给了必要权限。
- 是否在允许的交易所、账户、币种、市场类型内。
- 单笔最大亏损金额。
- 单币种最大仓位。
- 全账户最大风险敞口。
- 每日最大下单次数。
- 每日最大亏损熔断。
- 信号是否过期。
- 是否已经存在相同来源消息的订单。
- 是否缺少止损。
- 是否超过交易所最小下单量和价格步长。

默认策略：

- 无止损不自动实盘。
- 解析置信度低不自动实盘。
- 新交易所默认只能 `paper`。
- 第一次实盘必须走人工确认。

## 交易所适配器接口

统一接口建议包含：

- `ping()`
- `get_server_time()`
- `get_symbol_rules(symbol, market_type)`
- `get_balances()`
- `get_positions()`
- `place_order(order_request)`
- `cancel_order(symbol, client_order_id)`
- `get_order(symbol, client_order_id)`
- `stream_user_events(callback)`

Binance 和 Bitget 的差异收敛在适配器内部：

- Binance 使用 `X-MBX-APIKEY` 和 `signature`。
- Bitget 使用 `ACCESS-KEY`、`ACCESS-SIGN`、`ACCESS-PASSPHRASE`、`ACCESS-TIMESTAMP`。
- Binance Spot 用 `newClientOrderId`，Bitget 用 `clientOid`。
- Futures 要显式处理单向/双向持仓、杠杆、保证金模式。

## 执行流程

1. 消息进入 `MessageService` 并保存为 `log_entries`。
2. `SignalService` 根据消息来源和规则解析候选信号。
3. 候选信号写入 `signal_candidates`。
4. `TradingService` 把已批准信号转成 `TradeIntent`。
5. `RiskEngine` 执行硬性风控。
6. 风控通过后进入 `paper` 或 `manual_confirm`。
7. 用户确认或自动策略放行后，`ExchangeRouter` 选择交易所适配器。
8. 下单请求落库，发送到交易所。
9. 交易所返回 `orderId` 后更新 `exchange_orders`。
10. 私有 WebSocket 或订单轮询确认最终状态。

## 实施顺序

第一期：只做信号候选和纸面交易。

- 增加 `signals` 和 `trading` 基础模型。
- 从现有消息日志中解析信号。
- 仪表盘显示待确认信号、纸面订单、拒绝原因。
- 不接真实 API Key。

第二期：接 Bitget 测试执行。

- 实现 Bitget 适配器。
- 支持 `paper` 和 `manual_confirm`。
- 只允许白名单币种和固定小金额。
- 订单使用唯一 `clientOid`。

第三期：接 Binance。

- 实现 Binance Spot / Futures 适配器。
- 支持测试下单接口和真实订单查询。
- 增加交易所 symbol 规则缓存。

第四期：自动执行。

- 按策略维度开启 `live`。
- 增加熔断、撤单、仓位同步、成交回报。
- 增加“停止所有自动交易”的全局开关。

## 配置建议

`.env` 只放凭证和全局开关：

```text
TRADING_ENABLED=false
TRADING_MODE=paper
TRADING_DEFAULT_EXCHANGE=bitget
TRADING_MAX_DAILY_LOSS_USDT=50
TRADING_MAX_ORDER_RISK_USDT=5

BITGET_API_KEY=
BITGET_API_SECRET=
BITGET_API_PASSPHRASE=
BITGET_ENABLE_LIVE=false

BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_ENABLE_LIVE=false
```

策略、币种白名单、账户路由建议放数据库或独立配置文件，不建议全部塞进 `.env`。

## 关键风险

- KOL 文本歧义高，不能把自然语言解析结果直接视为交易指令。
- 交易所响应成功不等于成交成功。
- WebSocket 断线会造成状态滞后，必须有 REST 补偿查询。
- 市价单滑点不可控，第一版更适合限价或小额。
- API Key 必须限制权限、限制 IP、禁止提现权限。
- 自动交易必须有全局熔断按钮。

## 推荐决策

优先做 Bitget Futures 的纸面交易和人工确认链路，因为它和当前“信号驱动交易”的目标更贴近；Binance 作为第二个适配器接入，用来验证抽象是否足够通用。

不要一开始做复杂策略平台。先把“消息到信号、信号到风控、风控到订单、订单到回报”这条主链路做稳。
