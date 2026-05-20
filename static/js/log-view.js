(function () {
    "use strict";

    const $ = (selector) => document.querySelector(selector);
    const refs = {
        box: $("#log-container"),
        count: $("#log-count"),
        level: $("#level-filter"),
        platform: $("#platform-filter"),
        clear: $("#btn-clear-logs"),
    };

    function addLog(entry) {
        KMT.state.logs.push(entry);
        if (KMT.state.logs.length > KMT.state.maxLogs) {
            KMT.state.logs = KMT.state.logs.slice(-KMT.state.maxLogs);
        }
        renderLogs();
    }

    function setLogs(entries) {
        KMT.state.logs = [...entries].reverse();
        renderLogs();
    }

    function renderLogs() {
        const rows = KMT.state.logs.filter(matchesFilters);
        refs.box.innerHTML = rows.length
            ? rows.map(renderEntry).join("")
            : '<div class="log-empty">没有匹配的日志</div>';
        refs.count.textContent = `${rows.length} 条`;
        refs.box.scrollTop = refs.box.scrollHeight;
    }

    function renderEntry(entry) {
        const platform = entry.platform || "system";
        const meta = [
            entry.author ? `<span class="log-author">${KMT.escapeHtml(entry.author)}</span>` : "",
            entry.source_channel ? `<span class="log-channel">${KMT.escapeHtml(entry.source_channel)}</span>` : "",
        ].filter(Boolean).join(" / ");
        return `
            <div class="log-entry" data-level="${entry.level}" data-platform="${platform}">
                <span class="log-time">${KMT.escapeHtml(entry.timestamp)}</span>
                <span class="log-badge ${entry.level}">${KMT.escapeHtml(entry.level)}</span>
                <span class="log-badge ${platform}">${KMT.escapeHtml(platform)}</span>
                ${meta}
                <span class="log-content">${KMT.escapeHtml(entry.content)}</span>
            </div>
        `;
    }

    function matchesFilters(entry) {
        const filters = KMT.state.filters;
        if (filters.level && entry.level !== filters.level) return false;
        if (filters.platform && entry.platform !== filters.platform) return false;
        return true;
    }

    function bindFilters() {
        refs.level.addEventListener("change", () => {
            KMT.state.filters.level = refs.level.value;
            renderLogs();
        });
        refs.platform.addEventListener("change", () => {
            KMT.state.filters.platform = refs.platform.value;
            renderLogs();
        });
        refs.clear.addEventListener("click", () => {
            KMT.state.logs = [];
            renderLogs();
        });
    }

    window.KMTLogView = { addLog, setLogs, bindFilters };
})();
