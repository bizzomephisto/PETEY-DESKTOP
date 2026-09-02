const messages = document.getElementById('messages');
const composer = document.getElementById('composer');
const messageInput = document.getElementById('message');
const attachmentInput = document.getElementById('attachment');
const attachmentChip = document.getElementById('attachment-chip');
const sendButton = document.getElementById('send');
const statusText = document.getElementById('status');
let personName = 'User';
let personaPresets = {};
let savedPersonas = [];
let personalityLoaded = false;
let aiProviderLoaded = false;
let aiProviderConfiguration = null;
let memoryProviderLoaded = false;
let memoryProviderConfiguration = null;
let mediaCatalogLoaded = false;
let mediaSelectedModels = {};
let mediaPollTimer = null;
const displayedMediaJobs = new Set();
let conversations = [];
let activeConversationId = '';
let temporaryHistory = [];
let preferences = {always_on_top: false, sidebar_collapsed: false, ui_scale: 1};
let workspaces = [];
let activeWorkspaceId = '';
let workspaceDirectory = '';
let editorSha256 = null;
let workspaceLoaded = false;

function showEmptyState(title = 'Petey is ready.', copy = 'Start a conversation or attach an image for him to inspect.') {
    messages.innerHTML = `<div class="empty-state" id="empty-state"><img src="/static/petey_avatar.png" alt=""><h2>${title}</h2><p>${copy}</p></div>`;
}

function removeEmptyState() {
    document.getElementById('empty-state')?.remove();
}

async function copyChatText(text, button) {
    try {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            throw new Error('Clipboard API unavailable');
        }
    } catch (_error) {
        const helper = document.createElement('textarea');
        helper.value = text;
        helper.setAttribute('readonly', '');
        helper.style.position = 'fixed';
        helper.style.opacity = '0';
        document.body.append(helper);
        helper.select();
        const copied = document.execCommand('copy');
        helper.remove();
        if (!copied) {
            window.alert('Could not access the clipboard. Select the message and press Ctrl+C.');
            return;
        }
    }
    const previous = button.textContent;
    button.textContent = 'Copied';
    button.classList.add('copied');
    window.setTimeout(() => {
        button.textContent = previous;
        button.classList.remove('copied');
    }, 1200);
}

function addMessage(role, text, options = {}) {
    removeEmptyState();
    const item = document.createElement('article');
    item.className = `message ${role}${options.typing ? ' typing' : ''}`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'assistant' ? 'P' : personName.slice(0, 1).toUpperCase();

    const content = document.createElement('div');
    const meta = document.createElement('div');
    meta.className = 'meta';
    const speaker = document.createElement('span');
    speaker.textContent = role === 'assistant' ? 'Petey' : personName;
    meta.append(speaker);
    if (!options.typing && text) {
        const copyButton = document.createElement('button');
        copyButton.type = 'button';
        copyButton.className = 'copy-message';
        copyButton.textContent = 'Copy';
        copyButton.title = 'Copy message';
        copyButton.addEventListener('click', () => copyChatText(text, copyButton));
        meta.append(copyButton);
    }
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    content.append(meta, bubble);

    if (options.gifUrl) {
        const image = document.createElement('img');
        image.className = 'gif';
        image.src = options.gifUrl;
        image.alt = 'GIF selected by Petey';
        content.append(image);
    }
    if ((options.toolEvents || []).some(event =>
        event.name === 'generate_image' && event.result?.status === 'queued'
    )) {
        const action = document.createElement('button');
        action.type = 'button';
        action.className = 'message-action';
        action.textContent = 'View generation progress';
        action.addEventListener('click', () => {
            showView('media');
            loadMediaJobs();
        });
        content.append(action);
    }
    item.append(avatar, content);
    messages.append(item);
    messages.scrollTop = messages.scrollHeight;
    return item;
}

async function loadDesktop() {
    try {
        const bootstrap = await apiJson('/api/desktop/bootstrap');
        personName = bootstrap.person_name || 'User';
        document.getElementById('user-display-name').value = personName;
        activeConversationId = bootstrap.conversation_id;
        conversations = bootstrap.conversations || [];
        preferences = {...preferences, ...(bootstrap.preferences || {})};
        workspaces = bootstrap.workspaces || [];
        activeWorkspaceId = bootstrap.active_workspace_id || '';
        applyPreferences();
        renderConversations();
        await loadConversationMessages();
    } catch (error) {
        statusText.textContent = 'Could not load local state';
    }
}

async function loadConversationMessages() {
    messages.innerHTML = '';
    const history = await apiJson('/api/desktop/messages');
    history.forEach(item => addMessage(item.role, item.message));
    if (!history.length) showEmptyState();
    const active = conversations.find(item => item.id === activeConversationId);
    statusText.textContent = active ? active.title : `Ready for ${personName}`;
}

function renderConversations() {
    const list = document.getElementById('conversation-list');
    list.innerHTML = '';
    conversations.forEach(conversation => {
        const row = document.createElement('div');
        row.className = `conversation-row${conversation.id === activeConversationId ? ' active' : ''}`;
        const select = document.createElement('button');
        select.className = 'conversation-select';
        select.type = 'button';
        select.textContent = conversation.title;
        select.title = conversation.title;
        select.addEventListener('click', () => selectConversation(conversation.id));
        select.addEventListener('dblclick', event => {
            event.preventDefault();
            renameConversation(conversation);
        });
        const rename = document.createElement('button');
        rename.className = 'conversation-rename';
        rename.type = 'button';
        rename.textContent = '✎';
        rename.title = `Rename ${conversation.title}`;
        rename.setAttribute('aria-label', `Rename ${conversation.title}`);
        rename.addEventListener('click', () => renameConversation(conversation));
        const remove = document.createElement('button');
        remove.className = 'conversation-delete';
        remove.type = 'button';
        remove.textContent = '×';
        remove.title = `Delete ${conversation.title}`;
        remove.addEventListener('click', () => deleteConversation(conversation));
        row.append(select, rename, remove);
        list.append(row);
    });
}

async function renameConversation(conversation) {
    const requested = window.prompt('Rename chat:', conversation.title);
    if (requested === null) return;
    const title = requested.trim();
    if (!title) {
        window.alert('Enter a chat name.');
        return;
    }
    try {
        const payload = await apiJson(`/api/desktop/conversations/${encodeURIComponent(conversation.id)}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title}),
        });
        conversations = payload.conversations;
        renderConversations();
        if (conversation.id === activeConversationId) statusText.textContent = payload.conversation.title;
    } catch (error) {
        window.alert(error.message);
    }
}

async function selectConversation(conversationId) {
    if (conversationId === activeConversationId && !document.getElementById('temporary-mode').checked) return;
    await apiJson(`/api/desktop/conversations/${encodeURIComponent(conversationId)}/select`, {method: 'PUT'});
    activeConversationId = conversationId;
    leaveTemporaryMode();
    renderConversations();
    showView('chat');
    await loadConversationMessages();
}

async function deleteConversation(conversation) {
    if (!window.confirm(`Delete “${conversation.title}” and all of its messages?`)) return;
    try {
        const payload = await apiJson(`/api/desktop/conversations/${encodeURIComponent(conversation.id)}`, {method: 'DELETE'});
        conversations = payload.conversations;
        activeConversationId = payload.conversation_id;
        leaveTemporaryMode();
        renderConversations();
        await loadConversationMessages();
    } catch (error) {
        window.alert(error.message);
    }
}

document.getElementById('new-chat').addEventListener('click', async () => {
    try {
        const payload = await apiJson('/api/desktop/conversations', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title: 'New chat'}),
        });
        conversations = payload.conversations;
        activeConversationId = payload.conversation_id;
        leaveTemporaryMode();
        renderConversations();
        showView('chat');
        showEmptyState('New chat', 'This conversation will be saved to Petey’s local memory.');
        statusText.textContent = payload.conversation.title;
        messageInput.focus();
    } catch (error) {
        window.alert(error.message);
    }
});

attachmentInput.addEventListener('change', () => {
    const file = attachmentInput.files[0];
    attachmentChip.hidden = !file;
    attachmentChip.textContent = file ? `Attached: ${file.name}` : '';
});

messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 180)}px`;
});

messageInput.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        composer.requestSubmit();
    }
});

