(function () {
    "use strict";

    const modal = document.querySelector("#message-modal");
    const body = document.querySelector("#message-modal-body");
    const title = document.querySelector("#message-modal-title");
    const close = document.querySelector("#message-modal-close");
    if (!modal || !body || !title || !close) return;

    document.addEventListener("click", async (event) => {
        const message = event.target.closest(".message-link");
        if (message) return open(`/api/account/message-detail?log_id=${encodeURIComponent(message.dataset.logId || "")}`, "正在打开消息...", "message");
        const history = event.target.closest(".history-link");
        if (history) return open(historyUrl(history.dataset), "正在整理完整链路...", "history");
    });

    close.addEventListener("click", hide);
    modal.addEventListener("click", (event) => event.target === modal && hide());
    document.addEventListener("keydown", (event) => event.key === "Escape" && !modal.hidden && hide());

    async function open(url, loadingText, mode) {
        show("加载中", `<div class="message-loading">${escapeHtml(loadingText)}</div>`, mode);
        try {
            const response = await fetch(url);
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "详情加载失败");
            show(data.title || "详情", data.html || "", mode);
        } catch (error) {
            show("加载失败", `<div class="account-error">${escapeHtml(error.message)}</div>`, mode);
        }
    }

    function historyUrl(data) {
        const query = new URLSearchParams({
            symbol: data.symbol || "",
            hold_side: data.side || "",
            open_price: data.openPrice || "0",
            close_price: data.closePrice || "0",
            open_size: data.openSize || "0",
            net_profit: data.netProfit || "0",
            closed_at: data.closedAt || "0",
        });
        return `/api/account/history-detail?${query.toString()}`;
    }

    function show(nextTitle, html, mode) {
        title.textContent = nextTitle;
        body.innerHTML = html;
        modal.dataset.mode = mode || "message";
        modal.hidden = false;
    }

    function hide() {
        modal.hidden = true;
        delete modal.dataset.mode;
    }

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;
    }
})();
