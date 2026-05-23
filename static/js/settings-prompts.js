(function () {
    "use strict";

    const refs = {
        form: document.querySelector("#prompt-form"),
        id: document.querySelector("#prompt-id"),
        name: document.querySelector("#prompt-name"),
        author: document.querySelector("#prompt-author"),
        channel: document.querySelector("#prompt-channel"),
        prompt: document.querySelector("#prompt-text"),
        enabled: document.querySelector("#prompt-enabled"),
        status: document.querySelector("#prompt-status"),
        list: document.querySelector("#prompt-list"),
        newButton: document.querySelector("#prompt-new"),
    };
    let profiles = [];

    const defaultPrompt = [
        "你是交易信号解析助手，只输出 JSON。",
        "请识别消息是否为新开仓、持仓更新、行情观点或噪音。",
        "字段包括 symbol、side、entry、take_profits、stop_loss、leverage、position_size、confidence、evidence_text、missing_fields。",
        "不要猜缺失字段；不确定时把 status 设为 needs_review。",
    ].join("\n");

    async function boot() {
        if (!refs.form) return;
        bindEvents();
        resetForm();
        await loadProfiles();
    }

    function bindEvents() {
        refs.form.addEventListener("submit", saveProfile);
        refs.newButton.addEventListener("click", resetForm);
        refs.list.addEventListener("click", handleListClick);
    }

    async function loadProfiles() {
        setStatus("加载中");
        try {
            const data = await request("/api/signal-prompts");
            profiles = data.profiles || [];
            renderProfiles();
            setStatus("");
        } catch (error) {
            setStatus(error.message);
        }
    }

    async function saveProfile(event) {
        event.preventDefault();
        const payload = {
            name: refs.name.value.trim(),
            source_author: refs.author.value.trim(),
            source_channel: refs.channel.value.trim(),
            prompt: refs.prompt.value.trim(),
            enabled: refs.enabled.checked,
        };
        const profileId = refs.id.value;
        const url = profileId ? `/api/signal-prompts/${profileId}` : "/api/signal-prompts";
        const method = profileId ? "PUT" : "POST";
        try {
            await request(url, { method, body: JSON.stringify(payload) });
            setStatus("已保存");
            resetForm();
            await loadProfiles();
        } catch (error) {
            setStatus(error.message);
        }
    }

    async function handleListClick(event) {
        const button = event.target.closest("button[data-id]");
        if (!button) return;
        const profile = profiles.find((item) => item.id === button.dataset.id);
        if (!profile) return;
        if (button.dataset.action === "edit") {
            editProfile(profile);
            return;
        }
        try {
            await request(`/api/signal-prompts/${profile.id}`, { method: "DELETE" });
            await loadProfiles();
            setStatus("已删除");
        } catch (error) {
            setStatus(error.message);
        }
    }

    function renderProfiles() {
        refs.list.innerHTML = "";
        if (!profiles.length) {
            refs.list.appendChild(textBlock("empty-hint", "还没有解析提示词"));
            return;
        }
        profiles.forEach((profile) => refs.list.appendChild(profileItem(profile)));
    }

    function profileItem(profile) {
        const item = document.createElement("article");
        item.className = "prompt-item";
        const header = document.createElement("header");
        const title = document.createElement("strong");
        title.textContent = profile.name;
        const actions = document.createElement("div");
        actions.className = "prompt-actions";
        actions.appendChild(actionButton("编辑", "edit", profile.id));
        actions.appendChild(actionButton("删除", "delete", profile.id));
        header.append(title, actions);

        const meta = textBlock(
            "settings-hint",
            `${profile.enabled ? "启用" : "停用"} · ${profile.source_author || "通用博主"} · ${profile.source_channel || "通用频道"}`,
        );
        const body = textBlock("prompt-preview", profile.prompt.slice(0, 180));
        item.append(header, meta, body);
        return item;
    }

    function actionButton(label, action, id) {
        const button = document.createElement("button");
        button.className = "small-button";
        button.type = "button";
        button.dataset.action = action;
        button.dataset.id = id;
        button.textContent = label;
        return button;
    }

    function editProfile(profile) {
        refs.id.value = profile.id;
        refs.name.value = profile.name;
        refs.author.value = profile.source_author || "";
        refs.channel.value = profile.source_channel || "";
        refs.prompt.value = profile.prompt;
        refs.enabled.checked = Boolean(profile.enabled);
        refs.name.focus();
        setStatus("正在编辑");
    }

    function resetForm() {
        refs.id.value = "";
        refs.name.value = "";
        refs.author.value = "";
        refs.channel.value = "";
        refs.prompt.value = defaultPrompt;
        refs.enabled.checked = true;
        setStatus("");
    }

    async function request(url, options = {}) {
        const response = await fetch(url, {
            headers: { "Content-Type": "application/json" },
            ...options,
        });
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
