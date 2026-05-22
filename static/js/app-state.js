(function () {
    "use strict";

    const state = {
        logs: [],
        expandedLogs: new Set(),
        filters: { platform: "", author: "" },
        maxLogs: 300,
    };

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = value || "";
        return div.innerHTML;
    }

    function formatUptime(seconds) {
        const total = Number(seconds || 0);
        const h = Math.floor(total / 3600);
        const m = Math.floor((total % 3600) / 60);
        const s = total % 60;
        if (h) return `${h}h ${m}m`;
        if (m) return `${m}m ${s}s`;
        return `${s}s`;
    }

    function statusLabel(value) {
        return {
            connected: "已连接",
            disconnected: "未连接",
            reconnecting: "重连中",
            error: "错误",
        }[value] || value || "未知";
    }

    window.KMT = { state, escapeHtml, formatUptime, statusLabel };
})();
