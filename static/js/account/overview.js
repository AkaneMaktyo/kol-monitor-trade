(function () {
    "use strict";

    const $ = (selector) => document.querySelector(selector);
    const refs = {
        updated: $("#account-updated"),
        refresh: $("#account-refresh"),
        error: $("#account-error"),
        chart: $("#equity-chart"),
        range: $("#curve-range"),
        positionRows: $("#position-rows"),
        historyRows: $("#history-position-rows"),
        pendingRows: $("#pending-order-rows"),
        tradeRows: $("#trade-order-rows"),
        updateRows: $("#signal-update-rows"),
        metrics: {
            equity: $("#metric-equity"),
            available: $("#metric-available"),
            unrealized: $("#metric-unrealized"),
            realized: $("#metric-realized"),
            margin: $("#metric-margin"),
            risk: $("#metric-risk"),
            positions: $("#metric-positions"),
            orders: $("#metric-orders"),
        },
    };
    const labels = window.KMTAccountLabels;
    const navStatus = $("#nav-ws-status");
    if (navStatus) {
        navStatus.textContent = "只读视图";
        navStatus.style.color = "var(--muted)";
    }

    async function load() {
        refs.refresh.disabled = true;
        refs.updated.textContent = "刷新中...";
        try {
            const response = await fetch("/api/account/overview");
            if (!response.ok) throw new Error("账户接口请求失败");
            render(await response.json());
        } catch (error) {
            refs.error.textContent = error.message;
        } finally {
            refs.refresh.disabled = false;
        }
    }

    function render(data) {
        refs.error.textContent = (data.errors || []).join("；");
        refs.updated.textContent = `最后刷新 ${new Date().toLocaleTimeString()}`;
        renderMetrics(data.summary || {});
        renderChart(data.curve || []);
        renderRows(refs.positionRows, data.positions || [], positionRow, 7);
        renderRows(refs.historyRows, data.history_positions || [], historyRow, 10);
        renderRows(refs.pendingRows, data.pending_orders || [], pendingRow, 6);
        renderRows(refs.tradeRows, data.trade_orders || [], tradeRow, 6);
        renderRows(refs.updateRows, data.signal_updates || [], updateRow, 5);
    }

    function renderMetrics(summary) {
        setMetric("equity", money(summary.equity, summary.margin_coin));
        setMetric("available", money(summary.available, summary.margin_coin));
        setMetric("unrealized", signed(summary.unrealized_pl, summary.margin_coin), signClass(summary.unrealized_pl));
        setMetric("realized", signed(summary.realized_pl, summary.margin_coin), signClass(summary.realized_pl));
        setMetric("margin", money(summary.margin, summary.margin_coin));
        setMetric("risk", `${num(Number(summary.risk_rate || 0) * 100)}%`);
        setMetric("positions", summary.positions || 0);
        setMetric("orders", summary.pending_orders || 0);
    }

    function setMetric(key, text, klass) {
        const node = refs.metrics[key];
        node.textContent = text;
        node.parentElement.classList.toggle("positive", klass === "positive");
        node.parentElement.classList.toggle("negative", klass === "negative");
    }

    function renderChart(points) {
        if (!points.length) {
            refs.chart.innerHTML = '<div class="empty-row">暂无权益快照</div>';
            refs.range.textContent = "--";
            return;
        }
        const values = points.map((item) => Number(item.account_equity || 0));
        const min = Math.min(...values);
        const max = Math.max(...values);
        const span = max - min || 1;
        const coords = values.map((value, index) => {
            const x = points.length === 1 ? 500 : 36 + index * (928 / (points.length - 1));
            const y = 222 - ((value - min) / span) * 176;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        });
        refs.range.textContent = `${money(min)} - ${money(max)}`;
        refs.chart.innerHTML = chartSvg(coords.join(" "), `36,232 ${coords.join(" ")} 964,232`, min, max);
    }

    function renderRows(target, rows, mapper, span) {
        target.innerHTML = rows.length ? rows.map(mapper).join("") : `<tr><td class="empty-row" colspan="${span}">暂无数据</td></tr>`;
    }

    function positionRow(row) {
        const side = row.holdSide || row.posSide || row.side;
        const total = row.total || 0;
        return `<tr><td>${esc(row.symbol)}</td><td>${esc(labels.positionSide(side))}</td><td>${num(total)}</td><td>${num(row.openPriceAvg)}</td><td>${num(row.markPrice)}</td><td class="${signClass(row.unrealizedPL)}">${signed(row.unrealizedPL)}</td><td><button class="close-position-link" type="button" data-symbol="${esc(row.symbol)}" data-hold-side="${esc(side)}" data-total="${esc(total)}" data-available="${esc(row.available || total)}" data-delegated="${esc(row.openDelegateSize || row.locked || 0)}" data-leverage="${esc(row.leverage)}" data-margin-mode="${esc(row.marginMode)}" data-margin-coin="${esc(row.marginCoin || "USDT")}" data-mark-price="${esc(row.markPrice)}" data-open-price="${esc(row.openPriceAvg)}">平仓</button></td></tr>`;
    }

    function pendingRow(row) {
        return `<tr><td>${esc(row.symbol)}</td><td>${esc(labels.orderSide(row.side, row.tradeSide))}</td><td>${num(row.price)}</td><td>${num(row.size)}</td><td><span class="status-pill">${esc(labels.status(row.status))}</span></td><td>${esc(row.orderId)}</td></tr>`;
    }

    function historyRow(row) {
        const side = row.holdSide || row.posSide || row.side;
        return `<tr><td>${esc(row.symbol)}</td><td>${esc(labels.positionSide(side))}</td><td>${num(row.openAvgPrice)}</td><td>${num(row.closeAvgPrice)}</td><td>${num(row.openTotalPos)}</td><td>${num(row.closeTotalPos)}</td><td class="${signClass(row.pnl)}">${signed(row.pnl)}</td><td class="${signClass(row.netProfit)}">${signed(row.netProfit)}</td><td>${timeLabel(row.utime || row.uTime || row.ctime || row.cTime)}</td><td>${historyChainCell(row, side)}</td></tr>`;
    }

    function historyChainCell(row, side) {
        const closedAt = row.utime || row.uTime || row.ctime || row.cTime || "";
        return `<button class="history-link" type="button" data-symbol="${esc(row.symbol)}" data-side="${esc(side)}" data-open-price="${esc(row.openAvgPrice)}" data-close-price="${esc(row.closeAvgPrice)}" data-open-size="${esc(row.openTotalPos)}" data-net-profit="${esc(row.netProfit)}" data-closed-at="${esc(closedAt)}">查看链路</button>`;
    }

    function tradeRow(row) {
        const status = row.order_status || row.intent_status || "";
        return `<tr><td>${esc(row.created_at)}</td><td>${esc(row.symbol)}</td><td>${esc(labels.intentSide(row.side))}</td><td>${num(row.price)}</td><td>${num(row.quantity)}</td><td><span class="status-pill">${esc(labels.status(status))}</span></td></tr>`;
    }

    function updateRow(row) {
        return `<tr><td>${esc(row.updated_at)}</td><td>${esc(labels.action(row.action))}</td><td>${percent(row.close_fraction)}</td><td><span class="status-pill">${esc(labels.status(row.status))}</span></td><td>${signalCell(row)}</td></tr>`;
    }

    function signalCell(row) {
        if (!row.related_signal_id) return '<span class="muted">--</span>';
        if (!row.related_source_log_id) return `<span class="muted">${esc(row.related_signal_id)}</span>`;
        return `<button class="message-link" type="button" data-log-id="${esc(row.related_source_log_id)}" title="${esc(row.related_signal_id)}">打开原消息</button>`;
    }

    function chartSvg(line, fill, min, max) {
        return `<svg viewBox="0 0 1000 260" preserveAspectRatio="none"><line class="chart-grid" x1="36" x2="964" y1="52" y2="52"></line><line class="chart-grid" x1="36" x2="964" y1="140" y2="140"></line><line class="chart-grid" x1="36" x2="964" y1="228" y2="228"></line><polygon class="chart-fill" points="${fill}"></polygon><polyline class="chart-line" points="${line}"></polyline><text class="chart-label" x="44" y="46">${money(max)}</text><text class="chart-label" x="44" y="244">${money(min)}</text></svg>`;
    }

    const money = (value, coin) => `${num(value)}${coin ? ` ${coin}` : ""}`;
    const signed = (value, coin) => `${Number(value || 0) > 0 ? "+" : ""}${money(value, coin)}`;
    const percent = (value) => Number(value || 0) ? `${Math.round(Number(value) * 100)}%` : "--";
    const signClass = (value) => Number(value || 0) > 0 ? "positive" : Number(value || 0) < 0 ? "negative" : "";
    const num = (value) => Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 4 });
    const timeLabel = (value) => Number(value || 0) ? new Date(Number(value)).toLocaleString("zh-CN") : "--";
    const esc = (value) => {
        const div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;
    };

    refs.refresh.addEventListener("click", load);
    window.KMTAccountOverview = { load };
    load();
})();
