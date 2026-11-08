/* Core visible-browser settings. Web content never enters the PETEY settings DOM. */
(() => {
    const toggle = document.getElementById('web-browser-enabled');
    const badge = document.getElementById('web-browser-badge');
    const feedback = document.getElementById('web-browser-status');
    const open = document.getElementById('web-browser-open');
    const close = document.getElementById('web-browser-close');
    const install = document.getElementById('web-browser-install');
    const searchEngine = document.getElementById('web-browser-search-engine');
    if (!toggle) return;
    let busy = false;
    let polling = null;
    let installing = false;
    function render(status) {
        toggle.checked = Boolean(status.enabled);
        toggle.disabled = busy;
        searchEngine.disabled = busy;
        searchEngine.value = status.search_engine || 'auto';
        open.disabled = busy || !status.enabled || !status.installed || status.installing;
        close.disabled = busy || !status.open;
        install.disabled = busy || !status.installed || status.installing;
        badge.textContent = status.enabled ? (status.open ? 'Window open' : 'On') : 'Off';
        install.textContent = status.installing ? 'Installing Chromium…' : 'Install Chromium';
        installing = Boolean(status.installing);
        feedback.textContent = status.error || (!status.installed
            ? 'Update PETEY dependencies: python -m pip install -r requirements.txt'
            : status.installing ? 'Downloading Chromium. You can keep using PETEY.' : '');
        if ((status.installing || status.enabled) && !polling) polling = setInterval(() => {
            if (!busy && !document.hidden && (installing || toggle.offsetParent !== null)) refresh();
        }, 2000);
        if (!status.installing && !status.enabled && polling) { clearInterval(polling); polling = null; }
    }
    async function refresh() {
        try { const payload = await apiJson('/api/desktop/tools/browser'); render(payload.browser); }
        catch (error) { feedback.textContent = error.message; }
    }
    async function action(path, method, body) {
        busy = true;
        toggle.disabled = open.disabled = close.disabled = install.disabled = searchEngine.disabled = true;
        feedback.textContent = 'Working…';
        try {
            const payload = await apiJson('/api/desktop/tools/browser' + path, {
                method, headers: {'Content-Type': 'application/json'},
                ...(body === undefined ? {} : {body: JSON.stringify(body)}),
            });
            busy = false; render(payload.browser);
        } catch (error) {
            busy = false; await refresh(); feedback.textContent = error.message;
        }
    }
    toggle.addEventListener('change', () => action('', 'PUT', {enabled: toggle.checked}));
    searchEngine.addEventListener('change', () => action('', 'PUT', {search_engine: searchEngine.value}));
    open.addEventListener('click', () => action('/open', 'POST'));
    close.addEventListener('click', () => action('/close', 'POST'));
    install.addEventListener('click', () => action('/install', 'POST'));
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
    document.addEventListener('click', event => {
        if (event.target.closest('[data-settings-view="tools"], [data-view="settings"]')) refresh();
    });
    refresh();
})();
