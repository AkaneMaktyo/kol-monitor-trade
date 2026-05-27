(function () {
    "use strict";

    const state = {
        filters: {
            author: "",
            source_channel: "",
            candidate_status: "",
            execution_status: "",
            limit: 120,
        },
        data: { filters: {}, readiness: {}, summary: {}, items: [] },
        selected: new Set(),
        detailId: "",
        busy: false,
        lastActionText: "",
    };

    function selectedIds() {
        return [...state.selected];
    }

    function detailItem() {
        return state.data.items.find((item) => item.log_id === state.detailId) || null;
    }

    window.KMTReplayState = { state, selectedIds, detailItem };
})();
