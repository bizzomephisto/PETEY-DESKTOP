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
let speechSettingsLoaded = false;
let speechConfiguration = null;
let voiceInputSettingsLoaded = false;
let voiceInputConfiguration = {mode: 'disabled', provider: 'gemini', model: 'gemini-3.5-transcribe', wake_word: 'Petey', device_id: '', sensitivity: 'normal'};
let microphoneStream = null;
let microphoneContext = null;
let microphoneProcessor = null;
let microphoneCapture = [];
let microphonePreRoll = [];
let microphoneCapturing = false;
let microphoneLastVoiceAt = 0;
let microphoneCaptureStartedAt = 0;
let voiceInputRunning = false;
let voiceInputBusy = false;
let voiceInputPlaybackBlocked = false;
let microphoneTestActive = false;
let pushToTalkHeld = false;
let wakeWordArmedUntil = 0;
let keyboardPushToTalkActive = false;
let visualAudioEnergy = 0;
let lastPeteyCaption = '';
let visualCaptionTimer = null;
let nativeVisualFullscreen = false;
let geminiSpeechModels = [];
let geminiSpeechVoices = [];
let memoryProviderLoaded = false;
let memoryProviderConfiguration = null;
let mediaCatalogLoaded = false;
let mediaSelectedModels = {};
let mediaPollTimer = null;
const displayedMediaJobs = new Set();
let conversations = [];
let activeConversationId = '';
let temporaryHistory = [];
let preferences = {always_on_top: false, sidebar_collapsed: false, ui_scale: 1, visual_mode: false, visual_style: 'neural_core'};
let workspaces = [];
let activeWorkspaceId = '';
let workspaceDirectory = '';
let editorSha256 = null;
let workspaceLoaded = false;
let activeChatAudio = null;
let activeSpeechButton = null;
let activeSpeechCancel = null;

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
        if (role === 'assistant' && speechConfiguration?.provider !== 'disabled') {
            const speakButton = document.createElement('button');
            speakButton.type = 'button';
            speakButton.className = 'speak-message';
            speakButton.textContent = 'Speak';
            speakButton.title = 'Read this reply aloud';
            speakButton.addEventListener('click', () => speakChatText(text, speakButton));
            meta.append(speakButton);
        }
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
    if (role === 'assistant' && !options.typing && text) setLastPeteyCaption(text);
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
        speechConfiguration = bootstrap.speech || {provider: 'deapi', auto_speak: false};
        voiceInputConfiguration = {...voiceInputConfiguration, ...(bootstrap.voice_input || {})};
        workspaces = bootstrap.workspaces || [];
        activeWorkspaceId = bootstrap.active_workspace_id || '';
        applyPreferences();
        renderConversations();
        await loadConversationMessages();
        configureVoiceInputUI();
        if (['always_on', 'wake_word'].includes(voiceInputConfiguration.mode)) {
            window.setTimeout(() => startContinuousVoiceInput(), 250);
        }
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
        if (speechConfiguration?.provider !== 'disabled' && speechConfiguration?.auto_speak && payload.text) {
            speakChatText(payload.text);
        }
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
    const visualMode = Boolean(preferences.visual_mode);
    document.getElementById('view-chat').classList.toggle('visual-mode', visualMode);
    messages.hidden = visualMode;
    document.getElementById('visual-chat').hidden = !visualMode;
    document.getElementById('visual-mode-toggle').classList.toggle('active', visualMode);
    document.getElementById('visual-mode-toggle').textContent = visualMode ? 'Show chat' : 'Visual mode';
    const styleSelect = document.getElementById('visual-style-select');
    styleSelect.hidden = !visualMode;
    styleSelect.value = preferences.visual_style || 'neural_core';
    document.getElementById('visual-fullscreen').hidden = !visualMode;
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
document.getElementById('visual-mode-toggle').addEventListener('click', () => {
    savePreferences({visual_mode: !preferences.visual_mode});
});
document.getElementById('visual-style-select').addEventListener('change', event => {
    savePreferences({visual_style: event.target.value});
});

function captionExcerpt(text, wordLimit = 28) {
    const words = String(text || '').trim().split(/\s+/).filter(Boolean);
    return words.slice(Math.max(0, words.length - wordLimit)).join(' ');
}

function setLastPeteyCaption(text) {
    lastPeteyCaption = String(text || '').trim();
    if (!visualCaptionTimer) {
        document.getElementById('visual-caption').textContent = captionExcerpt(lastPeteyCaption);
    }
}

function startVisualCaption(text) {
    window.clearInterval(visualCaptionTimer);
    const words = String(text || '').trim().split(/\s+/).filter(Boolean);
    const caption = document.getElementById('visual-caption');
    lastPeteyCaption = String(text || '').trim();
    let cursor = 1;
    const render = () => {
        const start = Math.max(0, cursor - 16);
        caption.textContent = words.slice(start, cursor).join(' ');
        cursor = Math.min(words.length, cursor + 1);
    };
    render();
    visualCaptionTimer = window.setInterval(render, 330);
}

function finishVisualCaption() {
    window.clearInterval(visualCaptionTimer);
    visualCaptionTimer = null;
    document.getElementById('visual-caption').textContent = captionExcerpt(lastPeteyCaption);
}

async function toggleVisualFullscreen() {
    if (!preferences.visual_mode) return;
    const visual = document.getElementById('visual-chat');
    if (document.fullscreenElement) {
        await document.exitFullscreen();
        return;
    }
    if (nativeVisualFullscreen && window.pywebview?.api?.toggle_fullscreen) {
        const result = await window.pywebview.api.toggle_fullscreen();
        nativeVisualFullscreen = Boolean(result?.fullscreen);
        document.body.classList.toggle('native-visual-fullscreen', nativeVisualFullscreen);
        return;
    }
    try {
        if (!visual.requestFullscreen) throw new Error('Fullscreen API unavailable');
        await visual.requestFullscreen();
    } catch (_error) {
        if (!window.pywebview?.api?.toggle_fullscreen) {
            setVoiceInputStatus('Full screen is unavailable in this browser.');
            return;
        }
        const result = await window.pywebview.api.toggle_fullscreen();
        nativeVisualFullscreen = Boolean(result?.fullscreen);
        document.body.classList.toggle('native-visual-fullscreen', nativeVisualFullscreen);
    }
}

