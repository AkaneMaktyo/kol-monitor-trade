(function () {
    "use strict";
    const state = { channels: [], activeVideoId: "" };

    async function boot() {
        bindEvents();
        await loadChannels();
    }

    function bindEvents() {
        document.getElementById("channel-form").addEventListener("submit", onCreate);
        document.getElementById("sync-all").addEventListener("click", onSyncAll);
    }
    async function loadChannels() {
        const data = await fetchJson("/api/youtube/channels");
        state.channels = data.channels || [];
        render();
        syncActiveDetail();
    }

    async function onCreate(event) {
        event.preventDefault();
        setText("form-status", "正在添加并同步频道...");
        try {
            await fetchJson("/api/youtube/channels", {
                method: "POST",
                body: JSON.stringify({ source_url: valueOf("channel-url"), name: valueOf("channel-name") }),
            });
            event.target.reset();
            await loadChannels();
            setText("form-status", "添加成功");
        } catch (error) {
            setText("form-status", error.message);
        }
    }

    async function onSyncAll() {
        setText("video-status", "正在同步全部频道...");
        try {
            await fetchJson("/api/youtube/sync", { method: "POST" });
            await loadChannels();
            setText("video-status", "全部同步完成");
        } catch (error) {
            setText("video-status", error.message);
        }
    }

    async function onSyncChannel(channelId) {
        setText("video-status", "正在同步频道...");
        try {
            await fetchJson(`/api/youtube/channels/${channelId}/sync`, { method: "POST" });
            await loadChannels();
            setText("video-status", "频道同步完成");
        } catch (error) {
            setText("video-status", error.message);
        }
    }

    async function onDeleteChannel(channelId) {
        try {
            await fetchJson(`/api/youtube/channels/${channelId}`, { method: "DELETE" });
            state.activeVideoId = "";
            await loadChannels();
            resetDetail();
        } catch (error) {
            setText("video-status", error.message);
        }
    }

    async function onOpenVideo(videoId) {
        state.activeVideoId = videoId;
        render();
        await openVideo(videoId);
    }

    async function openVideo(videoId) {
        const data = await fetchJson(`/api/youtube/videos/${videoId}`);
        renderDetail(data.video);
    }

    function render() {
        const videos = state.channels.flatMap((item) => item.videos || []);
        const readyCount = videos.filter((item) => item.transcript_status === "ready").length;
        const errorCount = videos.filter((item) => item.transcript_status === "error").length;
        setText("channel-count", state.channels.length);
        setText("video-count", videos.length);
        setText("ready-count", readyCount);
        setText("error-count", errorCount);
        setText("channel-status", state.channels.length ? "已接入" : "等待同步");
        document.getElementById("channel-list").innerHTML = state.channels.map(channelCard).join("") || empty("还没有频道");
        document.getElementById("video-list").innerHTML = videos.map(videoCard).join("") || empty("同步后这里会显示最新视频");
        bindDynamicEvents();
    }

    function renderDetail(video) {
        const panel = document.getElementById("detail-panel");
        const player = document.getElementById("audio-player");
        const list = document.getElementById("segment-list");
        panel.classList.remove("empty");
        setText("detail-meta", `${video.published_at || "未知时间"} / ${formatDuration(video.audio_duration_ms)}`);
        panel.querySelector("h3").textContent = video.title;
        setBadge(document.getElementById("detail-badge"), video.transcript_status);
        player.src = `/api/youtube/audio/${video.video_id}`;
        list.innerHTML = (video.transcript_segments || []).map(segmentButton).join("");
        if (!video.transcript_segments || !video.transcript_segments.length) {
            list.innerHTML = empty(video.error_message || "当前还没有可播放段落");
        }
        list.querySelectorAll("[data-start]").forEach((button) => {
            button.addEventListener("click", () => {
                player.currentTime = Number(button.dataset.start) / 1000;
                player.play().catch(() => {});
            });
        });
        setText("video-status", `${statusLabel(video.transcript_status)} / ${video.transcript_source || "unknown"}`);
    }

    function resetDetail() {
        const panel = document.getElementById("detail-panel");
        panel.classList.add("empty");
        panel.querySelector("h3").textContent = "尚未选择视频";
        setText("detail-meta", "选择后可播放音频并按段跳转。");
        setBadge(document.getElementById("detail-badge"), "idle");
        document.getElementById("audio-player").removeAttribute("src");
        document.getElementById("segment-list").innerHTML = "";
    }

    function syncActiveDetail() {
        if (!state.activeVideoId) return;
        const exists = state.channels.some((channel) => (channel.videos || []).some((video) => video.video_id === state.activeVideoId));
        if (!exists) {
            state.activeVideoId = "";
            resetDetail();
            return;
        }
        openVideo(state.activeVideoId).catch((error) => setText("video-status", error.message));
    }

    function bindDynamicEvents() {
        document.querySelectorAll("[data-sync]").forEach((node) => node.addEventListener("click", () => onSyncChannel(node.dataset.sync)));
        document.querySelectorAll("[data-delete]").forEach((node) => node.addEventListener("click", () => onDeleteChannel(node.dataset.delete)));
        document.querySelectorAll("[data-video]").forEach((node) => node.addEventListener("click", () => onOpenVideo(node.dataset.video)));
    }

    function channelCard(channel) {
        return `<article class="channel-card">
            <strong>${escapeHtml(channel.title)}</strong>
            <div class="meta">${escapeHtml(channel.handle || channel.channel_id)}</div>
            <div class="meta">上次同步：${escapeHtml(channel.last_checked_at || "未同步")}</div>
            <div class="channel-actions">
                <button data-sync="${channel.id}" type="button">同步</button>
                <button data-delete="${channel.id}" type="button">删除</button>
            </div>
        </article>`;
    }

    function videoCard(video) {
        const active = state.activeVideoId === video.video_id ? " active" : "";
        return `<article class="video-item${active}" data-video="${video.video_id}">
            <div class="video-copy">
                <strong>${escapeHtml(video.title)}</strong>
                <div class="meta-row">
                    <span class="meta">${escapeHtml(video.published_at || "")}</span>
                    <span class="meta">${formatDuration(video.audio_duration_ms)}</span>
                </div>
            </div>
            <span class="status-pill${video.transcript_status === "error" ? " error" : ""}">${statusLabel(video.transcript_status)}</span>
        </article>`;
    }

    function segmentButton(segment) {
        return `<button class="segment-item" type="button" data-start="${segment.start_ms}">
            <span class="segment-time">${formatMs(segment.start_ms)}</span>
            <span>${escapeHtml(segment.text)}</span>
        </button>`;
    }

    async function fetchJson(url, options = {}) {
        const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || `请求失败: ${url}`);
        return data;
    }

    function formatMs(value) {
        const total = Math.floor(Number(value || 0) / 1000);
        const hours = Math.floor(total / 3600);
        const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
        const seconds = String(total % 60).padStart(2, "0");
        return hours > 0 ? `${hours}:${minutes}:${seconds}` : `${minutes}:${seconds}`;
    }

    function formatDuration(value) {
        if (!value) return "时长未知";
        return `时长 ${formatMs(value)}`;
    }

    function statusLabel(status) {
        return { ready: "已完成", error: "失败", pending: "处理中", idle: "未选择" }[status] || status || "未知";
    }

    function setBadge(node, status) {
        node.className = `status-pill${status === "error" ? " error" : ""}`; node.textContent = statusLabel(status);
    }

    function empty(text) {
        return `<div class="muted">${escapeHtml(text)}</div>`;
    }

    function valueOf(id) {
        return document.getElementById(id).value.trim();
    }

    function setText(id, text) {
        document.getElementById(id).textContent = String(text);
    }

    function escapeHtml(text) {
        return String(text || "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
    }

    boot().catch((error) => {
        console.error(error);
        setText("form-status", error.message);
        setText("video-status", error.message);
    });
})();
