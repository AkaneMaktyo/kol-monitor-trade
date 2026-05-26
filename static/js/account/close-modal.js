(function () {
    "use strict";

    const $ = (selector) => document.querySelector(selector);
    const refs = {
        modal: $("#close-modal"),
        form: $("#close-form"),
        cancel: $("#close-modal-cancel"),
        symbol: $("#close-symbol"),
        side: $("#close-side"),
        leverage: $("#close-leverage"),
        marginMode: $("#close-margin-mode"),
        total: $("#close-total"),
        markPrice: $("#close-mark-price"),
        openPrice: $("#close-open-price"),
        priceField: $("#close-price-field"),
        price: $("#close-price"),
        quantityLabel: $("#close-quantity-label"),
        quantity: $("#close-quantity"),
        slider: $("#close-slider"),
        sliderLabel: $("#close-slider-label"),
        delegated: $("#close-delegated"),
        available: $("#close-available"),
        pnl: $("#close-pnl"),
        fee: $("#close-fee"),
        size: $("#close-size"),
        status: $("#close-status"),
        submit: $("#close-submit"),
    };
    if (!refs.modal || !refs.form) return;

    const CLOSE_FEE_RATE = 0.0006;
    let current = null;

    document.addEventListener("click", (event) => {
        const trigger = event.target.closest(".close-position-link");
        if (trigger) open(trigger.dataset);
    });
    refs.cancel.addEventListener("click", hide);
    refs.modal.addEventListener("click", (event) => {
        if (event.target === refs.modal) hide();
    });
    refs.form.addEventListener("input", handleInput);
    refs.form.addEventListener("change", updatePreview);
    refs.form.addEventListener("submit", submitClose);

    function open(data) {
        current = {
            symbol: data.symbol || "",
            holdSide: data.holdSide || "",
            total: Number(data.total || 0),
            totalText: data.total || "0",
            available: Number(data.available || data.total || 0),
            availableText: data.available || data.total || "0",
            delegated: Number(data.delegated || 0),
            leverage: data.leverage || "",
            marginMode: data.marginMode || "",
            marginCoin: data.marginCoin || "USDT",
            markPrice: Number(data.markPrice || 0),
            openPrice: Number(data.openPrice || 0),
            unit: baseUnit(data.symbol || ""),
        };
        refs.symbol.textContent = current.symbol;
        refs.side.textContent = window.KMTAccountLabels.positionSide(current.holdSide);
        refs.leverage.textContent = current.leverage ? `${current.leverage}x` : "--";
        refs.marginMode.textContent = marginModeText(current.marginMode);
        refs.total.textContent = amountUnit(current.total);
        refs.markPrice.textContent = priceText(current.markPrice);
        refs.openPrice.textContent = priceText(current.openPrice);
        refs.quantityLabel.textContent = `平仓数量 (${current.unit})`;
        refs.delegated.textContent = amountUnit(current.delegated);
        refs.available.textContent = amountUnit(current.available);
        refs.quantity.step = stepValue(current.availableText);
        refs.quantity.max = current.availableText;
        refs.slider.value = "50";
        refs.quantity.value = sizeFromPercent(50);
        refs.price.value = current.markPrice ? trimNumber(current.markPrice) : "";
        refs.status.textContent = "";
        refs.status.classList.remove("error");
        refs.modal.hidden = false;
        updatePreview();
    }

    function hide() { refs.modal.hidden = true; current = null; }

    function handleInput(event) {
        if (event.target === refs.slider) {
            refs.quantity.value = sizeFromPercent(Number(refs.slider.value || 0));
        } else if (event.target === refs.quantity) {
            refs.slider.value = percentFromSize(Number(refs.quantity.value || 0));
        }
        updatePreview();
    }

    function updatePreview() {
        const size = closeSize();
        const type = orderType();
        refs.priceField.hidden = type !== "limit";
        refs.sliderLabel.textContent = `${Math.round(Number(refs.slider.value || 0))}%`;
        refs.size.textContent = size > 0 ? `${amountText(size)} ${current?.unit || ""}` : "--";
        renderEstimate(size, executionPrice(type));
    }

    async function submitClose(event) {
        event.preventDefault();
        if (!current) return;
        const size = closeSize();
        const type = orderType();
        const price = Number(refs.price.value || 0);
        if (size <= 0) return setStatus("平仓数量需大于 0", true);
        if (size > current.available) return setStatus("平仓数量不能超过可平数量", true);
        if (type === "limit" && price <= 0) return setStatus("限价平仓价格需大于 0", true);
        const orderLabel = type === "limit" ? `限价 ${priceText(price)}` : "市价";
        const text = `${current.symbol} ${refs.side.textContent} ${amountText(size)} ${current.unit}`;
        if (!window.confirm(`确认提交模拟盘${orderLabel}平仓？\n${text}`)) return;
        setBusy(true);
        try {
            const response = await fetch("/api/account/close-position", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload(size, type, price)),
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

    function payload(size, type, price) {
        return {
            symbol: current.symbol,
            hold_side: current.holdSide,
            mode: "quantity",
            quantity: size,
            order_type: type,
            price: type === "limit" ? price : null,
        };
    }

    function closeSize() { return current ? Number(refs.quantity.value || 0) : 0; }

    function orderType() { return refs.form.querySelector("input[name='close-order-type']:checked")?.value || "market"; }

    function sizeFromPercent(percent) {
        if (!current) return "0";
        if (percent >= 100) return current.availableText;
        return trimNumber(floorScale(current.available * Math.max(0, percent) / 100, scale()));
    }

    function percentFromSize(size) {
        if (!current?.available) return 0;
        return Math.max(0, Math.min(100, Math.round(size / current.available * 100)));
    }

    function scale() { return decimals(current?.availableText || "0"); }

    function executionPrice(type) { return type === "limit" ? Number(refs.price.value || 0) : current.markPrice; }

    function renderEstimate(size, price) {
        const pnl = estimatePnl(size, price);
        const fee = Number.isFinite(price) ? Math.abs(size * price * CLOSE_FEE_RATE) : NaN;
        setMoney(refs.pnl, pnl, true);
        setMoney(refs.fee, fee, false);
    }

    function estimatePnl(size, price) {
        if (!current?.openPrice || !price || !size) return NaN;
        return (current.holdSide === "long" ? price - current.openPrice : current.openPrice - price) * size;
    }

    function setBusy(value) { refs.submit.disabled = value; refs.submit.textContent = value ? "提交中" : "确认平仓"; }

    function setStatus(message, error) { refs.status.textContent = message; refs.status.classList.toggle("error", Boolean(error)); }

    const decimals = (value) => (String(value).split(".")[1] || "").length;
    const stepValue = (value) => decimals(value) ? `0.${"0".repeat(decimals(value) - 1)}1` : "1";
    const floorScale = (value, size) => Math.floor(value * 10 ** size) / 10 ** size;
    const trimNumber = (value) => Number(value || 0).toFixed(8)
        .replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
    const baseUnit = (symbol) => symbol.replace(/USDT$/i, "") || "张";
    const amountUnit = (value) => `${amountText(value)} ${current.unit}`;
    const amountText = (value) => Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 8 });
    const priceText = (value) => value ? `${amountText(value)} ${current?.marginCoin || "USDT"}` : "--";
    const marginModeText = (value) => ({ crossed: "全仓", isolated: "逐仓" }[value] || value || "--");
    const setMoney = (target, value, signed) => {
        const ok = Number.isFinite(value);
        target.textContent = ok ? `${signed && value > 0 ? "+" : ""}${amountText(value)} ${current.marginCoin}` : "--";
        target.className = signed && ok && value > 0 ? "positive" : signed && ok && value < 0 ? "negative" : "";
    };
})();
