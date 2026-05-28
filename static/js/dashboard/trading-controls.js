(function () {
    "use strict";

    const $ = (selector) => document.querySelector(selector);
    const refs = {
        form: $("#trading-controls-form"),
        enabled: $("#trading-enabled"),
        autoDemo: $("#trading-auto-demo"),
        feedback: $("#trading-controls-feedback"),
    };
    const state = {
        busy: false,
        last: { enabled: false, execution_mode: "dry_run" },
    };

    async function load() {
        if (!refs.form) return;
        setBusy(true, "正在读取当前开关...");
        try {
            const response = await request("/api/trading-controls");
            state.last = response.controls || state.last;
            apply(state.last);
            setBusy(false, hint(state.last), tone(state.last));
        } catch (error) {
            fail(error);
        }
    }

    function bind() {
        if (!refs.form || refs.form.dataset.bound) return;
        refs.form.dataset.bound = "true";
        refs.enabled.addEventListener("change", sync);
        refs.autoDemo.addEventListener("change", sync);
    }

    async function sync() {
        if (state.busy) return;
        const previous = { ...state.last };
        const next = payload();
        setBusy(true, "正在切换...");
        try {
            const response = await request("/api/trading-controls", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(next),
            });
            state.last = response.controls || next;
            apply(state.last);
            setBusy(false, result(state.last), tone(state.last));
            if (window.KMTSignalBoard) await window.KMTSignalBoard.load();
        } catch (error) {
            state.last = previous;
            apply(previous);
            fail(error);
        }
    }

    function apply(controls) {
        refs.enabled.checked = !!controls.enabled;
        refs.autoDemo.checked = controls.execution_mode === "auto_demo";
    }

    function payload() {
        return {
            enabled: !!refs.enabled.checked,
            execution_mode: refs.autoDemo.checked ? "auto_demo" : "dry_run",
        };
    }

    function hint(controls) {
        if (!controls.enabled) return "交易关闭时，新信号不会自动提交。";
        return controls.execution_mode === "auto_demo"
            ? "当前会尝试自动发到 Bitget 模拟盘。"
            : "当前是演练模式，只做模拟记录。";
    }

    function result(controls) {
        if (!controls.enabled) return "已关闭交易自动提交。";
        return controls.execution_mode === "auto_demo"
            ? "已打开自动模拟盘。"
            : "已切回演练模式。";
    }

    function tone(controls) {
        return controls.enabled && controls.execution_mode === "auto_demo" ? "success" : "warn";
    }

    async function request(url, options) {
        const response = await fetch(url, options);
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || "开关切换失败");
        }
        return response.json();
    }

    function setBusy(busy, message, kind) {
        state.busy = busy;
        refs.enabled.disabled = busy;
        refs.autoDemo.disabled = busy;
        setFeedback(message, kind);
    }

    function setFeedback(message, kind) {
        if (!refs.feedback) return;
        refs.feedback.textContent = message || "";
        refs.feedback.className = `control-feedback ${kind || ""}`.trim();
    }

    function fail(error) {
        console.error(error);
        setBusy(false, error.message || "开关切换失败", "error");
    }

    bind();
    window.KMTTradingControls = { load };
})();