document.getElementById('visual-fullscreen').addEventListener('click', toggleVisualFullscreen);
document.addEventListener('fullscreenchange', () => {
    document.getElementById('visual-fullscreen').textContent = document.fullscreenElement
        ? 'Exit full screen' : '⛶ Full screen';
});
document.addEventListener('keydown', event => {
    if (event.key === 'F11' && preferences.visual_mode) {
        event.preventDefault();
        toggleVisualFullscreen();
    } else if (event.key === 'Escape' && nativeVisualFullscreen) {
        event.preventDefault();
        toggleVisualFullscreen();
    }
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
    if (view === 'personality' && !speechSettingsLoaded) loadSpeechSettings();
    if (view === 'settings' && !aiProviderLoaded) loadAIProvider();
    if (view === 'settings' && !voiceInputSettingsLoaded) loadVoiceInputSettings();
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

const voiceInputButton = document.getElementById('voice-input-button');
const voiceInputModeSelect = document.getElementById('voice-input-mode');

function setVoiceInputStatus(message) {
    document.getElementById('voice-input-status').textContent = message;
}

function configureVoiceInputUI() {
    const mode = voiceInputConfiguration?.mode || 'disabled';
    voiceInputButton.hidden = mode === 'disabled';
    voiceInputButton.classList.toggle('listening', voiceInputRunning && !microphoneCapturing);
    voiceInputButton.classList.toggle('recording', microphoneCapturing);
    voiceInputButton.classList.toggle('processing', voiceInputBusy);
    voiceInputButton.title = {
        push_to_talk: 'Hold to talk to Petey',
        always_on: voiceInputRunning ? 'Microphone is listening; click to stop' : 'Click to start microphone',
        wake_word: voiceInputRunning ? `Listening for ${voiceInputConfiguration.wake_word || 'Petey'}; click to stop` : 'Click to start wake-name listening',
    }[mode] || 'Microphone input';
    if (mode === 'disabled') {
        setVoiceInputStatus('Enter to send · Shift+Enter for a new line');
    } else if (voiceInputBusy) {
        setVoiceInputStatus('Transcribing…');
    } else if (microphoneCapturing) {
        setVoiceInputStatus(mode === 'push_to_talk' ? 'Recording · release to send' : 'Listening to you…');
    } else if (mode === 'push_to_talk') {
        setVoiceInputStatus('Hold the mic or Space to talk · Enter to send');
    } else if (voiceInputRunning && mode === 'wake_word') {
        setVoiceInputStatus(`Listening for “${voiceInputConfiguration.wake_word || 'Petey'}”…`);
    } else if (voiceInputRunning) {
        setVoiceInputStatus('Mic always on · listening for speech');
    } else {
        setVoiceInputStatus('Click the mic to begin listening');
    }
}

function configureVoiceInputSettings() {
    const mode = voiceInputModeSelect.value;
    const enabled = mode !== 'disabled';
    document.getElementById('voice-input-model').disabled = !enabled;
    document.getElementById('voice-input-device').disabled = !enabled;
    document.getElementById('voice-input-sensitivity').disabled = !enabled;
    document.getElementById('voice-wake-word-field').hidden = mode !== 'wake_word';
    document.getElementById('voice-input-badge').textContent = {
        disabled: 'Off', push_to_talk: 'Push to talk', always_on: 'Always on', wake_word: 'Wake name',
    }[mode];
    document.getElementById('voice-input-note').textContent = {
        disabled: 'Audio stays off until microphone input is enabled.',
        push_to_talk: 'Hold the mic button or Space outside the message box, speak, then release to transcribe and send.',
        always_on: 'Petey detects speech and sends each utterance after a short silence.',
        wake_word: `Petey sends an utterance only when it contains “${document.getElementById('voice-wake-word').value.trim() || 'Petey'}”.`,
    }[mode];
}

async function loadVoiceInputSettings() {
    const feedback = document.getElementById('voice-input-settings-status');
    try {
        const payload = await apiJson('/api/desktop/voice-input');
        voiceInputConfiguration = {...voiceInputConfiguration, ...payload.configuration};
        voiceInputModeSelect.value = voiceInputConfiguration.mode;
        const models = payload.models?.length ? payload.models : ['gemini-3.5-transcribe'];
        fillSelect(document.getElementById('voice-input-model'), models, voiceInputConfiguration.model);
        document.getElementById('voice-wake-word').value = voiceInputConfiguration.wake_word || 'Petey';
        document.getElementById('voice-input-sensitivity').value = voiceInputConfiguration.sensitivity || 'normal';
        await refreshMicrophoneDevices();
        configureVoiceInputSettings();
        configureVoiceInputUI();
        voiceInputSettingsLoaded = true;
        if (voiceInputConfiguration.mode !== 'disabled' && !payload.gemini_has_api_key) {
            setFeedback(feedback, 'Add a Gemini API key in AI provider settings before using the microphone.', 'error');
        }
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
}

voiceInputModeSelect.addEventListener('change', configureVoiceInputSettings);
document.getElementById('voice-wake-word').addEventListener('input', configureVoiceInputSettings);
document.getElementById('save-voice-input').addEventListener('click', async () => {
    const feedback = document.getElementById('voice-input-settings-status');
    const button = document.getElementById('save-voice-input');
    button.disabled = true;
    try {
        const payload = await apiJson('/api/desktop/voice-input', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                mode: voiceInputModeSelect.value,
                provider: 'gemini',
                model: document.getElementById('voice-input-model').value,
                wake_word: document.getElementById('voice-wake-word').value,
                device_id: document.getElementById('voice-input-device').value,
                sensitivity: document.getElementById('voice-input-sensitivity').value,
            }),
        });
        await stopVoiceInput();
        voiceInputConfiguration = {...voiceInputConfiguration, ...payload.configuration};
        configureVoiceInputSettings();
        configureVoiceInputUI();
        if (['always_on', 'wake_word'].includes(voiceInputConfiguration.mode)) {
            await startContinuousVoiceInput();
        }
        setFeedback(feedback, voiceInputConfiguration.mode === 'disabled' ? 'Microphone input disabled.' : 'Microphone settings saved.', 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

async function refreshMicrophoneDevices() {
    const select = document.getElementById('voice-input-device');
    const selected = select.value || voiceInputConfiguration.device_id || '';
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
        const devices = (await navigator.mediaDevices.enumerateDevices())
            .filter(device => device.kind === 'audioinput');
        select.innerHTML = '';
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = 'System default microphone';
        select.append(defaultOption);
        devices.forEach((device, index) => {
            if (device.deviceId === 'default') return;
            const option = document.createElement('option');
            option.value = device.deviceId;
            option.textContent = device.label || `Microphone ${index + 1}`;
            select.append(option);
        });
        select.value = Array.from(select.options).some(option => option.value === selected) ? selected : '';
    } catch (_error) {
        // System default remains usable when the backend restricts enumeration.
    }
}

async function ensureMicrophone(deviceId = voiceInputConfiguration.device_id || '') {
    if (microphoneStream?.active && microphoneContext) return;
    if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('This desktop backend does not provide microphone capture.');
    }
    const audio = {echoCancellation: true, noiseSuppression: true, autoGainControl: true};
    if (deviceId) audio.deviceId = {exact: deviceId};
    try {
        microphoneStream = await navigator.mediaDevices.getUserMedia({audio, video: false});
    } catch (error) {
        if (!deviceId || !['OverconstrainedError', 'NotFoundError'].includes(error.name)) throw error;
        microphoneStream = await navigator.mediaDevices.getUserMedia({
            audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true},
            video: false,
        });
        setVoiceInputStatus('Saved microphone unavailable; using the system default.');
    }
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) throw new Error('This desktop backend does not provide audio capture.');
    microphoneContext = new AudioContextClass();
    await microphoneContext.resume();
    const source = microphoneContext.createMediaStreamSource(microphoneStream);
    microphoneProcessor = microphoneContext.createScriptProcessor(2048, 1, 1);
    const silentOutput = microphoneContext.createGain();
    silentOutput.gain.value = 0;
    microphoneProcessor.onaudioprocess = handleMicrophoneAudio;
    source.connect(microphoneProcessor);
    microphoneProcessor.connect(silentOutput);
    silentOutput.connect(microphoneContext.destination);
    await refreshMicrophoneDevices();
}

