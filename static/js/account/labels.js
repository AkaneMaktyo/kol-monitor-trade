(function () {
    "use strict";

    const clean = (value) => String(value || "").toLowerCase();

    const action = (value) => ({
        close: "平仓",
        take_partial_profit: "部分止盈",
        move_stop_to_breakeven: "移动保本",
        take_profit_hit: "止盈命中",
        hold: "继续持有",
        add_layer: "加仓候选",
        risk_modifier: "风险调整",
    }[value] || value || "--");

    const positionSide = (value) => ({
        long: "多仓",
        short: "空仓",
        buy: "多仓",
        sell: "空仓",
    }[clean(value)] || value || "--");

    const intentSide = (value) => ({
        long: "做多",
        short: "做空",
        buy: "买入",
        sell: "卖出",
    }[clean(value)] || value || "--");

    const orderSide = (side, tradeSide) => {
        const trade = clean(tradeSide);
        const value = clean(side);
        if (trade === "close") return value === "buy" ? "平多" : "平空";
        if (trade === "open") return value === "buy" ? "买入开多" : "卖出开空";
        return intentSide(side);
    };

    const status = (value) => ({
        live: "挂单中",
        new: "新订单",
        ready: "就绪",
        submitted: "已提交",
        failed: "失败",
        blocked: "已拦截",
        dry_run: "模拟记录",
        needs_review: "待复核",
        audit_only: "仅记录",
    }[clean(value)] || value || "--");

    window.KMTAccountLabels = { action, positionSide, intentSide, orderSide, status };
})();
