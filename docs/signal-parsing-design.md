# 信号解析试验与设计方案

## 试验范围

本次从本地 MySQL 的 `log_entries` 抽取当前系统已有 WxPusher 消息：

- 原始 WxPusher 日志：90 条。
- 按 Discord 原文链接 / WxPusher 详情链接去重后：72 条。
- 对候选消息拉取 WxPusher 详情页正文后做临时规则解析。

第二版保守规则的分类结果：

| 类型 | 数量 | 含义 |
| --- | ---: | --- |
| `new_signal` | 9 | 明确喊单，能抽出部分交易字段 |
| `position_update` | 18 | 平仓、保本、减仓、加层、继续持有等 |
| `media_or_link` | 22 | 图片、外链或图片伴随评论 |
| `commentary` | 23 | 观点、复盘、研究、闲聊 |

这个比例说明：当前消息不是单纯的“每条都是一张订单”，而是一个连续交易上下文流。

## 样本观察

### 英文格式化喊单

示例：

```text
GOLD BUY NOW @ 4510 TP : 4530 TP : 4560 SL : 4482
GBPAUD SELL NOW @ 1.88300 TP : 1.87331 TP : 1.85421 SL : 1.89146
SELLING $XAUUSD Entry : 4540.00 SL : 4560.00 TP : 4453.54
```

这类适合规则解析，能稳定抽出：

- `symbol`
- `side`
- `entry_numbers`
- `take_profits`
- `stop_loss`

### 中文结构化喊单

示例：

```text
ZEC
方向：1倍空
入场：680附近建仓，725补仓
信心度：中
倍数：1倍
仓位：每次10%仓位
止盈：点位1：640附近（求稳） 点位2：610附近 点位3：550
止损：小幅涨破前高760一点
```

这类也适合规则解析，但要保留原文：

- `entry_text`: `680附近建仓，725补仓`
- `stop_loss_text`: `小幅涨破前高760一点`
- `take_profit_text`: 原始止盈句子

不要只存数字，因为“附近”“小幅涨破”“求稳”都是后续风控和人工确认需要的信息。

### 回复原单后的操作更新

示例：

```text
回复: [GBPAUD SELL NOW @ 1.88300 TP : 1.87331 TP : 1.85421 SL : 1.89146](...)
Set B.E
```

```text
Booked half profits now
Close first
Hold last
risk half of normal risk
```

这类不能当新开仓信号。正确设计是：

1. 先拆出 `reply_text` 和 `reply_url`。
2. 主体文本识别成 `position_update`。
3. 如果有 `reply_url`，直接关联原始信号。
4. 如果没有 `reply_url`，按来源、作者、频道、最近活跃信号做状态关联。

### 自然语言交易计划

示例：

```text
我打算在当前59附近空一手看看，预计空到52-53附近止盈，然后稍微涨破前高一点我就止损
```

这类能看出交易意图，但字段不是刚性的：

- `symbol` 可能来自前文，例如 HYPE / ZEC。
- `entry` 是“当前59附近”。
- `take_profit` 是“52-53附近”。
- `stop_loss` 是“稍微涨破前高一点”。
- 还包含“空一手”“高风险”“小仓位”等语义。

这种不适合直接自动下单，最多进入 `needs_review`。

## 解析器设计

建议采用三层解析，不要一上来全靠大模型。

### 第一层：消息标准化

输入是 `LogEntry`，输出 `NormalizedMessage`：

- 去重：优先用 Discord 原文链接，其次 WxPusher 详情链接。
- 展开详情：摘要中有 `...` 时必须拉详情正文。
- 清洗样板行：频道名、`Embeds`、`图片`、固定转发头。
- 拆分主体：`main_text`、`reply_text`、`reply_url`、`source_url`。
- 保留原文：任何解析结果都必须能回看完整正文。

### 第二层：规则解析

规则解析负责高确定性场景：

- 英文标准信号。
- 中文字段式信号。
- `TP / SL / Entry / @` 数字结构。
- `close / hold / BE / booked half / risk half / add layer` 更新动作。
- 图片、纯链接、系统噪音过滤。

规则解析输出 `confidence` 和 `missing_fields`，字段不齐不自动补。

### 第三层：大模型补充

大模型只处理规则无法高置信解析的消息：

- 自然语言计划。
- 多币种混在一条消息里。
- “前高附近”“涨破一点”“低倍小仓”这类模糊表达。
- 需要判断是观点、复盘、还是可执行信号。
- 需要从上下文推断 symbol 或操作对象。

大模型输出仍然必须走 schema 校验，不能直接进入交易执行。

## 是否需要大模型

结论：需要，但不应该做第一入口。

推荐策略：

- 第一版用规则解析覆盖标准喊单和明确更新。
- 规则解析置信度低于阈值时，进入人工审核或调用大模型。
- 大模型只负责“提取候选结构”和“解释不确定性”，不负责决定下单。
- 任何大模型结果都要带 `confidence`、`evidence_text`、`missing_fields`。
- 自动实盘只允许规则高置信且字段完整的信号。

换句话说：规则解析是主干，大模型是兜底和辅助审核。

## 建议字段

`signal_candidates`：

- `id`
- `source_log_id`
- `source_url`
- `reply_url`
- `parser_version`
- `parser_mode`: `rule` / `llm` / `manual`
- `category`: `new_signal` / `position_update` / `commentary` / `media_or_link`
- `symbol`
- `side`
- `entry_text`
- `entry_numbers_json`
- `take_profit_text`
- `take_profits_json`
- `stop_loss_text`
- `stop_loss`
- `leverage_text`
- `position_size_text`
- `confidence`
- `missing_fields_json`
- `evidence_text`
- `raw_text`
- `status`: `parsed` / `needs_review` / `approved` / `rejected`

`signal_updates`：

- `id`
- `source_log_id`
- `related_signal_id`
- `reply_url`
- `action`: `close` / `reduce` / `take_partial_profit` / `move_stop_to_breakeven` / `hold` / `add_layer` / `risk_modifier`
- `action_text`
- `quantity_text`
- `confidence`
- `raw_text`
- `status`

## 第一版实现建议

1. 新增 `app/signals/` 子目录。
2. 实现 `NormalizedMessage` 和 `SignalCandidate` 数据结构。
3. 实现规则解析器，只覆盖明确格式。
4. 新增解析预览接口，不自动下单。
5. 在仪表盘显示解析结果、缺失字段和原文证据。
6. 等人工审核几天样本后，再决定接入大模型。

第一版目标不是“解析所有消息”，而是把“能安全解析”和“必须人工判断”分开。