composer.addEventListener('submit', async event => {
    event.preventDefault();
    const text = messageInput.value.trim();
    const file = attachmentInput.files[0];
    if (!text && !file) return;

    const displayedText = text || `[Attached ${file.name}]`;
    const temporary = document.getElementById('temporary-mode').checked;
    const priorTemporaryHistory = temporaryHistory.slice();
    addMessage('user', displayedText);
    const typing = addMessage('assistant', 'Typing…', {typing: true});
    const body = new FormData();
    body.append('message', text);
    if (file) body.append('attachment', file);
    if (temporary) {
        body.append('temporary', 'true');
        body.append('temporary_history', JSON.stringify(priorTemporaryHistory));
        temporaryHistory.push({role: 'user', content: displayedText});
    }

    messageInput.value = '';
    messageInput.style.height = 'auto';
    attachmentInput.value = '';
    attachmentChip.hidden = true;
    sendButton.disabled = true;
    statusText.textContent = 'Petey is typing…';
    try {
        const response = await fetch('/api/desktop/chat', {method: 'POST', body});
        const payload = await response.json();
        typing.remove();
        if (!response.ok) throw new Error(payload.error || 'Request failed');
        addMessage('assistant', payload.text || '', {
            gifUrl: payload.gif_url,
            toolEvents: payload.tool_events || [],
        });
        if (temporary) temporaryHistory.push({role: 'assistant', content: payload.text || ''});
        statusText.textContent = temporary ? 'Temporary · nothing saved' : `Ready for ${personName}`;
    } catch (error) {
        typing.remove();
        addMessage('assistant', `I hit a problem: ${error.message}`);
        statusText.textContent = 'Something went wrong';
    } finally {
        sendButton.disabled = false;
        messageInput.focus();
    }
});

loadDesktop();

async function apiJson(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
}

function setFeedback(element, text, kind = '') {
    element.textContent = text;
    element.classList.remove('success', 'error');
    if (kind) element.classList.add(kind);
}

function applyPreferences() {
    const scale = Number(preferences.ui_scale) || 1;
    document.documentElement.style.setProperty('--ui-scale', scale);
    document.querySelector('.app-shell').classList.toggle('sidebar-collapsed', Boolean(preferences.sidebar_collapsed));
    document.getElementById('always-on-top').checked = Boolean(preferences.always_on_top);
    document.getElementById('sidebar-collapsed-setting').checked = Boolean(preferences.sidebar_collapsed);
    document.getElementById('ui-scale-value').textContent = `${Math.round(scale * 100)}%`;
    document.getElementById('collapse-sidebar').title = preferences.sidebar_collapsed ? 'Expand sidebar' : 'Collapse sidebar';
}

async function savePreferences(changes, nativeTop = false) {
    const feedback = document.getElementById('preference-status');
    try {
        const payload = await apiJson('/api/desktop/preferences', {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(changes),
        });
        preferences = payload.preferences;
        applyPreferences();
        if (nativeTop && window.pywebview?.api?.set_always_on_top) {
            await window.pywebview.api.set_always_on_top(preferences.always_on_top);
        }
        setFeedback(feedback, 'Saved.', 'success');
        window.setTimeout(() => setFeedback(feedback, ''), 1200);
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
        applyPreferences();
    }
}

function changeScale(delta) {
    const next = Math.max(.75, Math.min(1.5, Math.round(((Number(preferences.ui_scale) || 1) + delta) * 10) / 10));
    if (next !== preferences.ui_scale) savePreferences({ui_scale: next});
}

document.getElementById('collapse-sidebar').addEventListener('click', () => {
    savePreferences({sidebar_collapsed: !preferences.sidebar_collapsed});
});
document.getElementById('sidebar-collapsed-setting').addEventListener('change', event => {
    savePreferences({sidebar_collapsed: event.target.checked});
});
document.getElementById('always-on-top').addEventListener('change', event => {
    savePreferences({always_on_top: event.target.checked}, true);
});
document.getElementById('scale-down').addEventListener('click', () => changeScale(-.1));
document.getElementById('scale-up').addEventListener('click', () => changeScale(.1));
document.getElementById('scale-reset').addEventListener('click', () => savePreferences({ui_scale: 1}));

document.addEventListener('keydown', event => {
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    if (['+', '='].includes(event.key)) {
        event.preventDefault();
        changeScale(.1);
    } else if (event.key === '-') {
        event.preventDefault();
        changeScale(-.1);
    } else if (event.key === '0') {
        event.preventDefault();
        savePreferences({ui_scale: 1});
    }
});

function leaveTemporaryMode() {
    const toggle = document.getElementById('temporary-mode');
    toggle.checked = false;
    toggle.closest('.temporary-toggle').classList.remove('active');
    temporaryHistory = [];
}

document.getElementById('temporary-mode').addEventListener('change', async event => {
    const active = event.target.checked;
    event.target.closest('.temporary-toggle').classList.toggle('active', active);
    temporaryHistory = [];
    if (active) {
        showEmptyState('Temporary chat', 'This chat will not be saved and will not use memory or RAG.');
        statusText.textContent = 'Temporary · nothing saved';
    } else {
        try {
            await loadConversationMessages();
        } catch (error) {
            statusText.textContent = 'Could not reload saved chat';
        }
    }
});

function showView(view) {
    document.querySelectorAll('.nav-button').forEach(item => item.classList.remove('active'));
    document.querySelectorAll('.app-view').forEach(item => item.classList.remove('active-view'));
    document.getElementById(`view-${view}`).classList.add('active-view');
    const settingsViews = ['settings', 'personality', 'knowledge', 'memory'];
    const navView = settingsViews.includes(view) ? 'settings' : view;
    document.querySelector(`.nav-button[data-view="${navView}"]`)?.classList.add('active');
    window.location.hash = view === 'settings' ? 'settings' : view;
    if (view === 'personality' && !personalityLoaded) loadPersonality();
    if (view === 'settings' && !aiProviderLoaded) loadAIProvider();
    if (view === 'media' && !mediaCatalogLoaded) loadMediaCatalog();
    if (view === 'media') loadMediaJobs();
    if (view === 'gallery') loadGallery();
    if (view === 'workspace' && !workspaceLoaded) loadWorkspaces();
    if (view === 'knowledge') loadKnowledge();
    if (view === 'memory') {
        loadMemoryStats();
        if (!memoryProviderLoaded) loadMemoryProvider();
    }
}

const aiProviderSelect = document.getElementById('ai-provider');
const aiModelInput = document.getElementById('ai-model');
const aiVisionModelInput = document.getElementById('ai-vision-model');
const aiBaseUrlInput = document.getElementById('ai-base-url');
const aiApiKeyInput = document.getElementById('ai-api-key');

const aiProviderDefaults = {
    gemini: {model: 'gemini-2.5-flash', base_url: ''},
    openai: {model: 'gpt-4.1-mini', base_url: ''},
    local: {model: '', base_url: 'http://localhost:1234/v1'},
};

function configureAIProvider(provider = aiProviderSelect.value) {
    const saved = aiProviderConfiguration?.providers?.[provider] || aiProviderDefaults[provider];
    aiModelInput.value = saved.model || aiProviderDefaults[provider].model;
    aiVisionModelInput.value = aiProviderConfiguration?.vision_model || 'gemini-2.5-flash';
    aiBaseUrlInput.value = saved.base_url || aiProviderDefaults.local.base_url;
    document.getElementById('ai-base-url-field').hidden = provider !== 'local';
    document.getElementById('local-provider-presets').hidden = provider !== 'local';
    document.getElementById('load-ai-models').hidden = provider === 'gemini';
    document.getElementById('clear-ai-key').hidden = !saved.has_api_key;
    document.getElementById('ai-thinking-enabled').checked = saved.thinking_enabled !== false;
    const source = provider === 'local' && !saved.has_api_key
        ? 'optional for most local servers'
        : saved.api_key_source === 'environment' ? 'configured by environment' : saved.has_api_key ? 'saved securely in local settings' : 'not configured';
    document.getElementById('ai-key-state').textContent = source;
    document.getElementById('vision-key-state').textContent = aiProviderConfiguration?.vision_has_api_key
        ? 'Gemini key configured'
        : 'Gemini key not configured';
    document.getElementById('ai-provider-badge').textContent = {gemini: 'Gemini', openai: 'OpenAI', local: 'Local'}[provider];
    document.getElementById('ai-provider-note').textContent = provider === 'local'
        ? 'Compatible with LM Studio, Ollama, and other servers exposing /v1/chat/completions.'
        : provider === 'openai'
            ? 'Requires an OpenAI API key; a ChatGPT subscription does not supply API credits.'
            : 'The saved Gemini key also powers RAG embeddings. Other chat providers keep Gemini embeddings for compatibility with existing knowledge.';
    aiApiKeyInput.value = '';
    aiApiKeyInput.placeholder = provider === 'local'
        ? 'Optional bearer token'
        : 'Leave blank to keep the existing key';
    const datalist = document.getElementById('ai-model-options');
    datalist.innerHTML = '';
    const suggestions = provider === 'gemini'
        ? ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash']
        : provider === 'openai' ? ['gpt-4.1-mini', 'gpt-4.1', 'gpt-4o-mini'] : [];
    suggestions.forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        datalist.append(option);
    });
}