function handleMicrophoneAudio(event) {
    const samples = new Float32Array(event.inputBuffer.getChannelData(0));
    let energy = 0;
    for (let index = 0; index < samples.length; index += 1) energy += samples[index] * samples[index];
    const rms = Math.sqrt(energy / samples.length);
    visualAudioEnergy = Math.max(visualAudioEnergy, Math.min(1, rms * 35));
    document.getElementById('voice-input-meter').style.width = `${Math.min(100, Math.max(1, rms * 900))}%`;
    if (microphoneTestActive) {
        document.getElementById('voice-input-test-status').textContent = rms > .006
            ? 'Input detected — microphone is working.' : 'Listening… speak into the microphone.';
    }
    if (!voiceInputRunning || voiceInputBusy || voiceInputPlaybackBlocked) return;
    const mode = voiceInputConfiguration.mode;
    if (mode === 'push_to_talk') {
        if (microphoneCapturing) microphoneCapture.push(samples);
        return;
    }
    const now = performance.now();
    const threshold = {high: .006, normal: .012, low: .025}[
        voiceInputConfiguration.sensitivity || 'normal'
    ];
    if (!microphoneCapturing) {
        microphonePreRoll.push(samples);
        const preRollLimit = Math.max(2, Math.ceil((microphoneContext.sampleRate * .35) / samples.length));
        if (microphonePreRoll.length > preRollLimit) microphonePreRoll.shift();
        if (rms >= threshold) {
            microphoneCapture = microphonePreRoll.splice(0);
            microphoneCapturing = true;
            microphoneCaptureStartedAt = now;
            microphoneLastVoiceAt = now;
            configureVoiceInputUI();
        }
        return;
    }
    microphoneCapture.push(samples);
    if (rms >= threshold) microphoneLastVoiceAt = now;
    if ((now - microphoneLastVoiceAt > 950 && now - microphoneCaptureStartedAt > 450)
        || now - microphoneCaptureStartedAt > 30000) {
        finishVoiceCapture();
    }
}

function wavBlob(chunks, sampleRate) {
    const frameCount = chunks.reduce((total, chunk) => total + chunk.length, 0);
    const buffer = new ArrayBuffer(44 + frameCount * 2);
    const view = new DataView(buffer);
    const writeText = (offset, value) => Array.from(value).forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
    writeText(0, 'RIFF');
    view.setUint32(4, 36 + frameCount * 2, true);
    writeText(8, 'WAVE');
    writeText(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeText(36, 'data');
    view.setUint32(40, frameCount * 2, true);
    let offset = 44;
    chunks.forEach(chunk => chunk.forEach(sample => {
        const clipped = Math.max(-1, Math.min(1, sample));
        view.setInt16(offset, clipped < 0 ? clipped * 32768 : clipped * 32767, true);
        offset += 2;
    }));
    return new Blob([buffer], {type: 'audio/wav'});
}

function beginVoiceCapture() {
    microphoneCapture = [];
    microphonePreRoll = [];
    microphoneCapturing = true;
    microphoneCaptureStartedAt = performance.now();
    microphoneLastVoiceAt = microphoneCaptureStartedAt;
    configureVoiceInputUI();
}

async function finishVoiceCapture(discard = false) {
    if (!microphoneCapturing) return;
    microphoneCapturing = false;
    const chunks = microphoneCapture;
    microphoneCapture = [];
    microphonePreRoll = [];
    configureVoiceInputUI();
    if (discard || !microphoneContext) return;
    const frames = chunks.reduce((total, chunk) => total + chunk.length, 0);
    if (frames < microphoneContext.sampleRate * .18) {
        setVoiceInputStatus('No speech detected.');
        return;
    }
    await transcribeVoiceInput(wavBlob(chunks, microphoneContext.sampleRate));
}

async function transcribeVoiceInput(audio) {
    voiceInputBusy = true;
    let failure = '';
    configureVoiceInputUI();
    try {
        const form = new FormData();
        form.append('audio', audio, 'petey-microphone.wav');
        const response = await fetch('/api/desktop/voice-input/transcribe', {method: 'POST', body: form});
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || `Transcription failed (${response.status}).`);
        handleVoiceTranscript(String(payload.transcript || '').trim());
    } catch (error) {
        failure = `Microphone: ${error.message}`;
    } finally {
        voiceInputBusy = false;
        configureVoiceInputUI();
        if (failure) setVoiceInputStatus(failure);
    }
}

function handleVoiceTranscript(transcript) {
    if (!transcript) return;
    let command = transcript;
    if (voiceInputConfiguration.mode === 'wake_word') {
        const wakeWord = voiceInputConfiguration.wake_word || 'Petey';
        const escaped = wakeWord.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const match = transcript.match(new RegExp(`\\b${escaped}\\b[\\s,.:;!?—-]*(.*)$`, 'i'));
        if (match) {
            command = match[1].trim();
            wakeWordArmedUntil = Date.now() + 8000;
            if (!command) {
                setVoiceInputStatus(`Heard “${wakeWord}” · listening for your request…`);
                return;
            }
        } else if (Date.now() < wakeWordArmedUntil) {
            wakeWordArmedUntil = 0;
        } else {
            setVoiceInputStatus(`Ignored speech without “${wakeWord}”.`);
            return;
        }
    }
    const existing = messageInput.value.trim();
    messageInput.value = existing ? `${existing} ${command}` : command;
    messageInput.dispatchEvent(new Event('input'));
    if (!sendButton.disabled) composer.requestSubmit();
    else setVoiceInputStatus('Transcript added to the message box; Petey is still replying.');
}

async function startContinuousVoiceInput() {
    if (!['always_on', 'wake_word'].includes(voiceInputConfiguration.mode)) return;
    try {
        await ensureMicrophone();
        voiceInputRunning = true;
        configureVoiceInputUI();
    } catch (error) {
        voiceInputRunning = false;
        configureVoiceInputUI();
        setVoiceInputStatus(`Microphone unavailable: ${error.message}`);
    }
}

