(function () {
    "use strict";

    const $ = (selector) => document.querySelector(selector);
    const refs = {
        form: $("#replay-filter-form"),
        rows: $("#replay-rows"),
        author: $("#filter-author"),
        source: $("#filter-source-channel"),
        candidate: $("#filter-candidate-status"),
        execution: $("#filter-execution-status"),
        limit: $("#filter-limit"),
    };
    if (!refs.form || !refs.rows || !window.KMTReplayRender) return;

    document.addEventListener("click", handleClick);
    refs.form.addEventListener("submit", submitFilters);

    boot().catch(report);

    async function boot() {
        await load();
        connectSocket();
    }

    async function load(preferredLogId) {
        const state = window.KMTReplayState.state;
        const filters = currentFilters();
        const response = await fetch(`/api/signals/replay/gold-empire?${new URLSearchParams(filters)}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "回放列表加载失败");
        state.filters = filters;
        state.data = data;
        syncSelection();
        state.detailId = preferredLogId && exists(preferredLogId) ? preferredLogId : state.detailId;
        if (!exists(state.detailId)) state.detailId = data.items[0]?.log_id || "";
        refs.author.value = filters.author;
        refs.source.value = filters.source_channel;
        refs.candidate.value = filters.candidate_status;
        refs.execution.value = filters.execution_status;
        refs.limit.value = String(filters.limit);
        window.KMTReplayRender.render();
    }

    function currentFilters() {
        return {
            author: refs.author.value.trim(),
            source_channel: refs.source.value.trim(),
            candidate_status: refs.candidate.value,
            execution_status: refs.execution.value,
            limit: String(Math.max(1, Math.min(Number(refs.limit.value || 120), 120))),
        };
    }

    function syncSelection() {
        const state = window.KMTReplayState.state;
        const allowed = new Set(state.data.items
            .filter((item) => item.selectable_actions?.batch_selectable)
            .map((item) => item.log_id));
        state.selected = new Set([...state.selected].filter((id) => allowed.has(id)));
    }

    function exists(logId) {
        return window.KMTReplayState.state.data.items.some((item) => item.log_id === logId);
    }

    async function submitFilters(event) {
        event.preventDefault();
        await safeRun(() => load());
    }

    async function handleClick(event) {
        const checkbox = event.target.closest("[data-select-log]");
        if (checkbox) return toggleSelection(checkbox);
        const batch = event.target.closest("[data-batch-action]");
        if (batch) return runAction(batch.dataset.batchAction, window.KMTReplayState.selectedIds());
        const action = event.target.closest("[data-row-action]");
        if (action) return handleRowAction(action.dataset.rowAction, action.dataset.logId);
        const row = event.target.closest("tr[data-log-id]");
        if (!row) return;
        window.KMTReplayState.state.detailId = row.dataset.logId;
        window.KMTReplayRender.render();
    }

    function toggleSelection(input) {
        const selected = window.KMTReplayState.state.selected;
        if (input.checked) selected.add(input.dataset.selectLog);
        else selected.delete(input.dataset.selectLog);
        window.KMTReplayRender.render();
    }

    function handleRowAction(action, logId) {
        if (action === "view_detail") {
            window.KMTReplayState.state.detailId = logId;
            return window.KMTReplayRender.render();
        }
        return runAction(action, [logId]);
    }

    async function runAction(action, logIds) {
        if (!logIds.length) return setActionStatus("请先选择记录");
        if (action !== "real_execute") return safeRun(() => submitAction(action, logIds, ""));
        const items = window.KMTReplayState.state.data.items.filter((item) => logIds.includes(item.log_id));
        window.KMTReplayConfirm.open({
            summary: `本次将对 ${items.length} 条记录走真实执行链路。当前模式：${window.KMTReplayState.state.data.readiness.execution_mode || "--"}`,
            preview: items.map((item) => `${item.candidate.bitget_symbol || item.candidate.symbol || "--"} / ${item.candidate.side || "--"} / 风险 ${item.risk.quote_risk_usdt || 0}U`).join("\n"),
            onConfirm: (text) => submitAction(action, logIds, text),
        });
    }

    async function submitAction(action, logIds, confirmationText) {
        const response = await fetch("/api/signals/replay/gold-empire/actions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, log_ids: logIds, confirmation_text: confirmationText }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "回放动作执行失败");
        const state = window.KMTReplayState.state;
        state.selected.clear();
        state.lastActionText = actionText(data);
        await load(data.results[0]?.log_id || "");
        if (!data.ok) throw new Error(state.lastActionText);
    }

    function actionText(data) {
        const base = `动作 ${data.action} 已处理 ${data.total || 0} 条`;
        return data.stopped_at ? `${base}，在第 ${data.stopped_at} 条停止` : base;
    }

    function setActionStatus(message) {
        window.KMTReplayState.state.lastActionText = message;
        window.KMTReplayRender.render();
    }

    async function safeRun(task) {
        try {
            await task();
        } catch (error) {
            report(error);
            throw error;
        }
    }

    function report(error) {
        console.error(error);
        setActionStatus(error.message || String(error));
    }

    function connectSocket() {
        const target = document.querySelector("#nav-ws-status");
        if (!target) return;
        const protocol = location.protocol === "https:" ? "wss" : "ws";
        const socket = new WebSocket(`${protocol}://${location.host}/ws`);
        socket.onopen = () => setSocket(target, true);
        socket.onclose = () => setSocket(target, false);
        socket.onerror = () => setSocket(target, false);
    }

    function setSocket(target, connected) {
        target.textContent = connected ? "已连接" : "未连接";
        target.style.color = connected ? "var(--green)" : "var(--red)";
    }
})();
