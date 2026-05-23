(function () {
    "use strict";

    const refs = {
        button: document.querySelector("#telegram-load"),
        includeUsers: document.querySelector("#telegram-include-users"),
        status: document.querySelector("#telegram-status"),
        list: document.querySelector("#telegram-channel-list"),
    };
    const labels = {
        channel: "频道",
        supergroup: "超级群",
        group: "群组",
        user: "私聊",
    };

    function boot() {
        if (!refs.button) return;
        refs.button.addEventListener("click", loadChannels);
        refs.list.addEventListener("click", copyId);
    }

    async function loadChannels() {
        setStatus("正在读取 Telegram 会话");
        refs.button.disabled = true;
        refs.list.innerHTML = "";
        try {
            const query = new URLSearchParams({
                include_users: refs.includeUsers.checked ? "true" : "false",
            });
            const data = await request(`/api/telegram/channels?${query}`);
            renderChannels(data.channels || []);
            setStatus(`已列出 ${data.total || 0} 个会话`);
        } catch (error) {
            setStatus(error.message);
        } finally {
            refs.button.disabled = false;
        }
    }

    function renderChannels(channels) {
        refs.list.innerHTML = "";
        if (!channels.length) {
            refs.list.appendChild(textBlock("empty-hint", "没有可显示的频道或群组"));
            return;
        }
        channels.forEach((channel) => refs.list.appendChild(channelItem(channel)));
    }

    function channelItem(channel) {
        const item = document.createElement("article");
        item.className = "telegram-channel";

        const id = document.createElement("code");
        id.textContent = channel.id;
        id.title = "点击复制 ID";
        id.dataset.copy = channel.id;

        const title = document.createElement("div");
        title.className = "telegram-channel-title";
        const name = document.createElement("strong");
        name.textContent = channel.title || "未命名";
        const meta = document.createElement("span");
        meta.textContent = [channel.username, `${channel.unread || 0} 未读`]
            .filter(Boolean)
            .join(" · ");
        title.append(name, meta);

        const badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = labels[channel.type] || channel.type;
        item.append(id, title, badge);
        return item;
    }

    async function copyId(event) {
        const target = event.target.closest("[data-copy]");
        if (!target) return;
        try {
            await navigator.clipboard.writeText(target.dataset.copy);
            setStatus(`已复制 ${target.dataset.copy}`);
        } catch (error) {
            setStatus("复制失败，请手动选择 ID");
        }
    }

    async function request(url) {
        const response = await fetch(url);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || "请求失败");
        return data;
    }

    function textBlock(className, text) {
        const node = document.createElement("p");
        node.className = className;
        node.textContent = text;
        return node;
    }

    function setStatus(text) {
        refs.status.textContent = text;
    }

    boot();
})();
