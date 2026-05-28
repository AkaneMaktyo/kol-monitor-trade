(function () {
    "use strict";

    const raw = (value) => String(value || "").trim();
    const code = (value) => raw(value).toLowerCase();
    const readable = (value) => raw(value).replace(/_/g, " ") || "--";
    const pick = (map, value) => map[code(value)] || readable(value);

    function action(value) {
        return pick({
            close: "平仓",
            take_partial_profit: "部分止盈",
            move_stop_to_breakeven: "移动保本",
            take_profit_hit: "止盈触发",
            hold: "继续持有",
            add_layer: "补仓",
            risk_modifier: "调整风险",
            preview: "预览",
            persist: "持久化",
            real_execute: "真实执行",
        }, value);
    }

    function positionSide(value) {
        return pick({ long: "多仓", short: "空仓", buy: "多仓", sell: "空仓" }, value);
    }

    function intentSide(value) {
        return pick({ long: "做多", short: "做空", buy: "买入", sell: "卖出" }, value);
    }

    function simpleSide(value) {
        return pick({ long: "多", short: "空" }, value);
    }

    function orderSide(side, tradeSide) {
        const trade = code(tradeSide);
        const value = code(side);
        if (trade === "close") return value === "buy" ? "平多" : "平空";
        if (trade === "open") return value === "buy" ? "买入开多" : "卖出开空";
        return intentSide(side);
    }

    function status(value) {
        return pick({
            live: "挂单中",
            new: "新订单",
            ready: "就绪",
            submitted: "已提交",
            failed: "执行失败",
            blocked: "已拦截",
            dry_run: "模拟执行",
            needs_review: "待复核",
            audit_only: "仅审计",
            parsed: "已解析",
            missing: "未就绪",
            fetched: "已抓取",
            not_needed: "无需补全",
            not_applicable: "不适用",
        }, value);
    }

    function mode(value) {
        return pick({ dry_run: "演练模式", auto_demo: "自动模拟盘" }, value);
    }

    function credential(value) {
        return pick({ ready: "已就绪", missing: "未就绪" }, value);
    }

    function category(value) {
        return pick({ new_signal: "新开仓信号", position_update: "仓位更新", commentary: "说明消息" }, value);
    }

    function kind(value) {
        return pick({ candidate: "候选信号", intent: "风控意图", update: "仓位更新", order: "订单结果" }, value);
    }

    function orderType(value) {
        return pick({ market: "市价", limit: "限价" }, value);
    }

    function field(value) {
        return pick({
            entry: "入场价",
            take_profit: "止盈",
            stop_loss: "止损",
            related_signal: "关联信号",
            reply_url: "回复链接",
            bitget_symbol: "交易所品种",
        }, value);
    }

    function reason(value) {
        const normalized = code(value);
        const direct = {
            historical_signal_stale: "历史信号已过时",
            low_confidence: "置信度不足",
            manual_review_required: "需要人工复核",
            missing_related_signal: "缺少关联信号",
            missing_reply_url: "缺少回复链接",
            missing_action: "缺少动作",
            unsupported_action: "动作暂不支持",
            missing_bitget_symbol: "缺少交易所品种",
        };
        if (direct[normalized]) return direct[normalized];
        if (normalized.startsWith("missing_")) return `缺少${field(normalized.slice(8))}`;
        if (normalized.startsWith("invalid_")) return `${field(normalized.slice(8))}无效`;
        return readable(value);
    }

    function reasonText(value) {
        return raw(value).split(",").filter(Boolean).map((part) => reason(part.trim())).join("、") || "--";
    }

    function replayDetail(item) {
        return {
            候选信号: {
                类别: category(item.candidate?.category),
                状态: status(item.candidate?.status),
                品种: item.candidate?.bitget_symbol || item.candidate?.symbol || "--",
                方向: simpleSide(item.candidate?.side),
                入场方式: orderType(item.candidate?.entry_order_type),
                入场参考: item.candidate?.entry_numbers || [],
                止盈: item.candidate?.take_profits || [],
                止损: item.candidate?.stop_loss || 0,
                缺失字段: (item.candidate?.missing_fields || []).map(field),
            },
            风控结果: {
                状态: status(item.risk?.status),
                原因: (item.risk?.reasons || []).map(reason),
                入场价: item.risk?.entry_price || 0,
                数量: item.risk?.quantity || 0,
                风险金额: item.risk?.quote_risk_usdt || 0,
                风险比例: item.risk?.risk_percent || 0,
            },
            执行结果: {
                类型: kind(item.execution?.kind),
                状态: status(item.execution?.status),
                意图: item.execution?.intent ? {
                    状态: status(item.execution.intent.status),
                    方向: simpleSide(item.execution.intent.side),
                    下单方式: orderType(item.execution.intent.order_type),
                    品种: item.execution.intent.symbol || "--",
                    入场价: item.execution.intent.entry_price || 0,
                    数量: item.execution.intent.quantity || 0,
                    止损: item.execution.intent.stop_loss || 0,
                    止盈: item.execution.intent.take_profits || [],
                    原因: (item.execution.intent.reasons || []).map(reason),
                } : null,
                更新: item.execution?.update ? {
                    状态: status(item.execution.update.status),
                    动作: action(item.execution.update.action),
                    原因: (item.execution.update.reasons || []).map(reason),
                    比例: item.execution.update.close_fraction || 0,
                } : null,
                订单: item.execution?.order ? {
                    状态: status(item.execution.order.status),
                    交易所单号: item.execution.order.order_id || "",
                    说明: reasonText(item.execution.order.error || ""),
                } : null,
            },
        };
    }

    const labels = {
        action, positionSide, intentSide, simpleSide, orderSide, status,
        mode, credential, category, kind, orderType, field, reason, reasonText, replayDetail,
    };

    window.KMTLabels = labels;
    window.KMTAccountLabels = labels;
})();
