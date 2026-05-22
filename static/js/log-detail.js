(function () {
    "use strict";

    const cache = new Map();
    const loading = new Set();

    function cached(url) {
        return cache.get(url) || "";
    }

    function isLoading(url) {
        return loading.has(url);
    }

    async function load(url, onChange) {
        if (!url || cache.has(url) || loading.has(url)) return;
        loading.add(url);
        onChange();
        try {
            const response = await fetch(`/api/wxpusher/detail?url=${encodeURIComponent(url)}`);
            const data = await response.json();
            cache.set(url, response.ok ? data.content : `详情加载失败: ${data.detail || response.status}`);
        } catch (error) {
            cache.set(url, `详情加载失败: ${error.message}`);
        } finally {
            loading.delete(url);
            onChange();
        }
    }

    window.KMTLogDetail = { cached, isLoading, load };
})();