async function stopVoiceInput() {
    voiceInputRunning = false;
    pushToTalkHeld = false;
    microphoneTestActive = false;
    if (microphoneCapturing) await finishVoiceCapture(true);
    if (microphoneProcessor) microphoneProcessor.disconnect();
    microphoneProcessor = null;
    microphoneStream?.getTracks().forEach(track => track.stop());
    microphoneStream = null;
    if (microphoneContext) await microphoneContext.close().catch(() => {});
    microphoneContext = null;
    document.getElementById('voice-input-meter').style.width = '0';
    document.getElementById('test-voice-input').textContent = 'Test microphone';
    configureVoiceInputUI();
}

document.getElementById('test-voice-input').addEventListener('click', async () => {
    const button = document.getElementById('test-voice-input');
    const status = document.getElementById('voice-input-test-status');
    if (microphoneTestActive) {
        await stopVoiceInput();
        status.textContent = 'Microphone test stopped.';
        if (['always_on', 'wake_word'].includes(voiceInputConfiguration.mode)) {
            await startContinuousVoiceInput();
        }
        return;
    }
    button.disabled = true;
    try {
        await stopVoiceInput();
        await ensureMicrophone(document.getElementById('voice-input-device').value);
        microphoneTestActive = true;
        button.textContent = 'Stop test';
        status.textContent = 'Listening… speak into the microphone.';
    } catch (error) {
        status.textContent = `Microphone unavailable: ${error.message}`;
    } finally {
        button.disabled = false;
    }
});

navigator.mediaDevices?.addEventListener?.('devicechange', refreshMicrophoneDevices);

function setVoicePlaybackActive(active) {
    voiceInputPlaybackBlocked = Boolean(active);
    if (!active) finishVisualCaption();
    if (active && microphoneCapturing && voiceInputConfiguration.mode !== 'push_to_talk') {
        finishVoiceCapture(true);
    }
}

voiceInputButton.addEventListener('click', async () => {
    if (voiceInputConfiguration.mode === 'push_to_talk') return;
    if (voiceInputRunning) await stopVoiceInput();
    else await startContinuousVoiceInput();
});

async function beginPushToTalk(event) {
    if (voiceInputConfiguration.mode !== 'push_to_talk' || voiceInputBusy) return;
    event.preventDefault();
    pushToTalkHeld = true;
    try {
        await ensureMicrophone();
        if (!pushToTalkHeld) return;
        voiceInputRunning = true;
        beginVoiceCapture();
        if (Number.isInteger(event.pointerId)) voiceInputButton.setPointerCapture?.(event.pointerId);
    } catch (error) {
        setVoiceInputStatus(`Microphone unavailable: ${error.message}`);
    }
}

async function endPushToTalk(event) {
    if (voiceInputConfiguration.mode !== 'push_to_talk' || !pushToTalkHeld) return;
    event.preventDefault();
    pushToTalkHeld = false;
    voiceInputRunning = false;
    microphoneStream?.getTracks().forEach(track => track.stop());
    await finishVoiceCapture();
    await stopVoiceInput();
}

voiceInputButton.addEventListener('pointerdown', beginPushToTalk);
voiceInputButton.addEventListener('pointerup', endPushToTalk);
voiceInputButton.addEventListener('pointercancel', endPushToTalk);
voiceInputButton.addEventListener('keydown', event => {
    if (event.repeat || ![' ', 'Enter'].includes(event.key)) return;
    beginPushToTalk(event);
});
voiceInputButton.addEventListener('keyup', event => {
    if (![' ', 'Enter'].includes(event.key)) return;
    endPushToTalk(event);
});

document.addEventListener('keydown', event => {
    if (event.code !== 'Space' || event.repeat || voiceInputConfiguration.mode !== 'push_to_talk') return;
    if (!document.getElementById('view-chat').classList.contains('active-view')) return;
    if (event.target === voiceInputButton) return;
    if (event.target.closest?.('input, textarea, select, [contenteditable="true"]')) return;
    if (document.querySelector('dialog[open]')) return;
    keyboardPushToTalkActive = true;
    beginPushToTalk(event);
});

document.addEventListener('keyup', event => {
    if (event.code !== 'Space' || !keyboardPushToTalkActive) return;
    keyboardPushToTalkActive = false;
    endPushToTalk(event);
});

const speechProviderSelect = document.getElementById('speech-provider');
const builtInGeminiSpeechModels = Array.from(
    document.getElementById('speech-gemini-model').options,
    option => option.value,
);
const builtInGeminiSpeechVoices = Array.from(
    document.getElementById('speech-gemini-voice').options,
    option => ({
        name: option.value,
        description: option.textContent.split('—').slice(1).join('—').trim(),
    }),
);

function fillSelect(select, items, selectedValue, labelFor) {
    select.innerHTML = '';
    items.forEach(item => {
        const option = document.createElement('option');
        option.value = typeof item === 'string' ? item : item.name;
        option.textContent = labelFor ? labelFor(item) : option.value;
        select.append(option);
    });
    select.value = selectedValue;
}

function fillSpeechForm(configuration) {
    if (!configuration) return;
    speechProviderSelect.value = configuration.provider || 'deapi';
    document.getElementById('speech-gemini-model').value = configuration.gemini_model || 'gemini-3.1-flash-tts-preview';
    document.getElementById('speech-gemini-voice').value = configuration.gemini_voice || 'Kore';
    document.getElementById('speech-deapi-voice').value = configuration.deapi_voice || 'af_sky';
    document.getElementById('speech-style').value = configuration.style || '';
    document.getElementById('speech-consistent-voice').checked = configuration.consistent_voice !== false;
    document.getElementById('speech-auto-speak').checked = Boolean(configuration.auto_speak);
    configureSpeechSettings();
}

function readSpeechForm() {
    return {
        provider: speechProviderSelect.value,
        gemini_model: document.getElementById('speech-gemini-model').value,
        gemini_voice: document.getElementById('speech-gemini-voice').value,
        deapi_voice: document.getElementById('speech-deapi-voice').value,
        style: document.getElementById('speech-style').value,
        consistent_voice: document.getElementById('speech-consistent-voice').checked,
        auto_speak: document.getElementById('speech-auto-speak').checked,
    };
}

function configureSpeechSettings() {
    const provider = speechProviderSelect.value;
    const gemini = provider === 'gemini';
    document.getElementById('speech-gemini-model-field').hidden = !gemini;
    document.getElementById('speech-gemini-voice-field').hidden = !gemini;
    document.getElementById('speech-style-field').hidden = !gemini;
    document.getElementById('speech-consistent-voice-row').hidden = !gemini;
    document.getElementById('speech-deapi-voice-field').hidden = provider !== 'deapi';
    document.getElementById('speech-auto-speak').disabled = provider === 'disabled';
    if (provider === 'disabled') document.getElementById('speech-auto-speak').checked = false;
    document.getElementById('speech-provider-badge').textContent = {
        deapi: 'Media provider', gemini: 'Gemini', disabled: 'Disabled',
    }[provider];
    document.getElementById('speech-provider-note').textContent = provider === 'gemini'
        ? 'Gemini generates 24 kHz speech and follows natural-language directions for style, accent, pace, and tone.'
        : provider === 'disabled'
            ? 'Text to speech is unavailable on the Media page while disabled.'
            : 'Speech uses the existing media service and its available speech models.';
}

