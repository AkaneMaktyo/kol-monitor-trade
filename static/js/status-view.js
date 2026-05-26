(function () {
    "use strict";

    const $ = (selector) => document.querySelector(selector);
    const refs = {
        telegram: $("#status-telegram"),
        discord: $("#status-discord"),
        wxpusher: $("#status-wxpusher"),
        uptime: $("#stat-uptime"),
        total: $("#stat-total"),
        forwarded: $("#stat-forwarded"),
        clients: $("#stat-ws-clients"),
        nav: $("#nav-ws-status"),
    };

    function renderStatus(data) {
        refs.uptime.textContent = KMT.formatUptime(data.uptime_seconds);
        refs.total.textContent = data.total_messages || 0;
        refs.forwarded.textContent = data.forwarded_count || 0;
        refs.clients.textContent = data.ws_clients || 0;
        renderPlatform(refs.telegram, data.telegram);
        renderPlatform(refs.discord, data.discord);
        renderPlatform(refs.wxpusher, data.wxpusher);
    }

    function renderPlatform(card, info) {
        if (!card || !info) return;
        const indicator = card.querySelector(".status-indicator");
        const text = card.querySelector(".status-text");
        const detail = card.querySelector(".status-detail");
        const heartbeat = card.querySelector(".status-heartbeat");
        indicator.className = `status-indicator ${info.status}`;
        text.textContent = KMT.statusLabel(info.status);
        detail.textContent = detailText(info);
        heartbeat.textContent = info.last_heartbeat
            ? `最后心跳: ${info.last_heartbeat}`
            : "暂无心跳";
    }

    function detailText(info) {
        if (info.error_message) return info.error_message;
        if (info.monitored_channels && info.monitored_channels.length) {
            return `监听: ${info.monitored_channels.join(", ")}`;
        }
        if (info.platform === "telegram") return "未监听任何频道";
        return "监听所有可见频道";
    }

    function setSocketStatus(connected) {
        refs.nav.textContent = connected ? "已连接" : "未连接";
        refs.nav.style.color = connected ? "var(--green)" : "var(--red)";
    }

    window.KMTStatusView = { renderStatus, setSocketStatus };
})();
