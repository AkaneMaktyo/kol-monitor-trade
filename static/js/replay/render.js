(function () {
    "use strict";

    const $ = (selector) => document.querySelector(selector);
    const refs = {
        readiness: $("#replay-readiness"),
        summary: $("#replay-summary"),
        rows: $("#replay-rows"),
        count: $("#replay-table-count"),
        selected: $("#replay-selected-count"),
        detailTitle: $("#replay-detail-title"),
        detailRaw: $("#detail-raw-content"),
        detailExtra: $("#detail-extra-content"),
        detailNormalized: $("#detail-normalized-content"),
        detailResult: $("#detail-result-content"),
        actionStatus: $("#replay-action-status"),
    };

    function render() {
        const state = window.KMTReplayState.state;
        refs.readiness.innerHTML = readinessCards(state.data.readiness || {});
        refs.summary.innerHTML = summaryCards(state.data.summary || {});
        refs.rows.innerHTML = (state.data.items || []).map(rowHtml).join("") || emptyRow();
        refs.count.textContent = `${(state.data.items || []).length} 条`;
        refs.selected.textContent = `已选 ${state.selected.size} 条`;
        refs.actionStatus.textContent = state.lastActionText || "";
        renderDetail();
    }

    function renderDetail() {
        const item = window.KMTReplayState.detailItem();
        refs.detailTitle.textContent = item ? `${item.timestamp} / ${item.author || "未知作者"}` : "未选择记录";
        refs.detailRaw.textContent = item ? item.raw_content || "" : "";
        refs.detailExtra.textContent = detailText(item);
        refs.detailNormalized.textContent = item ? item.normalized_text || "" : "";
        refs.detailResult.textContent = item ? JSON.stringify({
            candidate: item.candidate,
            risk: item.risk,
            execution: item.execution,
        }, null, 2) : "";
    }

    function readinessCards(data) {
        return [
            card("执行模式", data.execution_mode || "--", data.live_mode ? "当前允许真实执行" : data.disabled_reason || "当前不允许真实执行"),
            card("凭证状态", data.credential_status || "--", data.credential_message || ""),
            card("风险预算", `${num(data.risk_budget?.quote_risk_usdt)} USDT`, `${num(data.risk_budget?.risk_percent)}% / 权益 ${num(data.risk_budget?.account_equity_usdt)}`),
            card("批量真实执行", data.live_mode ? "可用" : "锁定", data.live_mode ? "仍需二次确认" : data.disabled_reason || ""),
        ].join("");
    }

    function summaryCards(data) {
        return [
            card("当前结果", `${data.total || 0} 条`, `可批量执行 ${data.real_executable || 0} 条`),
            card("parsed", data.candidate_statuses?.parsed || 0, ""),
            card("needs_review", data.candidate_statuses?.needs_review || 0, ""),
            card("执行状态", summaryText(data.execution_statuses || {}), ""),
        ].join("");
    }

    function rowHtml(item) {
        const selected = window.KMTReplayState.state.selected.has(item.log_id);
        const actions = item.selectable_actions || {};
        return `<tr class="${item.log_id === window.KMTReplayState.state.detailId ? "row-active" : ""}" data-log-id="${esc(item.log_id)}">
            <td>${actions.batch_selectable ? `<input type="checkbox" data-select-log="${esc(item.log_id)}" ${selected ? "checked" : ""}>` : "--"}</td>
            <td>${esc(item.timestamp)}</td>
            <td><div>${esc(item.author || "--")}</div><div class="row-meta">${esc(item.source_channel || "--")}</div></td>
            <td>${esc(item.content_preview || "--")}</td>
            <td>${pill(item.candidate?.status)}${reasonTags(item.risk?.reasons || [])}</td>
            <td>${pill(item.execution?.status)}${detailState(item.detail_state)}</td>
            <td><div class="row-actions">
                ${button("view_detail", item.log_id, "查看详情")}
                ${button("preview", item.log_id, "仅回放")}
                ${button("persist", item.log_id, "持久化回放")}
                ${button("real_execute", item.log_id, "真实执行", !actions.real_execute, actions.real_execute_disabled_reason)}
            </div></td>
        </tr>`;
    }

    function detailText(item) {
        if (!item) return "";
        if (item.detail_state?.status === "failed") return `详情抓取失败: ${item.detail_state.message || ""}`;
        if (item.detail_state?.status === "not_needed") return "该记录无需补全详情";
        return item.detail_text || "详情为空";
    }

    function detailState(detail) {
        const value = detail?.status || "--";
        return `<div class="pill-row">${pill(value)}</div>`;
    }

    function button(action, logId, label, disabled, title) {
        return `<button type="button" data-row-action="${action}" data-log-id="${esc(logId)}" ${disabled ? "disabled" : ""} title="${esc(title || "")}">${label}</button>`;
    }

    function reasonTags(reasons) {
        if (!reasons.length) return "";
        return `<div class="pill-row">${reasons.slice(0, 2).map((item) => pill(item)).join("")}</div>`;
    }

    function card(label, value, note) {
        return `<article class="summary-card"><span>${esc(label)}</span><strong>${esc(String(value || "--"))}</strong><span>${esc(note || "--")}</span></article>`;
    }

    function pill(value) {
        return `<span class="status-pill">${esc(value || "--")}</span>`;
    }

    function summaryText(data) {
        return Object.entries(data).map(([key, value]) => `${key}:${value}`).join(" / ") || "--";
    }

    function num(value) {
        return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 4 });
    }

    function emptyRow() {
        return '<tr><td colspan="7">暂无匹配记录</td></tr>';
    }

    function esc(value) {
        return window.KMT.escapeHtml(value == null ? "" : String(value));
    }

    window.KMTReplayRender = { render };
})();