async function loadSpeechSettings() {
    const feedback = document.getElementById('speech-settings-status');
    try {
        const payload = await apiJson('/api/desktop/speech');
        speechConfiguration = payload.configuration;
        geminiSpeechModels = payload.gemini_models?.length
            ? payload.gemini_models : builtInGeminiSpeechModels;
        geminiSpeechVoices = payload.gemini_voices?.length
            ? payload.gemini_voices : builtInGeminiSpeechVoices;
        fillSelect(document.getElementById('speech-gemini-model'), geminiSpeechModels, speechConfiguration.gemini_model);
        fillSelect(
            document.getElementById('speech-gemini-voice'), geminiSpeechVoices,
            speechConfiguration.gemini_voice,
            voice => `${voice.name} — ${voice.description}`,
        );
        fillSpeechForm(speechConfiguration);
        speechSettingsLoaded = true;
        if (speechConfiguration.provider === 'gemini' && !payload.gemini_has_api_key) {
            setFeedback(feedback, 'Add a Gemini API key in AI provider settings before generating speech.', 'error');
        }
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
}

speechProviderSelect.addEventListener('change', configureSpeechSettings);
document.getElementById('save-speech-settings').addEventListener('click', async () => {
    const feedback = document.getElementById('speech-settings-status');
    const button = document.getElementById('save-speech-settings');
    button.disabled = true;
    try {
        const payload = await apiJson('/api/desktop/speech', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(readSpeechForm()),
        });
        speechConfiguration = payload.configuration;
        speechSettingsLoaded = true;
        mediaCatalogLoaded = false;
        configureSpeechSettings();
        setFeedback(feedback, speechConfiguration.provider === 'disabled' ? 'Speech generation disabled.' : 'Speech settings saved.', 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

function resetSpeechButton(button) {
    if (!button) return;
    button.disabled = false;
    button.textContent = 'Speak';
    button.classList.remove('speaking');
}

async function speakChatText(text, button = null) {
    if (button?.classList.contains('speaking') && activeSpeechCancel) {
        activeSpeechCancel();
        activeSpeechCancel = null;
        resetSpeechButton(button);
        return;
    }
    if (activeSpeechCancel) activeSpeechCancel();
    activeSpeechCancel = null;
    resetSpeechButton(activeSpeechButton);
    activeSpeechButton = button;
    if (button) {
        button.disabled = false;
        button.textContent = 'Preparing…';
        button.classList.add('speaking');
    }
    try {
        if (
            speechConfiguration?.provider === 'gemini'
            && String(speechConfiguration.gemini_model || '').startsWith('gemini-3.1-')
        ) {
            startVisualCaption(text);
            setVoicePlaybackActive(true);
            try {
                await playGeminiSpeechStream(text, button);
            } finally {
                setVoicePlaybackActive(false);
            }
            return;
        }
        const queued = await apiJson('/api/desktop/chat/speech', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text}),
        });
        let job = queued.job;
        for (let attempt = 0; attempt < 300; attempt += 1) {
            if (job.status === 'completed' || job.status === 'failed') break;
            await new Promise(resolve => window.setTimeout(resolve, 1000));
            job = (await apiJson(`/api/desktop/media/jobs/${encodeURIComponent(job.id)}`)).job;
        }
        if (job.status === 'failed') throw new Error(job.error || 'Speech generation failed.');
        if (job.status !== 'completed') throw new Error('Speech generation timed out.');
        const source = job.result?.result_url
            || `/api/desktop/media/jobs/${encodeURIComponent(job.id)}/file`;
        const audio = new Audio(source);
        activeChatAudio = audio;
        activeSpeechCancel = () => {
            audio.pause();
            activeChatAudio = null;
            setVoicePlaybackActive(false);
        };
        if (button) {
            button.disabled = false;
            button.textContent = 'Stop';
            button.classList.add('speaking');
        }
        audio.addEventListener('ended', () => {
            if (activeChatAudio === audio) activeChatAudio = null;
            activeSpeechCancel = null;
            setVoicePlaybackActive(false);
            if (activeSpeechButton === button) activeSpeechButton = null;
            resetSpeechButton(button);
        }, {once: true});
        startVisualCaption(text);
        setVoicePlaybackActive(true);
        await audio.play();
    } catch (error) {
        if (activeSpeechCancel) activeSpeechCancel();
        setVoicePlaybackActive(false);
        resetSpeechButton(button);
        if (activeSpeechButton === button) activeSpeechButton = null;
        activeSpeechCancel = null;
        if (error.name !== 'AbortError') statusText.textContent = `Speech: ${error.message}`;
    }
}

async function playGeminiSpeechStream(text, button) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) throw new Error('Streaming audio is not supported by this desktop backend.');
    const context = new AudioContextClass({sampleRate: 24000});
    const controller = new AbortController();
    const scheduled = new Set();
    let nextStart = 0;
    let receivedAudio = false;
    let streamFinished = false;
    let resolvePlayback;
    const playbackFinished = new Promise(resolve => { resolvePlayback = resolve; });
    const finishIfReady = () => {
        if (streamFinished && scheduled.size === 0) resolvePlayback();
    };
    activeSpeechCancel = () => {
        controller.abort();
        scheduled.forEach(source => {
            try { source.stop(); } catch (_error) { /* already stopped */ }
        });
        scheduled.clear();
        streamFinished = true;
        context.close().catch(() => {});
        setVoicePlaybackActive(false);
        resolvePlayback();
    };
    if (button) {
        button.textContent = 'Stop';
        button.classList.add('speaking');
    }
    await context.resume();
    const response = await fetch('/api/desktop/chat/speech/stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text}),
        signal: controller.signal,
    });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || `Speech request failed (${response.status}).`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = '';

    const schedulePCM = encoded => {
        const binary = window.atob(encoded);
        const byteCount = binary.length - (binary.length % 2);
        if (!byteCount) return;
        const pcm = new Float32Array(byteCount / 2);
        for (let index = 0; index < byteCount; index += 2) {
            let sample = binary.charCodeAt(index) | (binary.charCodeAt(index + 1) << 8);
            if (sample >= 0x8000) sample -= 0x10000;
            pcm[index / 2] = sample / 32768;
        }
        let energy = 0;
        for (let index = 0; index < pcm.length; index += 1) energy += pcm[index] * pcm[index];
        visualAudioEnergy = Math.max(
            visualAudioEnergy,
            Math.min(1, Math.sqrt(energy / Math.max(1, pcm.length)) * 5),
        );
        const buffer = context.createBuffer(1, pcm.length, 24000);
        buffer.copyToChannel(pcm, 0);
        const source = context.createBufferSource();
        source.buffer = buffer;
        source.connect(context.destination);
        const startAt = Math.max(context.currentTime + 0.035, nextStart);
        nextStart = startAt + buffer.duration;
        scheduled.add(source);
        source.onended = () => {
            scheduled.delete(source);
            finishIfReady();
        };
        source.start(startAt);
        receivedAudio = true;
    };

    while (true) {
        const {value, done} = await reader.read();
        pending += decoder.decode(value || new Uint8Array(), {stream: !done});
        const lines = pending.split('\n');
        pending = lines.pop() || '';
        for (const line of lines) {
            if (!line.trim()) continue;
            const event = JSON.parse(line);
            if (event.error) throw new Error(event.error);
            if (event.audio) schedulePCM(event.audio);
        }
        if (done) break;
    }
    if (pending.trim()) {
        const event = JSON.parse(pending);
        if (event.error) throw new Error(event.error);
        if (event.audio) schedulePCM(event.audio);
    }
    streamFinished = true;
    if (!receivedAudio) throw new Error('Gemini finished without returning audio.');
    finishIfReady();
    await playbackFinished;
    await context.close().catch(() => {});
    activeSpeechCancel = null;
    if (activeSpeechButton === button) activeSpeechButton = null;
    resetSpeechButton(button);
}

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
    if (persona.speech) fillSpeechForm(persona.speech);
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
        speech: readSpeechForm(),
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
                `Loaded personality and voice from slot ${index + 1} — save personality to activate them.`,
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
        setFeedback(feedback, `Saved the current personality and voice to slot ${slot}.`, 'success');
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
        if (payload.speech) fillSpeechForm(payload.speech);
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
        speechConfiguration = result.speech || speechConfiguration;
        if (result.speech) fillSpeechForm(result.speech);
        mediaCatalogLoaded = false;
        setFeedback(feedback, 'Saved — new chats and Petey’s voice use this persona immediately.', 'success');
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
        const [payload, speechPayload] = await Promise.all([
            apiJson('/api/desktop/media'), apiJson('/api/desktop/speech'),
        ]);
        speechConfiguration = speechPayload.configuration;
        geminiSpeechModels = speechPayload.gemini_models?.length
            ? speechPayload.gemini_models : builtInGeminiSpeechModels;
        geminiSpeechVoices = speechPayload.gemini_voices?.length
            ? speechPayload.gemini_voices : builtInGeminiSpeechVoices;
        speechSettingsLoaded = true;
        mediaSelectedModels = payload.selected_models || {};
        const speechOption = mediaOperation.querySelector('option[value="txt2audio"]');
        speechOption.disabled = speechConfiguration.provider === 'disabled';
        if (speechOption.disabled && mediaOperation.value === 'txt2audio') mediaOperation.value = 'txt2img';
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
    if (config.speech) configureMediaSpeechFields();
    document.getElementById('media-upscale-fields').hidden = !config.upscale;
    setFeedback(mediaStatus, '');
    loadMediaModels(operation);
}