async function loadAIProvider() {
    const feedback = document.getElementById('ai-provider-status');
    try {
        const payload = await apiJson('/api/desktop/ai-provider');
        aiProviderConfiguration = payload.configuration;
        aiProviderSelect.value = payload.configuration.provider;
        configureAIProvider();
        aiProviderLoaded = true;
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
}

async function saveAIProvider(showFeedback = true, extra = {}) {
    const feedback = document.getElementById('ai-provider-status');
    const button = document.getElementById('save-ai-provider');
    button.disabled = true;
    if (showFeedback) setFeedback(feedback, 'Saving provider…');
    const payload = {
        provider: aiProviderSelect.value,
        model: aiModelInput.value.trim(),
        vision_model: aiVisionModelInput.value.trim(),
        base_url: aiBaseUrlInput.value.trim(),
        api_key: aiApiKeyInput.value.trim(),
        thinking_enabled: document.getElementById('ai-thinking-enabled').checked,
        ...extra,
    };
    try {
        const result = await apiJson('/api/desktop/ai-provider', {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
        });
        aiProviderConfiguration = result.configuration;
        configureAIProvider(payload.provider);
        if (showFeedback) setFeedback(feedback, 'Saved — new requests will use this provider.', 'success');
        return result.configuration;
    } finally {
        button.disabled = false;
    }
}

aiProviderSelect.addEventListener('change', () => configureAIProvider());
document.getElementById('save-ai-provider').addEventListener('click', async () => {
    try {
        await saveAIProvider();
    } catch (error) {
        setFeedback(document.getElementById('ai-provider-status'), error.message, 'error');
    }
});

document.querySelectorAll('.local-preset').forEach(button => {
    button.addEventListener('click', () => {
        aiBaseUrlInput.value = button.dataset.url;
    });
});

document.getElementById('test-ai-provider').addEventListener('click', async () => {
    const button = document.getElementById('test-ai-provider');
    const feedback = document.getElementById('ai-provider-status');
    button.disabled = true;
    try {
        await saveAIProvider(false);
        setFeedback(feedback, 'Connecting and asking the model for a test response…');
        const payload = await apiJson('/api/desktop/ai-provider/test', {method: 'POST'});
        setFeedback(feedback, `Connected: ${payload.response}`, 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

document.getElementById('load-ai-models').addEventListener('click', async () => {
    const button = document.getElementById('load-ai-models');
    const feedback = document.getElementById('ai-provider-status');
    button.disabled = true;
    try {
        await saveAIProvider(false);
        setFeedback(feedback, 'Loading available models…');
        const payload = await apiJson('/api/desktop/ai-provider/models');
        const datalist = document.getElementById('ai-model-options');
        datalist.innerHTML = '';
        payload.models.forEach(name => {
            const option = document.createElement('option');
            option.value = name;
            datalist.append(option);
        });
        if (payload.models.length === 1) aiModelInput.value = payload.models[0];
        setFeedback(feedback, `Found ${payload.models.length} model${payload.models.length === 1 ? '' : 's'}.`, 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

document.getElementById('clear-ai-key').addEventListener('click', async () => {
    if (!window.confirm('Clear the saved API key for this provider? Environment keys are unaffected.')) return;
    try {
        await saveAIProvider(false, {clear_api_key: true});
        setFeedback(document.getElementById('ai-provider-status'), 'Saved API key cleared.', 'success');
    } catch (error) {
        setFeedback(document.getElementById('ai-provider-status'), error.message, 'error');
    }
});

document.querySelectorAll('.nav-button').forEach(button => {
    button.addEventListener('click', () => showView(button.dataset.view));
});

document.querySelectorAll('.settings-tab').forEach(button => {
    button.addEventListener('click', () => showView(button.dataset.settingsView));
});

document.getElementById('project-link').addEventListener('click', async event => {
    if (!window.pywebview?.api?.open_project_repository) return;
    event.preventDefault();
    await window.pywebview.api.open_project_repository();
});

document.getElementById('media-provider-link').addEventListener('click', async event => {
    if (!window.pywebview?.api?.open_media_provider) return;
    event.preventDefault();
    await window.pywebview.api.open_media_provider();
});

document.getElementById('save-user-display-name').addEventListener('click', async () => {
    const input = document.getElementById('user-display-name');
    const feedback = document.getElementById('user-display-name-status');
    const button = document.getElementById('save-user-display-name');
    button.disabled = true;
    try {
        const payload = await apiJson('/api/desktop/identity', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({display_name: input.value}),
        });
        personName = payload.person_name || 'User';
        input.value = personName;
        await loadConversationMessages();
        setFeedback(feedback, `Saved as ${personName}.`, 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

const sliderKeys = ['tone', 'verbosity', 'formality', 'empathy'];
sliderKeys.forEach(key => {
    const input = document.getElementById(`persona-${key}`);
    input.addEventListener('input', () => {
        document.getElementById(`${key}-value`).textContent = input.value;
    });
});

function fillPersona(persona) {
    document.getElementById('persona-preset').value = persona.preset_key || '';
    document.getElementById('persona-name').value = persona.name || 'Petey';
    document.getElementById('persona-role').value = persona.role_tag || 'Assistant';
    document.getElementById('persona-tagline').value = persona.tagline || '';
    document.getElementById('persona-prompt').value = persona.system_prompt || '';
    document.getElementById('persona-traits').value = (persona.traits || []).join(', ');
    sliderKeys.forEach(key => {
        const value = persona.sliders?.[key] ?? 50;
        document.getElementById(`persona-${key}`).value = value;
        document.getElementById(`${key}-value`).textContent = value;
    });
}

function readPersonaForm() {
    return {
        preset_key: document.getElementById('persona-preset').value,
        name: document.getElementById('persona-name').value,
        role_tag: document.getElementById('persona-role').value,
        tagline: document.getElementById('persona-tagline').value,
        system_prompt: document.getElementById('persona-prompt').value,
        traits: document.getElementById('persona-traits').value.split(','),
        sliders: Object.fromEntries(sliderKeys.map(key =>
            [key, document.getElementById(`persona-${key}`).value]
        )),
    };
}

function renderSavedPersonaSlots() {
    const container = document.getElementById('saved-persona-slots');
    container.innerHTML = '';
    Array.from({length: 5}, (_, index) => {
        const persona = savedPersonas[index] || null;
        const card = document.createElement('article');
        card.className = 'persona-slot';
        const title = document.createElement('strong');
        title.textContent = persona?.name || `Slot ${index + 1}`;
        title.title = title.textContent;
        const description = document.createElement('small');
        description.textContent = persona
            ? (persona.role_tag || `Saved in slot ${index + 1}`)
            : 'Empty';
        const actions = document.createElement('div');
        actions.className = 'persona-slot-actions';
        const load = document.createElement('button');
        load.type = 'button';
        load.textContent = 'Load';
        load.disabled = !persona;
        load.addEventListener('click', () => {
            fillPersona({...persona, preset_key: ''});
            setFeedback(
                document.getElementById('personality-status'),
                `Loaded slot ${index + 1} into the editor — save personality to activate it.`,
                'success',
            );
        });
        const save = document.createElement('button');
        save.type = 'button';
        save.textContent = persona ? 'Replace' : 'Save';
        save.addEventListener('click', () => savePersonaSlot(index + 1, Boolean(persona)));
        actions.append(load, save);
        if (persona) {
            const clear = document.createElement('button');
            clear.type = 'button';
            clear.className = 'clear-slot';
            clear.textContent = '×';
            clear.title = `Clear slot ${index + 1}`;
            clear.addEventListener('click', () => clearPersonaSlot(index + 1));
            actions.append(clear);
        }
        card.append(title, description, actions);
        container.append(card);
    });
}

async function savePersonaSlot(slot, replacing) {
    if (replacing && !window.confirm(`Replace the persona saved in slot ${slot}?`)) return;
    const feedback = document.getElementById('personality-status');
    try {
        const result = await apiJson(`/api/desktop/personality/slots/${slot}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(readPersonaForm()),
        });
        savedPersonas = result.saved_personas || [];
        renderSavedPersonaSlots();
        setFeedback(feedback, `Saved the current editor values to slot ${slot}.`, 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
}

async function clearPersonaSlot(slot) {
    if (!window.confirm(`Clear saved persona slot ${slot}?`)) return;
    const feedback = document.getElementById('personality-status');
    try {
        const result = await apiJson(`/api/desktop/personality/slots/${slot}`, {method: 'DELETE'});
        savedPersonas = result.saved_personas || [];
        renderSavedPersonaSlots();
        setFeedback(feedback, `Cleared persona slot ${slot}.`, 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
}

async function loadPersonality() {
    const feedback = document.getElementById('personality-status');
    setFeedback(feedback, 'Loading…');
    try {
        const payload = await apiJson('/api/desktop/personality');
        personaPresets = payload.presets || {};
        savedPersonas = payload.saved_personas || [];
        const select = document.getElementById('persona-preset');
        select.innerHTML = '<option value="">Custom</option>';
        Object.entries(personaPresets).forEach(([key, preset]) => {
            const option = document.createElement('option');
            option.value = key;
            option.textContent = `${preset.icon || '✦'} ${preset.name}`;
            select.append(option);
        });
        fillPersona(payload.persona);
        renderSavedPersonaSlots();
        personalityLoaded = true;
        setFeedback(feedback, '');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
}

document.getElementById('persona-preset').addEventListener('change', event => {
    const preset = personaPresets[event.target.value];
    if (!preset) return;
    fillPersona({
        name: preset.name,
        role_tag: 'Assistant',
        tagline: '',
        system_prompt: preset.system_prompt,
        preset_key: event.target.value,
        traits: preset.traits,
        sliders: preset.sliders,
    });
});

document.getElementById('save-personality').addEventListener('click', async () => {
    const feedback = document.getElementById('personality-status');
    const button = document.getElementById('save-personality');
    button.disabled = true;
    setFeedback(feedback, 'Saving…');
    const payload = readPersonaForm();
    try {
        const result = await apiJson('/api/desktop/personality', {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
        });
        fillPersona(result.persona);
        setFeedback(feedback, 'Saved — new chats use this personality immediately.', 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

document.getElementById('rewrite-persona').addEventListener('click', async () => {
    const button = document.getElementById('rewrite-persona');
    const feedback = document.getElementById('personality-status');
    button.disabled = true;
    setFeedback(feedback, 'Gemini is rewriting the prompt…');
    try {
        const result = await apiJson('/api/desktop/personality/rewrite', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({prompt: document.getElementById('persona-prompt').value}),
        });
        document.getElementById('persona-prompt').value = result.prompt;
        document.getElementById('persona-preset').value = '';
        setFeedback(feedback, 'Rewritten — review it, then save.', 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

const knowledgeFile = document.getElementById('knowledge-file');
const uploadKnowledge = document.getElementById('upload-knowledge');
knowledgeFile.addEventListener('change', () => {
    const file = knowledgeFile.files[0];
    uploadKnowledge.disabled = !file;
    document.querySelector('.upload-button span').textContent = file ? file.name : 'Choose file';
});

uploadKnowledge.addEventListener('click', async () => {
    const file = knowledgeFile.files[0];
    if (!file) return;
    const feedback = document.getElementById('knowledge-upload-status');
    const body = new FormData();
    body.append('file', file);
    uploadKnowledge.disabled = true;
    setFeedback(feedback, 'Reading and queuing document…');
    try {
        const result = await apiJson('/api/desktop/knowledge', {method: 'POST', body});
        setFeedback(feedback, `${result.message} Embeddings continue in the background.`, 'success');
        knowledgeFile.value = '';
        document.querySelector('.upload-button span').textContent = 'Choose file';
        window.setTimeout(loadKnowledge, 700);
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
        uploadKnowledge.disabled = false;
    }
});

async function loadKnowledge() {
    const list = document.getElementById('knowledge-list');
    list.innerHTML = '<p class="muted">Loading documents…</p>';
    try {
        const payload = await apiJson('/api/desktop/knowledge');
        list.innerHTML = '';
        if (!payload.documents.length) {
            list.innerHTML = '<p class="muted">No knowledge files uploaded yet.</p>';
            return;
        }
        payload.documents.forEach(filename => {
            const row = document.createElement('div');
            row.className = 'document-row';
            const name = document.createElement('span');
            name.textContent = `▤  ${filename}`;
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.textContent = 'Delete';
            remove.addEventListener('click', () => deleteKnowledge(filename));
            row.append(name, remove);
            list.append(row);
        });
    } catch (error) {
        list.innerHTML = '';
        const message = document.createElement('p');
        message.className = 'wide-status error';
        message.textContent = error.message;
        list.append(message);
    }
}

async function deleteKnowledge(filename) {
    if (!window.confirm(`Delete ${filename} and all of its stored knowledge?`)) return;
    try {
        await apiJson(`/api/desktop/knowledge/${encodeURIComponent(filename)}`, {method: 'DELETE'});
        await loadKnowledge();
    } catch (error) {
        setFeedback(document.getElementById('knowledge-upload-status'), error.message, 'error');
    }
}

document.getElementById('refresh-knowledge').addEventListener('click', loadKnowledge);
document.getElementById('search-rag').addEventListener('click', async () => {
    const query = document.getElementById('rag-query').value.trim();
    const results = document.getElementById('rag-results');
    if (!query) return;
    results.hidden = false;
    results.textContent = 'Searching semantic memory…';
    try {
        const payload = await apiJson('/api/desktop/knowledge/search', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({query}),
        });
        results.textContent = payload.found ? payload.result : 'No relevant memory was found.';
    } catch (error) {
        results.textContent = error.message;
    }
});

const memoryProviderSelect = document.getElementById('memory-provider');
const memoryModelInput = document.getElementById('memory-model');
const memoryModelDefaults = {
    local: 'nomic-embed-text',
    gemini: 'gemini-embedding-001',
    openai: 'text-embedding-3-small',
};

function configureMemoryProvider(provider = memoryProviderSelect.value) {
    const models = memoryProviderConfiguration?.models || {};
    memoryModelInput.value = models[provider] || memoryModelDefaults[provider];
    document.getElementById('memory-base-url-field').hidden = provider !== 'local';
    document.getElementById('memory-base-url').value = memoryProviderConfiguration?.local_base_url || 'http://localhost:11434/v1';
    document.getElementById('semantic-memory-enabled').checked = memoryProviderConfiguration?.semantic_enabled !== false;
    document.getElementById('memory-provider-note').textContent = provider === 'local'
        ? 'Fully local when the chat provider is also Local. Ollama example: ollama pull nomic-embed-text.'
        : `Raw memory remains local; only text sent for vector creation goes to ${provider === 'openai' ? 'OpenAI' : 'Gemini'}.`;
    const options = document.getElementById('memory-model-options');
    options.innerHTML = '';
    const suggestions = provider === 'local' ? ['nomic-embed-text', 'mxbai-embed-large']
        : provider === 'openai' ? ['text-embedding-3-small', 'text-embedding-3-large']
            : ['gemini-embedding-001'];
    suggestions.forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        options.append(option);
    });
}

async function loadMemoryProvider() {
    try {
        const payload = await apiJson('/api/desktop/memory/provider');
        memoryProviderConfiguration = payload.configuration;
        memoryProviderSelect.value = payload.configuration.provider;
        configureMemoryProvider();
        memoryProviderLoaded = true;
    } catch (error) {
        setFeedback(document.getElementById('memory-provider-status'), error.message, 'error');
    }
}

async function saveMemoryProvider(showFeedback = true) {
    const feedback = document.getElementById('memory-provider-status');
    const payload = {
        provider: memoryProviderSelect.value,
        model: memoryModelInput.value.trim(),
        semantic_enabled: document.getElementById('semantic-memory-enabled').checked,
        local_base_url: document.getElementById('memory-base-url').value.trim(),
    };
    const result = await apiJson('/api/desktop/memory/provider', {
        method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    memoryProviderConfiguration = result.configuration;
    configureMemoryProvider(payload.provider);
    if (showFeedback) setFeedback(feedback, 'Memory provider saved.', 'success');
    return result;
}

memoryProviderSelect.addEventListener('change', () => configureMemoryProvider());
document.getElementById('save-memory-provider').addEventListener('click', async () => {
    try {
        await saveMemoryProvider();
    } catch (error) {
        setFeedback(document.getElementById('memory-provider-status'), error.message, 'error');
    }
});

document.getElementById('test-memory-provider').addEventListener('click', async () => {
    const feedback = document.getElementById('memory-provider-status');
    try {
        await saveMemoryProvider(false);
        setFeedback(feedback, 'Creating a test embedding…');
        const payload = await apiJson('/api/desktop/memory/provider/test', {method: 'POST'});
        setFeedback(feedback, payload.status === 'disabled'
            ? payload.message
            : `Connected — ${payload.model} returned ${payload.dimensions} dimensions.`, 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
});

document.getElementById('rebuild-memory').addEventListener('click', async () => {
    if (!window.confirm('Rebuild every stored vector using the selected embedding provider?')) return;
    const feedback = document.getElementById('memory-provider-status');
    try {
        await saveMemoryProvider(false);
        const payload = await apiJson('/api/desktop/memory/rebuild', {method: 'POST'});
        setFeedback(feedback, `Rebuilding ${payload.items} memory items in the background.`, 'success');
        window.setTimeout(loadMemoryStats, 1000);
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
});

document.getElementById('fully-local-preset').addEventListener('click', async () => {
    const feedback = document.getElementById('memory-provider-status');
    try {
        if (!aiProviderLoaded) await loadAIProvider();
        aiProviderSelect.value = 'local';
        configureAIProvider('local');
        await saveAIProvider(false);
        memoryProviderSelect.value = 'local';
        memoryProviderConfiguration = memoryProviderConfiguration || {models: {}};
        configureMemoryProvider('local');
        document.getElementById('semantic-memory-enabled').checked = true;
        await saveMemoryProvider(false);
        setFeedback(feedback, 'Local chat and memory saved. Load both local models, then test both connections.', 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
});

async function loadMemoryStats() {
    try {
        const stats = await apiJson('/api/desktop/memory/stats');
        document.getElementById('memory-conversation-count').textContent = stats.conversation_messages;
        document.getElementById('memory-document-count').textContent = stats.document_chunks;
        document.getElementById('memory-embedded-count').textContent = stats.embedded_memories;
    } catch (error) {
        setFeedback(document.getElementById('clear-memory-status'), error.message, 'error');
    }
}

document.getElementById('clear-conversation').addEventListener('click', async () => {
    if (!window.confirm('Clear every message in the current conversation? Uploaded knowledge will be kept.')) return;
    const feedback = document.getElementById('clear-memory-status');
    try {
        const result = await apiJson('/api/desktop/memory/conversation', {method: 'DELETE'});
        messages.innerHTML = '<div class="empty-state" id="empty-state"><h2>Conversation cleared.</h2><p>Your uploaded knowledge is still available.</p></div>';
        setFeedback(feedback, `Deleted ${result.deleted} conversation messages.`, 'success');
        loadMemoryStats();
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
});

document.getElementById('reset-all-memory').addEventListener('click', async () => {
    if (!window.confirm('Permanently delete every saved message, document, vector, and generation metric?')) return;
    if (!window.confirm('This cannot be undone. Reset Petey’s entire local memory database?')) return;
    const feedback = document.getElementById('reset-memory-status');
    try {
        const payload = await apiJson('/api/desktop/memory/all', {method: 'DELETE'});
        showEmptyState('Memory reset', 'Petey’s new local database is empty.');
        setFeedback(feedback, `Deleted ${payload.deleted} stored memory items.`, 'success');
        await Promise.all([loadMemoryStats(), loadKnowledge()]);
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
});

const mediaOperation = document.getElementById('media-operation');
const mediaModel = document.getElementById('media-model');
const mediaSourceField = document.getElementById('media-source-field');
const mediaSource = document.getElementById('media-source');
const mediaNonimageSource = document.getElementById('media-nonimage-source');
const mediaPrompt = document.getElementById('media-prompt');
const mediaStatus = document.getElementById('media-status');
let mediaModelRequest = 0;
let selectedVisualImage = null;
let mediaSelectionUrl = '';
const mediaPromptDraftStorageKey = 'petey.media-prompt-drafts.v1';

const mediaOperationUI = {
    txt2img: {source: null, prompt: 'Image prompt', placeholder: 'Describe the image you want…', visual: true},
    img2img: {source: 'image', prompt: 'Restyle prompt', placeholder: 'Describe how the image should change…', visual: true},
    txt2video: {source: null, prompt: 'Video prompt', placeholder: 'Describe the scene and motion…', visual: true, video: true},
    img2video: {source: 'image', prompt: 'Animation prompt', placeholder: 'Describe how the image should move…', visual: true, video: true},
    vid2video: {source: 'video', prompt: 'Restyle prompt', placeholder: 'Describe the new video style…', visual: true, video: true},
    txt2music: {source: 'optional_audio', prompt: 'Music style / caption', placeholder: 'Energetic electronic pop with cinematic drums…', music: true},
    txt2audio: {source: null, prompt: 'Text to speak', placeholder: 'Enter the words Petey should speak…', speech: true},
    'img-rmbg': {source: 'image', prompt: null},
    'img-upscale': {source: 'image', prompt: null, upscale: true},
};

function loadMediaPromptDrafts() {
    try {
        const saved = JSON.parse(window.localStorage.getItem(mediaPromptDraftStorageKey) || '{}');
        if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return {};
        return Object.fromEntries(
            Object.entries(saved).filter(([operation, prompt]) =>
                mediaOperationUI[operation]?.prompt && typeof prompt === 'string'
            )
        );
    } catch (_error) {
        return {};
    }
}

const mediaPromptDrafts = loadMediaPromptDrafts();
let activeMediaOperation = mediaOperation.value;

function saveMediaPromptDrafts() {
    try {
        window.localStorage.setItem(mediaPromptDraftStorageKey, JSON.stringify(mediaPromptDrafts));
    } catch (_error) {
        // Draft persistence is optional when browser storage is unavailable.
    }
}

function rememberMediaPrompt(operation = activeMediaOperation) {
    if (!mediaOperationUI[operation]?.prompt) return;
    mediaPromptDrafts[operation] = mediaPrompt.value;
    saveMediaPromptDrafts();
}

async function loadMediaCatalog() {
    const connection = document.getElementById('media-connection');
    setFeedback(connection, 'Connecting…');
    try {
        const payload = await apiJson('/api/desktop/media');
        mediaSelectedModels = payload.selected_models || {};
        mediaCatalogLoaded = true;
        configureMediaOperation();
        startMediaPolling();
        refreshDeapiBalance();
        setFeedback(connection, payload.configured ? 'Media service connected' : 'Media service not configured', payload.configured ? 'success' : 'error');
    } catch (error) {
        setFeedback(connection, error.message, 'error');
    }
}

function configureMediaOperation() {
    const operation = mediaOperation.value;
    const config = mediaOperationUI[operation];
    const hasPrompt = Boolean(config.prompt);
    document.getElementById('media-prompt-field').hidden = !hasPrompt;
    document.getElementById('media-prompt-actions').hidden = !hasPrompt || operation === 'txt2audio';
    if (hasPrompt) {
        document.getElementById('media-prompt-label').textContent = config.prompt;
        mediaPrompt.placeholder = config.placeholder;
        mediaPrompt.value = mediaPromptDrafts[operation] || '';
    } else {
        mediaPrompt.value = '';
    }
    mediaSourceField.hidden = !config.source;
    if (config.source) {
        const labels = {image: 'Source image', video: 'Source video', optional_audio: 'Reference audio (optional)'};
        const accepts = {image: 'image/*', video: 'video/*,.mov,.avi', optional_audio: 'audio/*,.m4a,.flac'};
        document.getElementById('media-source-label').textContent = labels[config.source];
        const isImage = config.source === 'image';
        document.getElementById('media-image-source-controls').hidden = !isImage;
        mediaNonimageSource.hidden = isImage;
        if (isImage) mediaSource.accept = accepts.image;
        else mediaNonimageSource.accept = accepts[config.source];
    }
    clearMediaSourceSelection();
    document.getElementById('media-visual-fields').hidden = !config.visual;
    document.getElementById('media-video-fields').hidden = !config.video;
    document.getElementById('media-music-fields').hidden = !config.music;
    document.getElementById('media-speech-fields').hidden = !config.speech;
    document.getElementById('media-upscale-fields').hidden = !config.upscale;
    setFeedback(mediaStatus, '');
    loadMediaModels(operation);
}

async function loadMediaModels(operation) {
    const requestNumber = ++mediaModelRequest;
    mediaModel.disabled = true;
    mediaModel.innerHTML = '<option value="">Loading compatible models…</option>';
    try {
        const payload = await apiJson(`/api/desktop/media/models/${encodeURIComponent(operation)}`);
        if (requestNumber !== mediaModelRequest) return;
        mediaModel.innerHTML = '<option value="">Auto — first available</option>';
        (payload.models || []).forEach(model => {
            const option = document.createElement('option');
            option.value = model.slug;
            option.textContent = model.name || model.slug;
            mediaModel.append(option);
        });
        mediaModel.value = mediaSelectedModels[operation] || '';
        mediaModel.disabled = false;
        if (!payload.models?.length) setFeedback(mediaStatus, 'No compatible models were returned. Check the media service configuration.', 'error');
    } catch (error) {
        if (requestNumber !== mediaModelRequest) return;
        mediaModel.innerHTML = '<option value="">Models unavailable</option>';
        setFeedback(mediaStatus, error.message, 'error');
    }
}

mediaPrompt.addEventListener('input', () => rememberMediaPrompt(mediaOperation.value));
mediaOperation.addEventListener('change', () => {
    rememberMediaPrompt(activeMediaOperation);
    activeMediaOperation = mediaOperation.value;
    configureMediaOperation();
});

function clearMediaSourceSelection() {
    selectedVisualImage = null;
    mediaSource.value = '';
    mediaNonimageSource.value = '';
    if (mediaSelectionUrl?.startsWith('blob:')) URL.revokeObjectURL(mediaSelectionUrl);
    mediaSelectionUrl = '';
    document.getElementById('media-image-selection').hidden = true;
    document.getElementById('clear-media-image').hidden = true;
}

function showMediaImageSelection(file, previewUrl) {
    if (mediaSelectionUrl?.startsWith('blob:')) URL.revokeObjectURL(mediaSelectionUrl);
    mediaSelectionUrl = previewUrl;
    document.getElementById('media-image-selection-preview').src = previewUrl;
    document.getElementById('media-image-selection-name').textContent = `${file.name} · ${formatFileSize(file.size)}`;
    document.getElementById('media-image-selection').hidden = false;
    document.getElementById('clear-media-image').hidden = false;
}

mediaSource.addEventListener('change', () => {
    const file = mediaSource.files[0];
    selectedVisualImage = null;
    if (file) showMediaImageSelection(file, URL.createObjectURL(file));
});
document.getElementById('clear-media-image').addEventListener('click', clearMediaSourceSelection);

function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const imageBrowserDialog = document.getElementById('image-browser-dialog');
let imageBrowserToken = '';
let imageBrowserPath = '';

document.getElementById('browse-media-images').addEventListener('click', () => {
    imageBrowserDialog.showModal();
});
document.getElementById('close-image-browser').addEventListener('click', () => imageBrowserDialog.close());
document.getElementById('cancel-image-browser').addEventListener('click', () => imageBrowserDialog.close());
imageBrowserDialog.addEventListener('click', event => {
    if (event.target === imageBrowserDialog) imageBrowserDialog.close();
});

document.getElementById('choose-image-folder').addEventListener('click', async () => {
    const status = document.getElementById('image-browser-status');
    try {
        if (window.pywebview?.api?.choose_image_folder) {
            const path = await window.pywebview.api.choose_image_folder();
            if (path) await openImageBrowserFolder(path);
        } else {
            document.getElementById('image-browser-manual').hidden = false;
            document.getElementById('image-browser-folder-path').focus();
        }
    } catch (error) {
        setFeedback(status, error.message || String(error), 'error');
    }
});

document.getElementById('open-image-browser-path').addEventListener('click', async () => {
    try {
        await openImageBrowserFolder(document.getElementById('image-browser-folder-path').value.trim());
    } catch (error) {
        setFeedback(document.getElementById('image-browser-status'), error.message, 'error');
    }
});

async function openImageBrowserFolder(path) {
    const payload = await apiJson('/api/desktop/image-browser/open', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({path}),
    });
    imageBrowserToken = payload.token;
    imageBrowserPath = '';
    document.getElementById('image-browser-root').textContent = payload.path;
    document.getElementById('image-browser-manual').hidden = true;
    await loadImageBrowserDirectory('');
}

async function loadImageBrowserDirectory(path = '') {
    if (!imageBrowserToken) return;
    const status = document.getElementById('image-browser-status');
    const grid = document.getElementById('image-browser-grid');
    grid.innerHTML = '<p class="muted">Loading thumbnails…</p>';
    setFeedback(status, '');
    try {
        const query = new URLSearchParams({token: imageBrowserToken, path});
        const payload = await apiJson(`/api/desktop/image-browser/list?${query}`);
        imageBrowserPath = payload.path === '.' ? '' : payload.path;
        document.getElementById('image-browser-path').textContent = `/${imageBrowserPath}`;
        grid.innerHTML = '';
        payload.folders.forEach(folder => grid.append(createImageFolderCard(folder)));
        payload.images.forEach(image => grid.append(createImageThumbnailCard(image)));
        if (!payload.folders.length && !payload.images.length) {
            grid.innerHTML = '<p class="muted">No supported images in this folder.</p>';
        }
        setFeedback(status, `${payload.images.length} image${payload.images.length === 1 ? '' : 's'} in this folder.`);
    } catch (error) {
        grid.innerHTML = '';
        setFeedback(status, error.message, 'error');
    }
}

function createImageFolderCard(folder) {
    const button = document.createElement('button');
    button.className = 'image-folder-card';
    button.type = 'button';
    const icon = document.createElement('span');
    icon.textContent = '▸';
    const name = document.createElement('strong');
    name.textContent = folder.name;
    button.append(icon, name);
    button.addEventListener('click', () => loadImageBrowserDirectory(folder.path));
    return button;
}

function imageBrowserUrl(endpoint, path) {
    return `/api/desktop/image-browser/${endpoint}?${new URLSearchParams({token: imageBrowserToken, path})}`;
}

function createImageThumbnailCard(item) {
    const button = document.createElement('button');
    button.className = 'image-thumbnail-card';
    button.type = 'button';
    const preview = document.createElement('img');
    preview.loading = 'lazy';
    preview.src = imageBrowserUrl('thumbnail', item.path);
    preview.alt = '';
    const copy = document.createElement('span');
    const name = document.createElement('strong');
    name.textContent = item.name;
    const details = document.createElement('small');
    details.textContent = `${item.width && item.height ? `${item.width}×${item.height} · ` : ''}${formatFileSize(item.size)}`;
    copy.append(name, details);
    button.append(preview, copy);
    button.addEventListener('click', () => selectVisualImage(item, button));
    return button;
}

async function selectVisualImage(item, button) {
    const status = document.getElementById('image-browser-status');
    button.disabled = true;
    setFeedback(status, `Selecting ${item.name}…`);
    try {
        selectedVisualImage = {
            token: imageBrowserToken,
            path: item.path,
            name: item.name,
            size: item.size,
        };
        mediaSource.value = '';
        showMediaImageSelection(item, imageBrowserUrl('thumbnail', item.path));
        imageBrowserDialog.close();
        setFeedback(mediaStatus, `Selected ${item.name}.`, 'success');
    } catch (error) {
        button.disabled = false;
        setFeedback(status, error.message, 'error');
    }
}

document.getElementById('image-browser-up').addEventListener('click', () => {
    const pieces = imageBrowserPath.split('/').filter(Boolean);
    pieces.pop();
    loadImageBrowserDirectory(pieces.join('/'));
});

document.getElementById('enhance-media-prompt').addEventListener('click', async () => {
    const button = document.getElementById('enhance-media-prompt');
    if (!mediaPrompt.value.trim()) return;
    const operation = mediaOperation.value;
    const prompt = mediaPrompt.value;
    button.disabled = true;
    setFeedback(mediaStatus, 'Gemini is enhancing the prompt…');
    try {
        const payload = await apiJson('/api/desktop/media/enhance', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({operation, prompt}),
        });
        mediaPromptDrafts[operation] = payload.prompt;
        saveMediaPromptDrafts();
        if (mediaOperation.value === operation) {
            mediaPrompt.value = payload.prompt;
            setFeedback(mediaStatus, 'Prompt enhanced. Review it, then generate.', 'success');
        }
    } catch (error) {
        setFeedback(mediaStatus, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

function mediaParameters() {
    return {
        width: document.getElementById('media-width').value,
        height: document.getElementById('media-height').value,
        steps: document.getElementById('media-steps').value,
        guidance: document.getElementById('media-guidance').value,
        frames: document.getElementById('media-frames').value,
        fps: document.getElementById('media-fps').value,
        lyrics: document.getElementById('media-lyrics').value,
        duration: document.getElementById('media-duration').value,
        voice: document.getElementById('media-voice').value,
        speed: document.getElementById('media-speed').value,
        scale: document.getElementById('media-scale').value,
    };
}

function renderMediaResult(payload) {
    const container = document.getElementById('media-result');
    const openLink = document.getElementById('media-open-result');
    container.innerHTML = '';
    container.classList.add('has-result');
    let media;
    if (payload.kind === 'image') {
        media = document.createElement('img');
        media.alt = 'Generated by Petey';
    } else if (payload.kind === 'video') {
        media = document.createElement('video');
        media.controls = true;
        media.preload = 'auto';
        media.playsInline = true;
    } else {
        media = document.createElement('audio');
        media.controls = true;
    }
    const localItem = payload.gallery_item;
    const previewUrl = localItem?.local_filename
        ? `/api/desktop/gallery/preview/${encodeURIComponent(localItem.id)}`
        : payload.result_url;
    media.src = previewUrl;
    container.append(media);
    openLink.href = payload.result_url;
    openLink.hidden = false;
}

document.getElementById('generate-media').addEventListener('click', async () => {
    const operation = mediaOperation.value;
    const config = mediaOperationUI[operation];
    const file = config.source === 'image'
        ? mediaSource.files[0]
        : mediaNonimageSource.files[0];
    const hasVisualImage = config.source === 'image' && Boolean(selectedVisualImage);
    if (['image', 'video'].includes(config.source) && !file && !hasVisualImage) {
        setFeedback(mediaStatus, `Choose a source ${config.source} first.`, 'error');
        return;
    }
    if (config.prompt && !mediaPrompt.value.trim()) {
        setFeedback(mediaStatus, 'Enter a prompt or text first.', 'error');
        return;
    }
    const button = document.getElementById('generate-media');
    const body = new FormData();
    body.append('operation', operation);
    body.append('model_slug', mediaModel.value);
    body.append('prompt', mediaPrompt.value);
    body.append('parameters', JSON.stringify(mediaParameters()));
    if (file) body.append('source', file);
    if (hasVisualImage) {
        body.append('source_browser_token', selectedVisualImage.token);
        body.append('source_browser_path', selectedVisualImage.path);
    }

    button.disabled = true;
    setFeedback(mediaStatus, 'Adding generation to Petey’s media queue…');
    try {
        const payload = await apiJson('/api/desktop/media/generate', {method: 'POST', body});
        mediaSelectedModels[operation] = mediaModel.value;
        setFeedback(mediaStatus, `Queued ${payload.job.id.slice(0, 8)}. You can submit another generation now.`, 'success');
        await loadMediaJobs();
        startMediaPolling();
    } catch (error) {
        setFeedback(mediaStatus, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

function startMediaPolling() {
    if (mediaPollTimer) return;
    mediaPollTimer = window.setInterval(loadMediaJobs, 2000);
}

async function loadMediaJobs() {
    const container = document.getElementById('media-jobs');
    try {
        const payload = await apiJson('/api/desktop/media/jobs');
        const jobs = payload.jobs || [];
        container.innerHTML = '';
        if (!jobs.length) {
            container.innerHTML = '<p class="muted">No generations submitted this session.</p>';
            return;
        }
        let newlyCompleted = false;
        jobs.slice(0, 12).forEach(job => {
            const card = document.createElement('div');
            card.className = `media-job ${job.status}${job.preview_url ? ' has-preview' : ''}`;
            const dot = document.createElement('span');
            dot.className = 'media-job-dot';
            let preview = null;
            if (job.preview_url) {
                const previewPath = (() => {
                    try { return new URL(job.preview_url).pathname.toLowerCase(); }
                    catch (_error) { return ''; }
                })();
                const videoPreview = /\.(mp4|webm|mov|m4v)$/.test(previewPath);
                preview = document.createElement(videoPreview ? 'video' : 'img');
                preview.className = 'media-job-preview';
                preview.src = job.preview_url;
                if (videoPreview) {
                    preview.muted = true;
                    preview.autoplay = true;
                    preview.loop = true;
                    preview.playsInline = true;
                    preview.preload = 'metadata';
                } else {
                    preview.alt = 'Live generation preview';
                }
            }
            const copy = document.createElement('div');
            copy.className = 'media-job-copy';
            const title = document.createElement('strong');
            title.textContent = job.prompt || mediaOperationUI[job.operation]?.prompt || job.operation;
            const detail = document.createElement('small');
            detail.textContent = `${job.operation} · ${job.model_slug || 'Auto model'}`;
            copy.append(title, detail);
            const status = document.createElement('span');
            status.className = 'media-job-status';
            const numericProgress = Number(job.progress);
            const hasProgress = job.progress !== null && job.progress !== undefined && Number.isFinite(numericProgress);
            if (job.status === 'failed') status.textContent = job.error;
            else if (job.status === 'running') {
                const providerStatus = job.provider_status || 'processing';
                status.textContent = hasProgress ? `${providerStatus} · ${numericProgress.toFixed(numericProgress % 1 ? 1 : 0)}%` : providerStatus;
            } else status.textContent = job.status;
            card.append(dot);
            if (preview) card.append(preview);
            card.append(copy, status);
            if (job.status === 'running') {
                const progressTrack = document.createElement('div');
                progressTrack.className = `media-job-progress${hasProgress ? '' : ' indeterminate'}`;
                const progressBar = document.createElement('span');
                if (hasProgress) progressBar.style.width = `${numericProgress}%`;
                progressTrack.append(progressBar);
                card.append(progressTrack);
            }
            container.append(card);

            if (job.status === 'completed' && job.result && !displayedMediaJobs.has(job.id)) {
                displayedMediaJobs.add(job.id);
                newlyCompleted = true;
                renderMediaResult(job.result);
                setFeedback(mediaStatus, `${job.operation} generation completed and was added to Gallery.`, 'success');
            }
        });
        if (newlyCompleted) {
            loadGallery();
            refreshDeapiBalance();
        }
    } catch (error) {
        container.innerHTML = '';
        const message = document.createElement('p');
        message.className = 'wide-status error';
        message.textContent = error.message;
        container.append(message);
    }
}

async function refreshDeapiBalance() {
    const button = document.getElementById('deapi-balance');
    button.disabled = true;
    button.textContent = 'Balance: loading…';
    try {
        const payload = await apiJson('/api/desktop/media/balance');
        const amount = Number(payload.balance);
        button.innerHTML = `Balance: $${amount.toFixed(2)} <span>↻</span>`;
        button.title = 'Refresh media balance';
    } catch (error) {
        button.innerHTML = 'Balance unavailable <span>↻</span>';
        button.title = error.message;
    } finally {
        button.disabled = false;
    }
}

document.getElementById('deapi-balance').addEventListener('click', refreshDeapiBalance);

async function loadGallery() {
    const grid = document.getElementById('gallery-grid');
    grid.innerHTML = '<p class="muted">Loading gallery…</p>';
    try {
        const payload = await apiJson('/api/desktop/gallery');
        grid.innerHTML = '';
        if (!payload.items.length) {
            grid.innerHTML = '<p class="muted">Your generated media will appear here.</p>';
            return;
        }
        payload.items.forEach(item => grid.append(buildGalleryCard(item)));
    } catch (error) {
        grid.innerHTML = '';
        const message = document.createElement('p');
        message.className = 'wide-status error';
        message.textContent = error.message;
        grid.append(message);
    }
}

function buildGalleryCard(item) {
    const card = document.createElement('article');
    card.className = 'gallery-card';
    const preview = document.createElement('div');
    preview.className = 'gallery-preview';
    let media;
    if (item.kind === 'image') {
        media = document.createElement('img');
        media.alt = item.prompt || 'Petey generation';
        media.loading = 'lazy';
    } else if (item.kind === 'video') {
        media = document.createElement('video');
        media.controls = true;
        media.preload = 'metadata';
        media.playsInline = true;
    } else {
        media = document.createElement('audio');
        media.controls = true;
        media.preload = 'metadata';
    }
    media.src = item.kind === 'video' && item.preview_url ? item.preview_url : item.media_url;
    preview.append(media);

    const details = document.createElement('div');
    details.className = 'gallery-details';
    const title = document.createElement('strong');
    title.textContent = item.operation;
    const date = document.createElement('small');
    date.textContent = new Date(item.created_at).toLocaleString();
    const prompt = document.createElement('div');
    prompt.className = 'gallery-prompt';
    prompt.textContent = item.prompt || 'No prompt';
    const actions = document.createElement('div');
    actions.className = 'gallery-actions';
    const open = document.createElement('a');
    open.href = item.media_url;
    open.target = '_blank';
    open.rel = 'noopener';
    open.textContent = 'Open';
    open.addEventListener('click', async event => {
        if (!window.pywebview?.api?.open_gallery_item || !item.local_filename) return;
        event.preventDefault();
        const result = await window.pywebview.api.open_gallery_item(item.id);
        if (!result?.ok && !result?.cancelled) {
            window.alert(result?.error || 'Could not open this gallery item.');
        }
    });
    actions.append(open);
    if (item.local_filename) {
        const download = document.createElement('a');
        download.href = `${item.media_url}?download=1`;
        download.download = '';
        download.textContent = 'Download';
        download.addEventListener('click', async event => {
            if (!window.pywebview?.api?.download_gallery_item) return;
            event.preventDefault();
            const result = await window.pywebview.api.download_gallery_item(item.id);
            if (!result?.ok && !result?.cancelled) {
                window.alert(result?.error || 'Could not save this gallery item.');
            }
        });
        actions.append(download);
    }
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = 'Delete';
    remove.addEventListener('click', () => deleteGalleryItem(item.id));
    actions.append(remove);
    details.append(title, date, prompt, actions);
    card.append(preview, details);
    return card;
}

async function deleteGalleryItem(itemId) {
    if (!window.confirm('Delete this generated item from Petey’s local gallery?')) return;
    try {
        await apiJson(`/api/desktop/gallery/${encodeURIComponent(itemId)}`, {method: 'DELETE'});
        await loadGallery();
    } catch (error) {
        window.alert(error.message);
    }
}

document.getElementById('refresh-gallery').addEventListener('click', loadGallery);

function activeWorkspace() {
    return workspaces.find(item => item.id === activeWorkspaceId);
}

function renderWorkspacePicker() {
    const select = document.getElementById('workspace-select');
    select.innerHTML = '';
    if (!workspaces.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No approved folders';
        select.append(option);
    } else {
        workspaces.forEach(workspace => {
            const option = document.createElement('option');
            option.value = workspace.id;
            option.textContent = `${workspace.name} — ${workspace.path}`;
            select.append(option);
        });
        if (!activeWorkspace()) activeWorkspaceId = workspaces[0].id;
        select.value = activeWorkspaceId;
    }
    document.getElementById('workspace-empty').hidden = Boolean(activeWorkspace());
    document.getElementById('workspace-ide').hidden = !activeWorkspace();
    document.getElementById('remove-workspace').disabled = !activeWorkspace();
}

async function loadWorkspaces() {
    try {
        const payload = await apiJson('/api/desktop/workspaces');
        workspaces = payload.workspaces || [];
        activeWorkspaceId = payload.active_workspace_id || '';
        workspaceLoaded = true;
        renderWorkspacePicker();
        if (activeWorkspace()) await loadWorkspaceDirectory('');
    } catch (error) {
        setFeedback(document.getElementById('editor-status'), error.message, 'error');
    }
}

async function approveWorkspacePath(path) {
    const payload = await apiJson('/api/desktop/workspaces', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({path}),
    });
    workspaces = payload.workspaces;
    activeWorkspaceId = payload.active_workspace_id;
    workspaceDirectory = '';
    renderWorkspacePicker();
    document.getElementById('workspace-manual').hidden = true;
    await loadWorkspaceDirectory('');
}

document.getElementById('add-workspace').addEventListener('click', async () => {
    try {
        if (window.pywebview?.api?.choose_workspace_folder) {
            const path = await window.pywebview.api.choose_workspace_folder();
            if (path) await approveWorkspacePath(path);
        } else {
            document.getElementById('workspace-manual').hidden = false;
            document.getElementById('workspace-path').focus();
        }
    } catch (error) {
        window.alert(error.message || String(error));
    }
});

document.getElementById('approve-workspace-path').addEventListener('click', async () => {
    try {
        await approveWorkspacePath(document.getElementById('workspace-path').value.trim());
        document.getElementById('workspace-path').value = '';
    } catch (error) {
        window.alert(error.message);
    }
});
document.getElementById('cancel-workspace-path').addEventListener('click', () => {
    document.getElementById('workspace-manual').hidden = true;
});

document.getElementById('workspace-select').addEventListener('change', async event => {
    activeWorkspaceId = event.target.value;
    if (!activeWorkspaceId) return;
    await apiJson(`/api/desktop/workspaces/${encodeURIComponent(activeWorkspaceId)}/select`, {method: 'PUT'});
    clearWorkspaceEditor();
    await loadWorkspaceDirectory('');
});

document.getElementById('remove-workspace').addEventListener('click', async () => {
    const workspace = activeWorkspace();
    if (!workspace || !window.confirm(`Remove “${workspace.path}” from Petey’s approved folders? No files will be deleted.`)) return;
    const payload = await apiJson(`/api/desktop/workspaces/${encodeURIComponent(workspace.id)}`, {method: 'DELETE'});
    workspaces = payload.workspaces;
    activeWorkspaceId = payload.active_workspace_id;
    clearWorkspaceEditor();
    renderWorkspacePicker();
    if (activeWorkspace()) await loadWorkspaceDirectory('');
});

async function loadWorkspaceDirectory(path = '') {
    const query = new URLSearchParams({workspace_id: activeWorkspaceId, path});
    const payload = await apiJson(`/api/desktop/workspace/tree?${query}`);
    workspaceDirectory = payload.path === '.' ? '' : payload.path;
    document.getElementById('workspace-directory').textContent = `/${workspaceDirectory}`;
    const files = document.getElementById('workspace-files');
    files.innerHTML = '';
    payload.entries.forEach(entry => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `workspace-file ${entry.type}`;
        button.textContent = entry.name;
        button.title = entry.path;
        button.addEventListener('click', () => entry.type === 'directory'
            ? loadWorkspaceDirectory(entry.path) : openWorkspaceFile(entry.path));
        files.append(button);
    });
    if (!payload.entries.length) files.innerHTML = '<p class="muted">This folder is empty.</p>';
}

document.getElementById('workspace-up').addEventListener('click', () => {
    const pieces = workspaceDirectory.split('/').filter(Boolean);
    pieces.pop();
    loadWorkspaceDirectory(pieces.join('/'));
});
document.getElementById('refresh-workspace').addEventListener('click', () => loadWorkspaceDirectory(workspaceDirectory));

async function openWorkspaceFile(path) {
    const query = new URLSearchParams({workspace_id: activeWorkspaceId, path});
    try {
        const file = await apiJson(`/api/desktop/workspace/file?${query}`);
        document.getElementById('editor-path').value = file.path;
        document.getElementById('workspace-editor').value = file.content;
        editorSha256 = file.sha256;
        setFeedback(document.getElementById('editor-status'), `Opened ${file.path}`);
    } catch (error) {
        setFeedback(document.getElementById('editor-status'), error.message, 'error');
    }
}

function clearWorkspaceEditor() {
    document.getElementById('editor-path').value = '';
    document.getElementById('workspace-editor').value = '';
    editorSha256 = null;
    setFeedback(document.getElementById('editor-status'), '');
}

document.getElementById('new-workspace-file').addEventListener('click', () => {
    clearWorkspaceEditor();
    document.getElementById('editor-path').value = workspaceDirectory ? `${workspaceDirectory}/` : '';
    document.getElementById('editor-path').focus();
});

document.getElementById('save-workspace-file').addEventListener('click', async () => {
    const feedback = document.getElementById('editor-status');
    const path = document.getElementById('editor-path').value.trim();
    if (!path) return setFeedback(feedback, 'Enter a relative file path.', 'error');
    try {
        const payload = await apiJson('/api/desktop/workspace/file', {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
                workspace_id: activeWorkspaceId, path,
                content: document.getElementById('workspace-editor').value,
                expected_sha256: editorSha256,
            }),
        });
        editorSha256 = payload.file.sha256;
        document.getElementById('editor-path').value = payload.file.path;
        setFeedback(feedback, `Saved ${payload.file.path}`, 'success');
        await loadWorkspaceDirectory(workspaceDirectory);
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
});

document.getElementById('workspace-editor').addEventListener('keydown', event => {
    if (event.key === 'Tab') {
        event.preventDefault();
        const editor = event.target;
        const start = editor.selectionStart;
        editor.setRangeText('    ', start, editor.selectionEnd, 'end');
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault();
        document.getElementById('save-workspace-file').click();
    }
});

const workspaceProposals = new Map();

function addWorkspaceProposal(proposal) {
    workspaceProposals.set(proposal.id, proposal);
    renderWorkspaceProposals();
}

function renderWorkspaceProposals() {
    const container = document.getElementById('workspace-proposals');
    container.innerHTML = '';
    if (!workspaceProposals.size) {
        container.innerHTML = '<p class="muted">No pending proposals.</p>';
        return;
    }
    workspaceProposals.forEach(proposal => {
        const card = document.createElement('article');
        card.className = 'workspace-proposal';
        const title = document.createElement('strong');
        title.textContent = proposal.type === 'write_file' ? `Edit ${proposal.path}` : 'Run command';
        const detail = document.createElement('small');
        detail.textContent = proposal.type === 'write_file' ? 'Review the complete diff below.' : `${proposal.command}  (cwd: /${proposal.cwd || ''})`;
        card.append(title, detail);
        if (proposal.type === 'write_file') {
            const diff = document.createElement('pre');
            diff.textContent = proposal.diff;
            card.append(diff);
        }
        const actions = document.createElement('div');
        actions.className = 'proposal-actions';
        const approve = document.createElement('button');
        approve.className = 'primary-button';
        approve.type = 'button';
        approve.textContent = proposal.type === 'write_file' ? 'Apply edit' : 'Approve & run';
        approve.addEventListener('click', () => approveWorkspaceProposal(proposal.id, approve));
        const reject = document.createElement('button');
        reject.className = 'secondary-button';
        reject.type = 'button';
        reject.textContent = 'Reject';
        reject.addEventListener('click', () => rejectWorkspaceProposal(proposal.id));
        actions.append(approve, reject);
        card.append(actions);
        container.append(card);
    });
}

async function approveWorkspaceProposal(id, button) {
    button.disabled = true;
    try {
        const payload = await apiJson(`/api/desktop/workspace/proposals/${encodeURIComponent(id)}/approve`, {method: 'POST'});
        workspaceProposals.delete(id);
        renderWorkspaceProposals();
        if (payload.type === 'write_file') {
            await loadWorkspaceDirectory(workspaceDirectory);
            await openWorkspaceFile(payload.file.path);
        } else {
            const run = payload.run;
            document.getElementById('workspace-console').textContent = `$ ${run.command}\n${run.output || ''}\n[exit ${run.exit_code ?? 'timeout'} · ${run.duration_seconds}s]`;
        }
    } catch (error) {
        button.disabled = false;
        window.alert(error.message);
    }
}

async function rejectWorkspaceProposal(id) {
    try {
        await apiJson(`/api/desktop/workspace/proposals/${encodeURIComponent(id)}`, {method: 'DELETE'});
        workspaceProposals.delete(id);
        renderWorkspaceProposals();
    } catch (error) {
        window.alert(error.message);
    }
}

document.getElementById('review-workspace-command').addEventListener('click', async () => {
    try {
        const payload = await apiJson('/api/desktop/workspace/command', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
                workspace_id: activeWorkspaceId,
                command: document.getElementById('workspace-command').value,
                cwd: workspaceDirectory,
            }),
        });
        addWorkspaceProposal(payload.proposal);
    } catch (error) {
        window.alert(error.message);
    }
});

document.getElementById('ask-workspace-agent').addEventListener('click', async () => {
    const button = document.getElementById('ask-workspace-agent');
    const feedback = document.getElementById('workspace-agent-status');
    button.disabled = true;
    setFeedback(feedback, 'Petey is preparing reviewable proposals…');
    try {
        const payload = await apiJson('/api/desktop/workspace/agent', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
                workspace_id: activeWorkspaceId,
                instruction: document.getElementById('workspace-agent-prompt').value,
                selected_path: document.getElementById('editor-path').value.trim(),
            }),
        });
        payload.proposals.forEach(addWorkspaceProposal);
        const suffix = payload.errors?.length ? ` Some actions were rejected: ${payload.errors.join(' ')}` : '';
        setFeedback(feedback, `${payload.reply}${suffix}`, payload.proposals.length ? 'success' : '');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

document.getElementById('clear-workspace-console').addEventListener('click', () => {
    document.getElementById('workspace-console').textContent = '';
});

const requestedView = window.location.hash.replace('#', '');
const knownViews = ['chat', 'media', 'gallery', 'workspace', 'settings', 'personality', 'knowledge', 'memory'];
if (knownViews.includes(requestedView)) showView(requestedView);
