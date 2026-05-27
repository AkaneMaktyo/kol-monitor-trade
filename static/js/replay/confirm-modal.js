(function () {
    "use strict";

    const $ = (selector) => document.querySelector(selector);
    const refs = {
        modal: $("#replay-confirm-modal"),
        form: $("#replay-confirm-form"),
        cancel: $("#replay-confirm-cancel"),
        summary: $("#replay-confirm-summary"),
        preview: $("#replay-confirm-preview"),
        input: $("#replay-confirm-input"),
        status: $("#replay-confirm-status"),
        submit: $("#replay-confirm-submit"),
    };
    if (!refs.modal || !refs.form) return;

    let current = null;

    refs.cancel.addEventListener("click", close);
    refs.modal.addEventListener("click", (event) => {
        if (event.target === refs.modal) close();
    });
    refs.form.addEventListener("submit", submit);

    function open(payload) {
        current = payload;
        refs.summary.textContent = payload.summary || "";
        refs.preview.textContent = payload.preview || "";
        refs.input.value = "";
        refs.status.textContent = "";
        refs.status.classList.remove("error");
        refs.submit.disabled = false;
        refs.submit.textContent = "确认真实执行";
        refs.modal.hidden = false;
        refs.input.focus();
    }

    function close() {
        refs.modal.hidden = true;
        current = null;
    }

    async function submit(event) {
        event.preventDefault();
        if (!current) return;
        refs.submit.disabled = true;
        refs.submit.textContent = "提交中...";
        try {
            await current.onConfirm(refs.input.value);
            close();
        } catch (error) {
            refs.status.textContent = error.message;
            refs.status.classList.add("error");
            refs.submit.disabled = false;
            refs.submit.textContent = "确认真实执行";
        }
    }

    window.KMTReplayConfirm = { open, close };
})();