function configureMediaSpeechFields() {
    const gemini = speechConfiguration?.provider === 'gemini';
    const voiceSelect = document.getElementById('media-voice');
    if (gemini) {
        fillSelect(
            voiceSelect, geminiSpeechVoices, speechConfiguration.gemini_voice,
            voice => `${voice.name} — ${voice.description}`,
        );
    } else {
        const voices = [
            ['af_sky', 'Sky — Female US'], ['af_bella', 'Bella — Female US'],
            ['af_nicole', 'Nicole — Female US'], ['af_sarah', 'Sarah — Female US'],
            ['am_adam', 'Adam — Male US'], ['am_michael', 'Michael — Male US'],
            ['bf_emma', 'Emma — Female UK'], ['bm_george', 'George — Male UK'],
        ];
        fillSelect(voiceSelect, voices.map(([name, description]) => ({name, description})), speechConfiguration?.deapi_voice || 'af_sky', voice => voice.description);
    }
    document.getElementById('media-speed-field').hidden = gemini;
    document.getElementById('media-speech-style-field').hidden = !gemini;
    document.getElementById('media-speech-style').value = gemini ? (speechConfiguration.style || '') : '';
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
        style: document.getElementById('media-speech-style').value,
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
    const localUrl = localItem?.local_filename
        ? `/api/desktop/gallery/file/${encodeURIComponent(localItem.id)}`
        : '';
    const previewUrl = localItem?.local_filename && payload.kind === 'video'
        ? `/api/desktop/gallery/preview/${encodeURIComponent(localItem.id)}`
        : localUrl || payload.result_url;
    media.src = previewUrl;
    container.append(media);
    openLink.href = localUrl || payload.result_url || '#';
    openLink.hidden = !localUrl && !payload.result_url;
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

function startNeuralVisualization() {
    const canvas = document.getElementById('neural-canvas');
    const context = canvas.getContext('2d');
    const stateLabel = document.getElementById('visual-chat-state');
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const nodes = Array.from({length: reducedMotion ? 48 : 82}, (_, index) => {
        const angle = Math.random() * Math.PI * 2;
        const radius = Math.pow(Math.random(), .62) * .92;
        return {
            x: Math.cos(angle) * radius,
            y: Math.sin(angle) * radius,
            z: (Math.random() * 2 - 1) * Math.sqrt(Math.max(0, 1 - radius * radius)),
            vx: (Math.random() - .5) * .00006,
            vy: (Math.random() - .5) * .00006,
            phase: Math.random() * Math.PI * 2,
            colorIndex: index % 4,
            orbitRadius: .12 + Math.random() * .85,
            orbitSpeed: (.000035 + Math.random() * .000085) * (index % 2 ? 1 : -1),
            size: 1.1 + Math.random() * 2.2,
            hot: index % 11 === 0,
        };
    });
    let width = 1;
    let height = 1;
    let pixelRatio = 1;
    let previousTime = performance.now();

    const resize = () => {
        const bounds = canvas.getBoundingClientRect();
        width = Math.max(1, bounds.width);
        height = Math.max(1, bounds.height);
        pixelRatio = Math.min(2, window.devicePixelRatio || 1);
        canvas.width = Math.round(width * pixelRatio);
        canvas.height = Math.round(height * pixelRatio);
        context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    };
    if (window.ResizeObserver) new ResizeObserver(resize).observe(canvas);
    else window.addEventListener('resize', resize);
    resize();

    const draw = time => {
        const delta = Math.min(34, time - previousTime);
        previousTime = time;
        visualAudioEnergy *= .91;
        const syntheticSpeech = voiceInputPlaybackBlocked
            ? .22 + Math.max(0, Math.sin(time * .021)) * .34 + Math.random() * .16
            : 0;
        const activity = Math.min(1, Math.max(visualAudioEnergy, syntheticSpeech));
        const visible = !document.getElementById('visual-chat').hidden;
        if (visible) {
            context.clearRect(0, 0, width, height);
            context.fillStyle = '#010204';
            context.fillRect(0, 0, width, height);
            const centerX = width * .5;
            const centerY = height * .47;
            const style = preferences.visual_style || 'neural_core';
            const clusterRadius = Math.min(width, height) * (.29 + activity * .035);
                       const points = nodes.map(node => {
                if (style === 'orbital_mind') {
                    const angle = node.phase + time * node.orbitSpeed * (1 + activity * 2.2);
                    const radius = node.orbitRadius * Math.min(width, height) * (.34 + activity * .035);
                    return {
                        node,
                        x: centerX + Math.cos(angle) * radius,
                        y: centerY + Math.sin(angle) * radius * .48,
                    };
                }
                if (style === 'signal_bloom') {
                    const angle = node.phase + Math.sin(time * .00024 + node.orbitRadius * 8) * .16;
                    const wave = Math.sin(time * .0022 - node.orbitRadius * 15 + node.phase) * (8 + activity * 24);
                    const radius = node.orbitRadius * Math.min(width, height) * .38 + wave;
                    return {
                        node,
                        x: centerX + Math.cos(angle) * radius,
                        y: centerY + Math.sin(angle) * radius * .78,
                    };
                }
                if (style === 'synapse_drift') {
                    const movement = reducedMotion ? .18 : 1;
                    node.vx += Math.sin(time * .00042 + node.phase) * .0000007 * delta * movement;
                    node.vy += Math.cos(time * .00037 + node.phase) * .0000007 * delta * movement;
                    node.vx *= .998;
                    node.vy *= .998;
                    node.x += node.vx * delta * (1 + activity * 1.8);
                    node.y += node.vy * delta * (1 + activity * 1.8);
                    if (node.x > 1.08) node.x = -1.08;
                    if (node.x < -1.08) node.x = 1.08;
                    if (node.y > 1.08) node.y = -1.08;
                    if (node.y < -1.08) node.y = 1.08;
                    return {
                        node,
                        x: centerX + node.x * width * .46,
                        y: centerY + node.y * height * .43,
                    };
                }
                const movement = reducedMotion ? .18 : 1;
                node.vx += (-node.x * .0000017 + Math.sin(time * .0007 + node.phase) * .0000018 * (1 + activity * 2.8)) * delta * movement;
                node.vy += (-node.y * .0000017 + Math.cos(time * .00061 + node.phase) * .0000018 * (1 + activity * 2.8)) * delta * movement;
                node.vx *= .992;
                node.vy *= .992;
                node.x += node.vx * delta;
                node.y += node.vy * delta;
                const distance = Math.hypot(node.x, node.y);
                if (distance > 1.04) {
                    node.x *= .985;
                    node.y *= .985;
                    node.vx *= -.35;
                    node.vy *= -.35;
                }
                const breathing = 1 + Math.sin(time * .0015 + node.phase) * (.025 + activity * .055);
                const rotation = time * .000085;
                const rotatedX = node.x * Math.cos(rotation) - node.z * Math.sin(rotation);
                const depth = node.x * Math.sin(rotation) + node.z * Math.cos(rotation);
                const brainWidth = 1 - Math.max(0, node.y) * .27;
                const perspective = .88 + (depth + 1) * .09;
                return {
                    node,
                    depth,
                    x: centerX + rotatedX * brainWidth * clusterRadius * 1.22 * breathing * perspective,
                    y: centerY + (node.y + Math.abs(rotatedX) * .045) * clusterRadius * .88 * breathing * perspective,
                };
            });

            if (style === 'neural_core') {
                const outlineAlpha = .055 + activity * .06;
                context.strokeStyle = `rgba(115,200,255,${outlineAlpha})`;
                context.lineWidth = .8;
                context.beginPath();
                context.moveTo(centerX, centerY + clusterRadius * .92);
                context.bezierCurveTo(
                    centerX - clusterRadius * .98, centerY + clusterRadius * .76,
                    centerX - clusterRadius * 1.24, centerY - clusterRadius * .15,
                    centerX - clusterRadius * .5, centerY - clusterRadius * .82,
                );
                context.bezierCurveTo(
                    centerX - clusterRadius * .2, centerY - clusterRadius * 1.03,
                    centerX - clusterRadius * .05, centerY - clusterRadius * .94,
                    centerX, centerY - clusterRadius * .82,
                );
                context.bezierCurveTo(
                    centerX + clusterRadius * .05, centerY - clusterRadius * .94,
                    centerX + clusterRadius * .2, centerY - clusterRadius * 1.03,
                    centerX + clusterRadius * .5, centerY - clusterRadius * .82,
                );
                context.bezierCurveTo(
                    centerX + clusterRadius * 1.24, centerY - clusterRadius * .15,
                    centerX + clusterRadius * .98, centerY + clusterRadius * .76,
                    centerX, centerY + clusterRadius * .92,
                );
                context.stroke();

                for (let particle = 0; particle < 76; particle += 1) {
                    const seed = Math.abs(Math.sin(particle * 91.733));
                    const angle = particle * 2.39996 + Math.sin(time * .00018 + particle) * .045;
                    const radius = clusterRadius * (.22 + seed * 1.18);
                    const flicker = .16 + Math.max(0, Math.sin(time * .004 + particle * 1.7)) * (.22 + activity * .42);
                    context.fillStyle = `rgba(${particle % 5 ? '150,213,255' : '255,190,119'},${flicker})`;
                    context.beginPath();
                    context.arc(
                        centerX + Math.cos(angle) * radius * 1.13,
                        centerY + Math.sin(angle) * radius * .72,
                        .35 + seed * .8 + activity * .45,
                        0, Math.PI * 2,
                    );
                    context.fill();
                }

                const hotPoints = points.filter(({node}) => node.hot);
                hotPoints.forEach(({node, x, y}, tendrilIndex) => {
                    const direction = Math.atan2(y - centerY, x - centerX) + Math.sin(node.phase + time * .0003) * .22;
                    const reach = Math.max(width, height) * (.38 + (tendrilIndex % 3) * .08);
                    const endX = x + Math.cos(direction) * reach;
                    const endY = y + Math.sin(direction) * reach * .65;
                    const bend = (tendrilIndex % 2 ? 1 : -1) * (32 + tendrilIndex * 3);
                    const control1X = x + Math.cos(direction) * reach * .3 - Math.sin(direction) * bend;
                    const control1Y = y + Math.sin(direction) * reach * .18 + Math.cos(direction) * bend;
                    const control2X = x + Math.cos(direction) * reach * .7 + Math.sin(direction) * bend * .7;
                    const control2Y = y + Math.sin(direction) * reach * .48 - Math.cos(direction) * bend * .7;
                    context.strokeStyle = `rgba(${tendrilIndex % 2 ? '34,225,230' : '136,91,246'},${.09 + activity * .2})`;
                    context.lineWidth = .55 + activity * .85;
                    context.beginPath();
                    context.moveTo(x, y);
                    context.bezierCurveTo(control1X, control1Y, control2X, control2Y, endX, endY);
                    context.stroke();
                    for (let particle = 0; particle < 7; particle += 1) {
                        const progress = (particle / 7 + time * (.00008 + tendrilIndex * .000002)) % 1;
                        const inverse = 1 - progress;
                        const particleX = inverse ** 3 * x
                            + 3 * inverse ** 2 * progress * control1X
                            + 3 * inverse * progress ** 2 * control2X
                            + progress ** 3 * endX;
                        const particleY = inverse ** 3 * y
                            + 3 * inverse ** 2 * progress * control1Y
                            + 3 * inverse * progress ** 2 * control2Y
                            + progress ** 3 * endY;
                        context.fillStyle = `rgba(190,230,255,${(.18 + activity * .65) * (1 - progress * .55)})`;
                        context.beginPath();
                        context.arc(particleX, particleY, .7 + activity * 1.5, 0, Math.PI * 2);
                        context.fill();
                    }
                });
            }

            if (style === 'orbital_mind') {
                context.strokeStyle = `rgba(186,143,255,${.08 + activity * .13})`;
                context.lineWidth = .65;
                for (let ring = 1; ring <= 4; ring += 1) {
                    context.beginPath();
                    context.ellipse(
                        centerX, centerY,
                        clusterRadius * ring * .75,
                        clusterRadius * ring * .36,
                        time * .000025 * (ring % 2 ? 1 : -1), 0, Math.PI * 2,
                    );
                    context.stroke();
                }
            } else if (style === 'signal_bloom') {
                context.lineWidth = .6 + activity;
                points.forEach(({x, y}, index) => {
                    if (index % 3) return;
                    context.strokeStyle = `rgba(211,77,216,${.06 + activity * .18})`;
                    context.beginPath();
                    context.moveTo(centerX, centerY);
                    context.lineTo(x, y);
                    context.stroke();
                });
            }

            const connectionDistance = style === 'synapse_drift'
                ? Math.min(width, height) * (.17 + activity * .025)
                : style === 'orbital_mind'
                    ? clusterRadius * .33
                    : clusterRadius * (style === 'neural_core' ? .49 + activity * .07 : .38 + activity * .06);
            context.lineWidth = .7 + activity * .45;
            for (let left = 0; left < points.length; left += 1) {
                for (let right = left + 1; right < points.length; right += 1) {
                    const dx = points[left].x - points[right].x;
                    const dy = points[left].y - points[right].y;
                    const distance = Math.hypot(dx, dy);
                    if (distance >= connectionDistance) continue;
                    const alpha = (1 - distance / connectionDistance) * (.12 + activity * .28);
                    const neuralColors = ['32,218,255', '137,91,246', '255,172,74', '239,91,221'];
                    const connectionColor = {
                        neural_core: neuralColors[points[left].node.colorIndex],
                        synapse_drift: activity > .5 ? '63,225,207' : '42,132,154',
                        orbital_mind: activity > .5 ? '247,189,104' : '136,91,206',
                        signal_bloom: activity > .5 ? '248,106,226' : '135,66,190',
                    }[style];
                    context.strokeStyle = `rgba(${connectionColor},${alpha})`;
                    context.beginPath();
                    context.moveTo(points[left].x, points[left].y);
                    context.lineTo(points[right].x, points[right].y);
                    context.stroke();
                }
            }

            const palette = {
                neural_core: {bright: '224,211,255', glow: '137,91,246', fade: '84,42,160', solid: '#a986f4'},
                synapse_drift: {bright: '193,255,247', glow: '48,210,194', fade: '15,105,120', solid: '#68e1d2'},
                orbital_mind: {bright: '255,235,199', glow: '242,168,76', fade: '111,55,167', solid: '#efbd78'},
                signal_bloom: {bright: '255,215,251', glow: '225,75,207', fade: '101,32,150', solid: '#e77cdb'},
            }[style];
            points.forEach(({node, x, y, depth}) => {
                const neuralNodePalettes = [
                    {bright: '210,250,255', glow: '20,210,255', fade: '10,100,160', solid: '#35dfff'},
                    {bright: '235,220,255', glow: '137,91,246', fade: '72,30,150', solid: '#a986f4'},
                    {bright: '255,240,205', glow: '255,164,55', fade: '145,72,20', solid: '#ffb55b'},
                    {bright: '255,218,250', glow: '231,83,214', fade: '121,28,129', solid: '#ec72dc'},
                ];
                const nodePalette = style === 'neural_core'
                    ? neuralNodePalettes[node.colorIndex]
                    : palette;
                const pulse = Math.max(0, Math.sin(time * (.002 + activity * .006) + node.phase));
                const depthScale = style === 'neural_core' ? .82 + ((depth || 0) + 1) * .19 : 1;
                const radius = (node.size + pulse * (1.2 + activity * 3.2) + (node.hot ? activity * 1.8 : 0)) * depthScale;
                const glow = context.createRadialGradient(x, y, 0, x, y, radius * 4.2);
                glow.addColorStop(0, `rgba(${nodePalette.bright},${.72 + activity * .25})`);
                glow.addColorStop(.24, `rgba(${nodePalette.glow},${.46 + activity * .34})`);
                glow.addColorStop(1, `rgba(${nodePalette.fade},0)`);
                context.fillStyle = glow;
                context.beginPath();
                context.arc(x, y, radius * 4.2, 0, Math.PI * 2);
                context.fill();
                context.fillStyle = node.hot && activity > .32 ? `rgb(${nodePalette.bright})` : nodePalette.solid;
                context.beginPath();
                context.arc(x, y, Math.max(1, radius * .52), 0, Math.PI * 2);
                context.fill();
            });

            const coreRadius = (style === 'synapse_drift' ? 7 : 18) + activity * (style === 'signal_bloom' ? 31 : 23);
            const core = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, coreRadius * 3.2);
            core.addColorStop(0, `rgba(${palette.bright},${.25 + activity * .4})`);
            core.addColorStop(.28, `rgba(${palette.glow},${.16 + activity * .34})`);
            core.addColorStop(1, `rgba(${palette.fade},0)`);
            context.fillStyle = core;
            context.beginPath();
            context.arc(centerX, centerY, coreRadius * 3.2, 0, Math.PI * 2);
            context.fill();
        }
        stateLabel.textContent = voiceInputPlaybackBlocked
            ? 'Speaking'
            : microphoneCapturing
                ? 'Listening'
                : voiceInputBusy
                    ? 'Understanding'
                    : voiceInputRunning
                        ? 'Ready · microphone active'
                        : 'Present';
        window.requestAnimationFrame(draw);
    };
    window.requestAnimationFrame(draw);
}

startNeuralVisualization();

const requestedView = window.location.hash.replace('#', '');
const knownViews = ['chat', 'media', 'gallery', 'workspace', 'settings', 'personality', 'knowledge', 'memory'];
if (knownViews.includes(requestedView)) showView(requestedView);
