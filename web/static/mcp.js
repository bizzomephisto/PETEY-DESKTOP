/* Direct MCP settings. Server strings are always rendered as text. */
(() => {
    const container = document.getElementById('mcp-server-list');
    if (!container) return;
    const feedback = document.getElementById('mcp-status');
    const node = (tag, text, className) => {
        const element = document.createElement(tag);
        if (text !== undefined) element.textContent = text;
        if (className) element.className = className;
        return element;
    };
    const toggle = (text, checked, parent) => {
        const label = node('label', undefined, 'preference-row');
        label.append(node('span', text));
        const input = node('input'); input.type = 'checkbox'; input.setAttribute('role', 'switch'); input.checked = checked;
        label.append(input); parent.append(label); return input;
    };
    async function action(button, path, method, body, success, afterSuccess) {
        button.disabled = true; setFeedback(feedback, 'Working…');
        try {
            const payload = await apiJson('/api/desktop/mcp/servers' + path, {
                method, headers: {'Content-Type': 'application/json'}, ...(body === undefined ? {} : {body: JSON.stringify(body)})
            });
            if (afterSuccess) afterSuccess();
            render(payload); setFeedback(feedback, success, 'success');
        } catch (error) {
            setFeedback(feedback, error.message, 'error');
        } finally { button.disabled = false; }
    }
    function render(payload) {
        const expanded = new Set([...container.querySelectorAll('details[data-mcp-disclosure][open]')].map(item => item.dataset.mcpDisclosure));
        container.replaceChildren();
        if (!payload.servers.length) container.append(node('p', 'No MCP servers configured.', 'muted'));
        for (const server of payload.servers) {
            const card = node('section', undefined, 'mcp-server-card');
            const disclosure = node('details', undefined, 'mcp-server-details');
            disclosure.dataset.mcpDisclosure = JSON.stringify([server.id]);
            disclosure.open = expanded.has(disclosure.dataset.mcpDisclosure);
            const summary = node('summary');
            summary.append(node('h3', server.name));
            summary.append(node('span', `${server.connected ? 'Connected' : 'Disconnected'} · ${server.transport === 'stdio' ? 'Local command' : 'Remote HTTP'}`, 'hint mcp-server-status'));
            disclosure.append(summary);
            const content = node('div', undefined, 'mcp-server-body');
            disclosure.append(content); card.append(disclosure);
            const enabled = toggle(`Enable ${server.name}`, server.enabled, card);
            enabled.parentElement.classList.add('mcp-header-toggle');
            enabled.parentElement.title = 'Let Petey use selected tools. Save settings to apply.';
            // Keep controls outside summary so toggling access never folds the details.
            if (server.endpoint) content.append(node('p', server.endpoint, 'hint'));
            if (server.transport === 'http') {
                const auth = node('details');
                auth.open = !server.has_authentication;
                auth.append(node('summary', server.has_authentication ? 'Authentication — credential saved' : 'Authentication — no credential saved'));
                const kindLabel = node('label', 'Authentication method');
                const kind = node('select');
                for (const [value, label] of [['bearer', 'Bearer token / API key (Authorization)'], ['api_key', 'API key (X-API-Key)'], ['clear', 'Remove saved authentication']]) {
                    const option = node('option', label); option.value = value; kind.append(option);
                }
                kind.value = server.authentication_type || 'bearer'; kindLabel.append(kind); auth.append(kindLabel);
                const secretLabel = node('label', 'Token or API key');
                const secret = node('input'); secret.type = 'password'; secret.autocomplete = 'new-password';
                secret.placeholder = server.has_authentication ? 'Enter a replacement credential' : 'Paste token or API key';
                secretLabel.append(secret); auth.append(secretLabel);
                kind.onchange = () => { secret.disabled = kind.value === 'clear'; };
                const tinyfish = server.endpoint === 'https://agent.tinyfish.ai';
                auth.append(node('p', (tinyfish ? 'For Tinyfish, select Bearer token / API key and paste your Tinyfish key. ' : 'Use the authentication method from the server’s instructions. ') + 'Saved values stay hidden; changing authentication turns this server off and clears tool grants. Browser OAuth sign-in is not supported yet.', 'hint'));
                const saveAuth = node('button', 'Save authentication', 'secondary-button'); saveAuth.type = 'button';
                saveAuth.onclick = () => {
                    if (kind.value !== 'clear' && !secret.value.trim()) {
                        setFeedback(feedback, 'Enter a token or API key before saving authentication.', 'error'); return;
                    }
                    action(saveAuth, `/${server.id}`, 'PUT', {credential: {type: kind.value, value: secret.value.trim()}},
                        'Authentication saved. Test connection, select tools, and enable the server again.', () => { secret.value = ''; });
                };
                auth.append(saveAuth); content.append(auth);
            }
            if (server.error) content.append(node('p', server.error, 'wide-status'));
            const keywordLabel = node('label', 'Chat keywords (comma separated)');
            const keywords = node('input'); keywords.type = 'text'; keywords.value = server.keywords.join(', ');
            keywords.placeholder = server.name; keywords.maxLength = 1600; keywordLabel.append(keywords); content.append(keywordLabel);
            content.append(node('p', 'Mention a keyword to make these tools available. With no keywords, mention the server name.', 'hint'));
            const surfaces = {};
            for (const [key, label] of [['petey_desktop', 'Desktop'], ['mobile_petey', 'Mobile / companion'], ['discord', 'Discord']]) {
                surfaces[key] = toggle(label, Boolean(server.surfaces[key]), content);
            }
            const tools = node('details'); tools.open = true;
            tools.append(node('summary', `Tools (${server.tools.length} discovered)`));
            const choices = [];
            if (!server.tools.length) tools.append(node('p', 'Test connection to discover tools. Previously selected tools remain saved.', 'hint'));
            for (const tool of server.tools) {
                const row = node('div', undefined, 'mcp-tool-row');
                const details = node('details', undefined, 'mcp-tool-details');
                details.dataset.mcpDisclosure = JSON.stringify([server.id, tool.name]);
                details.open = expanded.has(details.dataset.mcpDisclosure);
                details.append(node('summary', tool.name));
                details.append(node('p', tool.description || 'No description provided by this server.', 'hint'));
                row.append(details);
                const selected = toggle(`Enable ${tool.name}`, server.allowed_tools.includes(tool.name), row);
                selected.parentElement.classList.add('mcp-header-toggle');
                choices.push([tool.name, selected]);
                tools.append(row);
            }
            content.append(tools);
            content.append(node('p', 'Save settings to apply enable switches and tool selections. Selected tools may change files or external services according to what that server supports.', 'hint'));
            const buttons = node('div', undefined, 'inline-actions');
            const test = node('button', 'Test connection', 'secondary-button'); test.type = 'button';
            test.onclick = () => action(test, `/${server.id}/test`, 'POST', undefined, 'Connection tested. Select tools and save settings.');
            const save = node('button', 'Save settings', 'primary-button'); save.type = 'button';
            save.onclick = () => {
                const settings = {enabled: enabled.checked, keywords: keywords.value.split(',').map(v => v.trim()).filter(Boolean),
                    surfaces: Object.fromEntries(Object.entries(surfaces).map(([key, input]) => [key, input.checked]))};
                if (server.tools.length) settings.allowed_tools = choices.filter(([, input]) => input.checked).map(([name]) => name);
                action(save, `/${server.id}`, 'PUT', settings, 'MCP settings saved.');
            };
            const remove = node('button', 'Remove server', 'text-button'); remove.type = 'button';
            remove.onclick = () => action(remove, `/${server.id}`, 'DELETE', undefined, 'Server removed.');
            buttons.append(test, save, remove); content.append(buttons); container.append(card);
        }
    }
    async function load() {
        try { render(await apiJson('/api/desktop/mcp/servers')); }
        catch (error) { setFeedback(feedback, error.message, 'error'); }
    }
    document.getElementById('mcp-import').onclick = async event => {
        const textarea = document.getElementById('mcp-config-json');
        let config;
        try { config = JSON.parse(textarea.value); }
        catch (_) { setFeedback(feedback, 'Enter valid JSON with an mcpServers object.', 'error'); return; }
        const button = event.currentTarget;
        button.disabled = true;
        try {
            render(await apiJson('/api/desktop/mcp/servers/import', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(config)}));
            textarea.value = ''; setFeedback(feedback, 'Imported with servers off. Test connection, select tools, then save.', 'success');
        } catch (error) { setFeedback(feedback, error.message, 'error'); }
        finally { button.disabled = false; }
    };
    window.peteyGeneralMCP = {load};
    load();
})();
