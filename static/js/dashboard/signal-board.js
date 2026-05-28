(function () {
    "use strict";

    const $ = (selector) => document.querySelector(selector);
    const refs = {
        panel: $("#trading-panel"),
        mode: $("#trading-mode"),
        summary: $("#trading-summary"),
        ready: $("#signal-ready-list"),
        review: $("#signal-review-list"),
        updates: $("#signal-update-list"),
        orders: $("#signal-order-list"),
        counts: {
            ready: $("#count-ready"),
            review: $("#count-review"),
            updates: $("#count-updates"),
            orders: $("#count-orders"),
        },
    };
    const state = { readiness: null, signals: { ready: [], review: [], updates: [], orders: [] } };
    const labels = window.KMTLabels;

    async function load() {
        if (!refs.panel) return;
        const response = await fetch("/api/signals/board");
        if (!response.ok) throw new Error("交易决策看板加载失败");
        const data = await response.json();
        state.readiness = data.readiness || null;
        state.signals = data.signals || state.signals;
        render();
    }

    function apply(event) {
        if (!refs.panel || !event || !event.candidate) return;
        if (event.candidate.category === "new_signal") upsertSignal(event);
        if (event.candidate.category === "position_update" && event.update) upsertUpdate(event);
        if (event.order) {
            upsert("orders", orderRow(event), "source_log_id");
            if (state.readiness) state.readiness.last_order = orderRow(event);
        }
        render();
    }

    function upsertSignal(event) {
        const bucket = event.intent && event.intent.status === "ready" ? "ready" : "review";
        remove("ready", event.candidate.source_log_id);
        remove("review", event.candidate.source_log_id);
        upsert(bucket, signalRow(event), "source_log_id");
    }

    function upsertUpdate(event) {
        upsert("updates", {
            source_log_id: event.candidate.source_log_id,
            symbol: event.candidate.symbol || "--",
            side: event.candidate.side || "",
            action: event.update.action || "",
            summary: event.update.action_text || event.candidate.evidence_text || "",
            close_fraction: event.update.close_fraction || 0,
            status: event.update.status || "",
            reasons: event.update.reasons || [],
            updated_at: event.message_time || "",
        }, "source_log_id");
    }

    function signalRow(event) {
        const intent = event.intent || {};
        return {
            source_log_id: event.candidate.source_log_id,
            symbol: event.candidate.bitget_symbol || event.candidate.symbol || "--",
            side: event.candidate.side || "",
            summary: event.candidate.evidence_text || "",
            status: intent.status || event.candidate.status || "",
            order_status: event.order && event.order.status || "",
            order_type: intent.order_type || event.candidate.entry_order_type || "",
            entry_price: intent.entry_price || 0,
            quantity: intent.quantity || 0,
            missing_fields: event.candidate.missing_fields || [],
            reasons: intent.reasons || [],
            risk_percent: intent.risk_percent || 0,
            quote_risk_usdt: intent.quote_risk_usdt || 0,
            updated_at: event.message_time || "",
        };
    }

    function orderRow(event) {
        const intent = event.intent || {};
        return {
            source_log_id: event.candidate && event.candidate.source_log_id || "",
            symbol: intent.symbol || event.candidate && (event.candidate.bitget_symbol || event.candidate.symbol) || "--",
            side: intent.side || event.candidate && event.candidate.side || "",
            order_type: intent.order_type || "",
            entry_price: intent.entry_price || 0,
            quantity: intent.quantity || 0,
            intent_status: intent.status || "",
            status: event.order.status || "",
            exchange_order_id: event.order.order_id || "",
            error_message: event.order.error || "",
            updated_at: event.message_time || "",
        };
    }

    function render() {
        if (!state.readiness) return;
        refs.mode.textContent = state.readiness.live_mode ? "真实提交已就绪" : state.readiness.execution_mode === "dry_run" ? "当前为演练模式" : "交易未就绪";
        refs.mode.className = `trading-mode-pill ${state.readiness.live_mode ? "pill-good" : state.readiness.trading_enabled ? "pill-warn" : "pill-bad"}`;
        refs.summary.innerHTML = [
            summaryBox("交易开关", state.readiness.trading_enabled ? "已开启" : "已关闭", state.readiness.product_type),
            summaryBox("执行模式", labels.mode(state.readiness.execution_mode), `${state.readiness.max_signal_age_seconds} 秒时效窗`),
            summaryBox("凭证状态", labels.credential(state.readiness.credential_status), state.readiness.credential_message || ""),
            summaryBox("风险预算", `${num(state.readiness.risk_budget.quote_risk_usdt)} USDT`, `${num(state.readiness.risk_budget.risk_percent)}% / 权益 ${num(state.readiness.risk_budget.account_equity_usdt)}`),
            summaryBox("最近下单", labels.status(state.readiness.last_order && state.readiness.last_order.status), lastOrderText(state.readiness.last_order)),
        ].join("");
        lane("ready", refs.ready, state.signals.ready, renderSignal);
        lane("review", refs.review, state.signals.review, renderSignal);
        lane("updates", refs.updates, state.signals.updates, renderUpdate);
        lane("orders", refs.orders, state.signals.orders, renderOrder);
    }

    function lane(name, target, rows, renderer) {
        refs.counts[name].textContent = rows.length;
        target.innerHTML = rows.length ? rows.map(renderer).join("") : '<div class="signal-empty">暂无数据</div>';
    }

    function renderSignal(row) {
        return item(`${esc(row.symbol)} ${labels.simpleSide(row.side)}`, row.status, [
            labels.orderType(row.order_type), row.entry_price ? `入场 ${num(row.entry_price)}` : "",
            row.quantity ? `数量 ${num(row.quantity)}` : "", row.order_status ? `订单 ${labels.status(row.order_status)}` : "",
            row.updated_at || "",
        ], row.summary, [...(row.missing_fields || []), ...(row.reasons || []), row.quote_risk_usdt ? `风险 ${num(row.quote_risk_usdt)}U` : ""]);
    }

    function renderUpdate(row) {
        return item(`${labels.action(row.action)} ${row.symbol ? `· ${esc(row.symbol)}` : ""}`, row.status, [
            row.close_fraction ? `比例 ${Math.round(row.close_fraction * 100)}%` : "",
            labels.simpleSide(row.side), row.updated_at || "",
        ], row.summary, row.reasons || []);
    }

    function renderOrder(row) {
        return item(`${esc(row.symbol)} ${labels.simpleSide(row.side)}`, row.status || row.intent_status, [
            labels.orderType(row.order_type), row.entry_price ? `价格 ${num(row.entry_price)}` : "",
            row.quantity ? `数量 ${num(row.quantity)}` : "", row.updated_at || "",
        ], row.error_message ? labels.reasonText(row.error_message) : exchangeText(row), [row.exchange_order_id ? `订单号 ${row.exchange_order_id}` : ""]);
    }

    function item(title, status, meta, text, tags) {
        return `<article class="signal-item"><div class="signal-top"><div class="signal-title">${title}</div>${pill(status)}</div>
            <div class="signal-meta">${meta.filter(Boolean).map((part) => `<span>${esc(part)}</span>`).join("")}</div>
            <div class="signal-text">${esc(text || "--")}</div>
            <div class="signal-tags">${tags.filter(Boolean).slice(0, 4).map((tag) => `<span class="signal-tag">${esc(tagLabel(tag))}</span>`).join("")}</div></article>`;
    }

    function summaryBox(label, value, note) {
        return `<article class="summary-box"><span>${esc(label)}</span><strong>${esc(value || "--")}</strong><p>${esc(note || "--")}</p></article>`;
    }

    function pill(status) {
        return `<span class="signal-pill ${pillClass(status)}">${esc(labels.status(status))}</span>`;
    }

    function upsert(bucket, row, key) {
        state.signals[bucket] = [row, ...state.signals[bucket].filter((item) => item[key] !== row[key])].slice(0, 6);
    }

    function remove(bucket, value) {
        state.signals[bucket] = state.signals[bucket].filter((item) => item.source_log_id !== value);
    }

    function lastOrderText(order) {
        return order ? `${order.symbol || "--"} / ${labels.status(order.status)}` : "暂无记录";
    }

    function exchangeText(row) {
        return row.exchange_order_id ? `交易所订单 ${row.exchange_order_id}` : "等待订单回报";
    }

    function pillClass(status) {
        return ["ready", "submitted", "dry_run"].includes(status) ? "pill-good"
            : ["blocked", "needs_review", "audit_only"].includes(status) ? "pill-warn"
                : status === "failed" ? "pill-bad" : "";
    }

    function tagLabel(tag) {
        return /^[a-z0-9_,]+$/i.test(String(tag || "")) ? labels.reasonText(tag) : tag;
    }

    function num(value) {
        return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 4 });
    }

    function esc(value) {
        return KMT.escapeHtml(value == null ? "" : String(value));
    }

    window.KMTSignalBoard = { load, apply };
})();
