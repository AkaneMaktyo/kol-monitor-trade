(function () {
    "use strict";

    const $ = (selector) => document.querySelector(selector);
    const refs = {
        modal: $("#close-modal"),
        form: $("#close-form"),
        cancel: $("#close-modal-cancel"),
        symbol: $("#close-symbol"),
        side: $("#close-side"),
        total: $("#close-total"),
        percent: $("#close-percent"),
        quantity: $("#close-quantity"),
        percentField: $("#close-percent-field"),
        quantityField: $("#close-quantity-field"),
        size: $("#close-size"),
        status: $("#close-status"),
        submit: $("#close-submit"),
    };
    if (!refs.modal || !refs.form) return;

    let current = null;

    document.addEventListener("click", (event) => {
        const trigger = event.target.closest(".close-position-link");
        if (trigger) open(trigger.dataset);
    });
    refs.cancel.addEventListener("click", hide);
    refs.modal.addEventListener("click", (event) => {
        if (event.target === refs.modal) hide();
    });
    refs.form.addEventListener("input", updatePreview);
    refs.form.addEventListener("change", updatePreview);
    refs.form.addEventListener("submit", submitClose);

    function open(data) {
        current = {
            symbol: data.symbol || "",
            holdSide: data.holdSide || "",
            total: Number(data.total || 0),
            totalText: data.total || "0",
        };
        refs.symbol.textContent = current.symbol;
        refs.side.textContent = window.KMTAccountLabels.positionSide(current.holdSide);
        refs.total.textContent = num(current.total);
        refs.quantity.value = current.totalText;
        refs.quantity.max = current.totalText;
        refs.percent.value = "50";
        refs.status.textContent = "";
        refs.modal.hidden = false;
        updatePreview();
    }

    function hide() {
        refs.modal.hidden = true;
        current = null;
    }

    function updatePreview() {
        const mode = modeValue();
        refs.percentField.hidden = mode !== "percent";
        refs.quantityField.hidden = mode !== "quantity";
        const size = closeSize(mode);
        refs.size.textContent = size > 0 ? num(size) : "--";
    }

    async function submitClose(event) {
        event.preventDefault();
        if (!current) return;
        const mode = modeValue();
        const size = closeSize(mode);
        if (size <= 0) return setStatus("平仓数量需大于 0", true);
        if (size > current.total) return setStatus("平仓数量不能超过当前仓位", true);
        if (mode === "percent" && Number(refs.percent.value || 0) > 100) {
            return setStatus("平仓比例不能超过 100%", true);
        }
        const text = `${current.symbol} ${refs.side.textContent} ${num(size)}`;
        if (!window.confirm(`确认提交模拟盘市价平仓？\n${text}`)) return;
        setBusy(true);
        try {
            const response = await fetch("/api/account/close-position", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload(mode)),
            });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.detail || data.order?.error || "平仓提交失败");
            setStatus(`已提交，订单号 ${data.order.order_id || data.order.client_oid}`, false);
            if (window.KMTAccountOverview) window.KMTAccountOverview.load();
        } catch (error) {
            setStatus(error.message, true);
        } finally {
            setBusy(false);
        }
    }

    function payload(mode) {
        return {
            symbol: current.symbol,
            hold_side: current.holdSide,
            mode,
            quantity: mode === "quantity" ? Number(refs.quantity.value || 0) : null,
            percent: mode === "percent" ? Number(refs.percent.value || 0) : null,
        };
    }

    function closeSize(mode) {
        if (!current) return 0;
        if (mode === "quantity") return Number(refs.quantity.value || 0);
        const percent = Math.max(0, Math.min(100, Number(refs.percent.value || 0)));
        if (percent === 100) return current.total;
        const factor = 10 ** decimals(current.totalText);
        return Math.floor(current.total * percent / 100 * factor) / factor;
    }

    function modeValue() {
        return refs.form.querySelector("input[name='close-mode']:checked")?.value || "percent";
    }

    function setBusy(value) {
        refs.submit.disabled = value;
        refs.submit.textContent = value ? "提交中" : "确认平仓";
    }

    function setStatus(message, error) {
        refs.status.textContent = message;
        refs.status.classList.toggle("error", Boolean(error));
    }

    const decimals = (value) => (String(value).split(".")[1] || "").length;
    const num = (value) => Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 8 });
})();
