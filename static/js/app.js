(function () {
    "use strict";

    let ws = null;
    let reconnectTimer = null;
    let reconnectDelay = 1000;
    const maxReconnectDelay = 30000;

    async function boot() {
        KMTLogView.bindFilters();
        await Promise.all([loadInitialData(), loadSignalBoard(), loadTradingControls()]);
        connect();
    }

    async function loadInitialData() {
        const [status, logs] = await Promise.all([
            fetchJson("/api/status"),
            fetchJson("/api/logs?limit=100"),
        ]);
        KMTStatusView.renderStatus(status);
        KMTLogView.setLogs(logs.entries || []);
    }

    async function fetchJson(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`请求失败: ${url}`);
        return response.json();
    }

    async function loadSignalBoard() {
        if (!window.KMTSignalBoard) return;
        try {
            await KMTSignalBoard.load();
        } catch (error) {
            console.error(error);
        }
    }

    async function loadTradingControls() {
        if (!window.KMTTradingControls) return;
        try {
            await KMTTradingControls.load();
        } catch (error) {
            console.error(error);
        }
    }

    function connect() {
        const protocol = location.protocol === "https:" ? "wss" : "ws";
        ws = new WebSocket(`${protocol}://${location.host}/ws`);

        ws.onopen = () => {
            KMTStatusView.setSocketStatus(true);
            reconnectDelay = 1000;
        };

        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            if (message.type === "heartbeat") {
                KMTStatusView.renderStatus(message.data);
            }
            if (message.type === "log_entry") {
                KMTLogView.addLog(message.data);
            }
            if (message.type === "signal_result" && window.KMTSignalBoard) {
                KMTSignalBoard.apply(message.data);
            }
        };

        ws.onclose = () => {
            KMTStatusView.setSocketStatus(false);
            scheduleReconnect();
        };

        ws.onerror = () => {
            KMTStatusView.setSocketStatus(false);
        };
    }

    function scheduleReconnect() {
        if (reconnectTimer) return;
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            reconnectDelay = Math.min(reconnectDelay * 2, maxReconnectDelay);
            connect();
        }, reconnectDelay);
    }

    boot().catch((error) => {
        console.error(error);
        KMTStatusView.setSocketStatus(false);
    });
})();
