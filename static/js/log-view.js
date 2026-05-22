(function () {
    "use strict";
    const $ = (selector) => document.querySelector(selector);
    const refs = {
        box: $("#log-container"),
        count: $("#log-count"),
        platform: $("#platform-filter"),
        author: $("#author-filter"),
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
        const platformRows = KMT.state.logs.filter(matchesPlatform);
        updateAuthorOptions(platformRows);
        const rows = dedupeRows(platformRows.filter(matchesAuthor));
        refs.box.innerHTML = rows.length
            ? rows.map(renderEntry).join("")
            : '<div class="log-empty">没有匹配的日志</div>';
        refs.count.textContent = `${rows.length} 条`;
    }

    function renderEntry(entry) {
        const platform = entry.platform || "system";
        const parsed = parseContent(entry.content);
        const expanded = KMT.state.expandedLogs.has(entry.id);
        const canExpand = parsed.long || parsed.links.length || parsed.detailUrl;
        const meta = renderMeta(entry, parsed, platform);
        return `
            <div class="log-entry ${expanded ? "expanded" : ""}" data-level="${entry.level}" data-platform="${platform}">
                <div class="log-meta">${meta}</div>
                <div class="log-title">${KMT.escapeHtml(parsed.title)}</div>
                ${renderSummary(parsed, expanded)}
                ${expanded ? renderDetail(parsed.detailUrl) : ""}
                ${renderLinks(parsed.links, expanded)}
                ${canExpand ? renderToggle(entry.id, expanded) : ""}
            </div>
        `;
    }

    function renderMeta(entry, parsed, platform) {
        const author = displayAuthor(entry, parsed);
        return [
            `<span class="log-time">${KMT.escapeHtml(entry.timestamp)}</span>`,
            `<span class="log-badge ${platform}">${KMT.escapeHtml(platform)}</span>`,
            author ? `<span class="log-author">${KMT.escapeHtml(author)}</span>` : "",
            entry.source_channel ? `<span class="log-channel">${KMT.escapeHtml(entry.source_channel)}</span>` : "",
        ].filter(Boolean).join(" / ");
    }

    function parseContent(content) {
        const lines = String(content || "").split("\n").map((line) => line.trim()).filter(Boolean);
        const links = [];
        const textLines = [];
        let sourceName = "";
        lines.forEach((line) => {
            const link = parseKnownLink(line);
            if (link) links.push(link);
            else if (isSubscriptionTitle(line)) sourceName = sourceFromTitle(line);
            else textLines.push(line);
        });
        const title = textLines[0] || "[空消息]";
        const summary = textLines.slice(1).join("\n");
        const detail = links.find((item) => item.label === "详情");
        return {
            title,
            summary,
            authorName: authorFromTitle(title),
            sourceName,
            links,
            detailUrl: detail ? detail.url : "",
            long: title.length > 120 || summary.length > 160 || textLines.length > 2,
        };
    }

    function dedupeRows(rows) {
        const seen = new Set();
        return rows.filter((entry) => {
            const key = dedupeKey(entry);
            if (!key) return true;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }

    function dedupeKey(entry) {
        if (entry.platform !== "wxpusher") return "";
        const line = String(entry.content || "").split("\n")
            .find((item) => item.startsWith("原文: ") || item.startsWith("详情: "));
        return line ? line.replace(/^(原文|详情):\s*/, "") : "";
    }

    function authorFromTitle(title) {
        const match = String(title || "").match(/^\[([^\]]+)\]/);
        return match ? match[1].trim() : "";
    }

    function parseKnownLink(line) {
        const match = line.match(/^(原文|详情):\s*(https?:\/\/\S+)$/);
        return match ? { label: match[1], url: match[2] } : null;
    }

    const isSubscriptionTitle = (line) => line.startsWith("您订阅的【") && line.endsWith("】有新的消息");
    const sourceFromTitle = (line) => line.replace(/^您订阅的【/, "").replace(/】有新的消息$/, "");

    function displayAuthor(entry, parsed) {
        if (entry.platform === "wxpusher" && entry.author === "WxPusher") {
            return parsed.sourceName || entry.author;
        }
        return entry.author || "";
    }

    function renderSummary(parsed, expanded) {
        if (!parsed.summary) return "";
        return `<div class="log-summary ${expanded ? "" : "collapsed"}">${KMT.escapeHtml(parsed.summary)}</div>`;
    }

    function renderDetail(url) {
        if (!url || !window.KMTLogDetail) return "";
        if (KMTLogDetail.isLoading(url)) {
            return '<div class="log-detail loading">正在加载完整内容...</div>';
        }
        const content = KMTLogDetail.cached(url);
        return content ? `<div class="log-detail">${KMT.escapeHtml(content)}</div>` : "";
    }

    function renderLinks(links, expanded) {
        if (!expanded || !links.length) return "";
        const items = links.map((item) => `<a href="${KMT.escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${KMT.escapeHtml(item.label)}</a>`);
        return `<div class="log-links">${items.join("")}</div>`;
    }

    function renderToggle(id, expanded) {
        return `<button class="log-toggle" type="button" data-log-toggle="${KMT.escapeHtml(id)}">${expanded ? "收起" : "展开"}</button>`;
    }

    function updateAuthorOptions(rows) {
        const selected = refs.author.value;
        const authors = [...new Set(rows.map((entry) => parseContent(entry.content).authorName).filter(Boolean))];
        authors.sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
        refs.author.innerHTML = `<option value="">全部作者</option>${authors.map(authorOption).join("")}`;
        refs.author.value = authors.includes(selected) ? selected : "";
        KMT.state.filters.author = refs.author.value;
    }

    const authorOption = (author) => `<option value="${KMT.escapeHtml(author)}">${KMT.escapeHtml(author)}</option>`;
    const matchesPlatform = (entry) => !KMT.state.filters.platform || entry.platform === KMT.state.filters.platform;
    const matchesAuthor = (entry) => !KMT.state.filters.author
        || parseContent(entry.content).authorName === KMT.state.filters.author;

    function bindFilters() {
        refs.platform.addEventListener("change", () => setFilter("platform", refs.platform.value));
        refs.author.addEventListener("change", () => setFilter("author", refs.author.value));
        refs.clear.addEventListener("click", () => {
            KMT.state.logs = [];
            KMT.state.expandedLogs.clear();
            renderLogs();
        });
        refs.box.addEventListener("click", (event) => {
            const button = event.target.closest("[data-log-toggle]");
            if (button) toggleLog(button.dataset.logToggle);
        });
    }

    function setFilter(name, value) {
        KMT.state.filters[name] = value;
        renderLogs();
    }

    function toggleLog(id) {
        if (KMT.state.expandedLogs.has(id)) {
            KMT.state.expandedLogs.delete(id);
        } else {
            KMT.state.expandedLogs.add(id);
            loadDetail(id);
        }
        renderLogs();
    }

    function loadDetail(id) {
        const entry = KMT.state.logs.find((item) => String(item.id) === String(id));
        const url = entry ? parseContent(entry.content).detailUrl : "";
        if (url && window.KMTLogDetail) KMTLogDetail.load(url, renderLogs);
    }

    window.KMTLogView = { addLog, setLogs, bindFilters };
})();
