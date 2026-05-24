(function () {
    "use strict";

    const modal = document.querySelector("#message-modal");
    const body = document.querySelector("#message-modal-body");
    const title = document.querySelector("#message-modal-title");
    const close = document.querySelector("#message-modal-close");
    if (!modal || !body || !title || !close) return;

    document.addEventListener("click", async (event) => {
        const trigger = event.target.closest(".message-link");
        if (!trigger) return;
        await openRecord(trigger.dataset.logId || "");
    });

    close.addEventListener("click", hide);
    modal.addEventListener("click", (event) => {
        if (event.target === modal) hide();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) hide();
    });

    async function openRecord(logId) {
        if (!logId) return;
        show("加载中", '<div class="message-loading">正在打开消息详情...</div>');
        try {
            const response = await fetch(`/api/account/message-detail?log_id=${encodeURIComponent(logId)}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "消息详情加载失败");
            render(data.html || "");
        } catch (error) {
            show("加载失败", `<div class="account-error">${escapeHtml(error.message)}</div>`);
        }
    }

    function render(html) {
        title.textContent = "消息详情";
        body.innerHTML = `<article class="message-html">${html}</article>`;
    }

    function show(nextTitle, html) {
        title.textContent = nextTitle;
        body.innerHTML = html;
        modal.hidden = false;
    }

    function hide() {
        modal.hidden = true;
    }

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;
    }
})();
