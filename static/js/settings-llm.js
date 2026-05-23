(function () {
    "use strict";

    const refs = {
        form: document.querySelector("#llm-form"),
        provider: document.querySelector("#llm-provider"),
        baseUrl: document.querySelector("#llm-base-url"),
        model: document.querySelector("#llm-model"),
        apiKey: document.querySelector("#llm-api-key"),
        enabled: document.querySelector("#llm-enabled"),
        status: document.querySelector("#llm-status"),
        test: document.querySelector("#llm-test"),
    };

    async function boot() {
        if (!refs.form) return;
        refs.form.addEventListener("submit", saveConfig);
        refs.test.addEventListener("click", testConfig);
        await loadConfig();
    }

    async function loadConfig() {
        try {
            const data = await request("/api/llm-config");
            renderConfig(data.config || {});
        } catch (error) {
            setStatus(error.message);
        }
    }

    function renderConfig(config) {
        refs.provider.value = config.provider || "deepseek";
        refs.baseUrl.value = config.base_url || "https://api.deepseek.com";
        setModel(config.model || "deepseek-v4-flash");
        refs.enabled.checked = Boolean(config.enabled);
        refs.apiKey.value = "";
        refs.apiKey.placeholder = config.has_api_key ? "已保存，留空不修改" : "请输入 DeepSeek API Key";
        setStatus(config.has_api_key ? "已保存 API Key" : "未配置 API Key");
    }

    function setModel(model) {
        const values = [...refs.model.options].map((item) => item.value);
        if (!values.includes(model)) {
            refs.model.add(new Option(model, model));
        }
        refs.model.value = model;
    }

    async function saveConfig(event) {
        event.preventDefault();
        try {
            const data = await request("/api/llm-config", {
                method: "PUT",
                body: JSON.stringify(payload()),
            });
            renderConfig(data.config || {});
            setStatus("已保存");
        } catch (error) {
            setStatus(error.message);
        }
    }

    async function testConfig() {
        setStatus("测试中");
        try {
            const data = await request("/api/llm-config/test", {
                method: "POST",
                body: JSON.stringify(payload()),
            });
            const result = data.result || {};
            setStatus(`测试成功：${result.model || refs.model.value}`);
        } catch (error) {
            setStatus(error.message);
        }
    }

    function payload() {
        return {
            provider: refs.provider.value.trim(),
            base_url: refs.baseUrl.value.trim(),
            model: refs.model.value.trim(),
            api_key: refs.apiKey.value.trim(),
            enabled: refs.enabled.checked,
        };
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

    function setStatus(message) {
        refs.status.textContent = message || "";
    }

    boot();
})();
