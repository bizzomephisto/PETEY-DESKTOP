const messages = document.getElementById('messages');
const composer = document.getElementById('composer');
const messageInput = document.getElementById('message');
const attachmentInput = document.getElementById('attachment');
const attachmentChip = document.getElementById('attachment-chip');
const sendButton = document.getElementById('send');
const voiceResponseButtons = [
    document.getElementById('voice-response-toggle'),
    document.getElementById('visual-voice-response-toggle'),
];
const statusText = document.getElementById('status');
const chatNameText = document.getElementById('chat-name');
const chatPersonaSelect = document.getElementById('chat-persona');
const mobileChatPersonaSelect = document.getElementById('mobile-chat-persona');
const jumpToLatestButton = document.getElementById('jump-to-latest');
const newChatDialog = document.getElementById('new-chat-dialog');
const newChatTitle = document.getElementById('new-chat-title');
const newChatPersona = document.getElementById('new-chat-persona');
const mobileLayoutQuery = window.matchMedia('(max-width: 760px)');
let personName = 'User';
let personaPresets = {};
let savedPersonas = [];
let personalityLoaded = false;
let aiProviderLoaded = false;
let aiProviderConfiguration = null;
let speechSettingsLoaded = false;
let speechConfiguration = null;
let voiceResponseEnabled = false;
let voiceResponseInitialized = false;
let lastAppliedVisualMode = null;
let voiceInputSettingsLoaded = false;
let voiceInputConfiguration = {mode: 'disabled', provider: 'deapi', model: 'WhisperLargeV3', gemini_model: 'gemini-3.5-transcribe', wake_word: 'Petey', device_id: '', sensitivity: 'normal', wake_ack_delay_ms: 500, submit_silence_ms: 800, follow_up_seconds: 8};
let planBuilderLoaded = false;
let planEstimateTimer = null;
let planEstimateRequest = 0;
let voiceInputModels = {deapi: ['WhisperLargeV3'], gemini: ['gemini-3.5-transcribe']};
let microphoneStream = null;
let microphoneContext = null;
let microphoneSource = null;
let microphoneProcessor = null;
let microphoneSilentOutput = null;
let microphoneFrameCount = 0;
let microphoneCapture = [];
let microphonePreRoll = [];
let microphoneCapturing = false;
let microphoneLastVoiceAt = 0;
let microphoneCaptureStartedAt = 0;
let voiceInputRunning = false;
let voiceInputBusy = false;
let voiceInputPlaybackBlocked = false;
let wakeCueConfiguration = {voice: 'default', clips: [], fallback_phrases: ['Yeah?', "What's up?", 'Mm-hmm?']};
let wakeCueAudios = [];
let wakeCueBuffers = [];
let wakeCueAudio = null;
let wakeCuePlaying = false;
let lastWakeCueIndex = -1;
let microphoneTestActive = false;
let pushToTalkHeld = false;
let mobileVisualMicMuted = false;
let wakeWordArmedUntil = 0;
let wakeCueAcknowledgedUntil = 0;
let wakeCuePendingTimer = null;
let wakeCuePendingAfter = 0;
let wakeDetectorSessionId = '';
let wakeDetectorStarting = false;
let wakeDetectorBusy = false;
let wakeDetectorChunks = [];
let wakeDetectorSampleCount = 0;
let voiceConversationActive = false;
let voiceConversationAwaitingReply = false;
let voiceConversationFollowupTimer = null;
let keyboardPushToTalkActive = false;
let visualAudioEnergy = 0;
let lastPeteyCaption = '';
let visualCaptionTimer = null;
let visualCaptionHideTimer = null;
let nativeVisualFullscreen = false;
let geminiSpeechModels = [];
let geminiSpeechVoices = [];
let openaiSpeechModels = [];
let openaiSpeechVoices = [];
let memoryProviderLoaded = false;
let memoryProviderConfiguration = null;
let mediaCatalogLoaded = false;
let mediaSelectedModels = {};
const mediaModelsCache = new Map();
let mediaPollTimer = null;
let mediaJobsLoading = false;
let lastMediaJobsSignature = '';
const displayedMediaJobs = new Set();
let conversations = [];
let activeConversationId = '';
let conversationPersonaOptions = [];
let temporaryHistory = [];
let pendingDeleteConversation = null;
let preferences = {always_on_top: false, sidebar_collapsed: false, ui_scale: 1, visual_mode: false, visual_style: 'neural_core'};
let workspaces = [];
let activeWorkspaceId = '';
let workspaceDirectory = '';
let editorSha256 = null;
let workspaceLoaded = false;
let toolsLoaded = false;
let activeChatAudio = null;
let activeSpeechButton = null;
let activeSpeechCancel = null;
let speechPlaybackContext = null;
let speechUnlockAudio = null;
let neuralAnimationFrame = null;
let neuralDraw = null;

function ensureNeuralVisualizationRunning() {
    const visual = document.getElementById('visual-chat');
    const chatVisible = document.getElementById('view-chat').classList.contains('active-view');
    if (neuralAnimationFrame || !neuralDraw || document.hidden || visual.hidden || !chatVisible) return;
    neuralAnimationFrame = window.requestAnimationFrame(neuralDraw);
}

function showEmptyState(title = 'Petey is ready.', copy = 'Start a conversation or attach an image for him to inspect.') {
    messages.innerHTML = `<div class="empty-state" id="empty-state"><img src="/static/petey_avatar.png" alt=""><h2>${title}</h2><p>${copy}</p></div>`;
    updateJumpToLatest();
}

function removeEmptyState() {
    document.getElementById('empty-state')?.remove();
}

function distanceFromLatest() {
    return Math.max(0, messages.scrollHeight - messages.scrollTop - messages.clientHeight);
}

function updateJumpToLatest() {
    jumpToLatestButton.hidden = messages.childElementCount === 0 || distanceFromLatest() < 140;
}

function scrollToLatest(smooth = true) {
    messages.scrollTo({
        top: messages.scrollHeight,
        behavior: smooth && !window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'auto',
    });
    if (!smooth) updateJumpToLatest();
}

jumpToLatestButton.addEventListener('click', () => scrollToLatest(true));
messages.addEventListener('scroll', updateJumpToLatest, {passive: true});

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

function generatedImageUrl(job) {
    const result = job?.result || {};
    const galleryItem = result.gallery_item;
    if (galleryItem?.local_filename && galleryItem.id) {
        return `/api/desktop/gallery/file/${encodeURIComponent(galleryItem.id)}`;
    }
    return result.result_url || '';
}

function configureExternalOpenLink(link, label = 'file') {
    link.target = '_blank';
    link.rel = 'noopener';
    link.addEventListener('click', async event => {
        const galleryItemId = link.dataset.galleryItemId || '';
        if (galleryItemId && window.pywebview?.api?.open_gallery_item) {
            event.preventDefault();
            try {
                const result = await window.pywebview.api.open_gallery_item(galleryItemId);
                if (!result?.ok) window.alert(result?.error || `Could not open this ${label}.`);
            } catch (_error) {
                window.alert(`Could not open this ${label}.`);
            }
            return;
        }
        if (!window.pywebview?.api?.open_external_url) return;
        event.preventDefault();
        try {
            if (!await window.pywebview.api.open_external_url(link.href)) {
                window.alert(`Could not open this ${label} in the default browser.`);
            }
        } catch (_error) {
            window.alert(`Could not open this ${label} in the default browser.`);
        }
    });
}

async function loadChatGeneratedImage(source, prompt) {
    let displaySource = source;
    let objectUrl = '';
    if (source.startsWith('/')) {
        const response = await fetch(source, {cache: 'no-store'});
        if (!response.ok) throw new Error(`Gallery returned ${response.status}.`);
        const blob = await response.blob();
        if (!blob.type.startsWith('image/')) throw new Error('Gallery returned a non-image file.');
        objectUrl = URL.createObjectURL(blob);
        displaySource = objectUrl;
    }
    const image = document.createElement('img');
    image.alt = prompt;
    try {
        await new Promise((resolve, reject) => {
            image.addEventListener('load', resolve, {once: true});
            image.addEventListener('error', () => reject(new Error('The image file could not be decoded.')), {once: true});
            image.src = displaySource;
        });
        return {image, objectUrl};
    } catch (error) {
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        throw error;
    }
}

async function followChatImageJob(card, event) {
    const jobId = String(event?.result?.job_id || '');
    if (!jobId) return;
    const status = card.querySelector('.chat-image-status');
    const prompt = String(event.result?.prompt || 'Generated image');
    for (let attempt = 0; attempt < 600 && card.isConnected; attempt += 1) {
        try {
            const payload = await apiJson(`/api/desktop/media/jobs/${encodeURIComponent(jobId)}`);
            const job = payload.job;
            if (job.status === 'failed') {
                card.classList.add('failed');
                status.textContent = job.error || 'Image generation failed.';
                return;
            }
            if (job.status === 'completed') {
                const source = generatedImageUrl(job);
                if (!source) {
                    card.classList.add('failed');
                    status.textContent = 'The image finished, but its file is unavailable.';
                    return;
                }
                const followLatest = distanceFromLatest() < 100;
                try {
                    const {image, objectUrl} = await loadChatGeneratedImage(source, prompt);
                    const caption = document.createElement('figcaption');
                    caption.textContent = prompt;
                    const open = document.createElement('a');
                    open.href = source;
                    const galleryItem = job.result?.gallery_item;
                    if (galleryItem?.local_filename && galleryItem.id) {
                        open.dataset.galleryItemId = String(galleryItem.id);
                    }
                    configureExternalOpenLink(open, 'image');
                    open.textContent = 'Open image';
                    caption.append(' · ', open);
                    card.replaceChildren(image, caption);
                    card.classList.remove('pending');
                    card.classList.add('completed');
                    if (followLatest) messages.scrollTop = messages.scrollHeight;
                    updateJumpToLatest();
                } catch (error) {
                    card.classList.remove('pending');
                    card.classList.add('failed');
                    status.textContent = `The generated image could not be displayed: ${error.message}`;
                }
                return;
            }
            const progress = Number(job.progress);
            const progressText = Number.isFinite(progress) ? ` · ${Math.round(progress)}%` : '';
            status.textContent = `${job.status === 'queued' ? 'Image queued' : 'Creating image'}${progressText}…`;
        } catch (error) {
            if (attempt === 0) {
                try {
                    const source = `/api/desktop/gallery/file/${encodeURIComponent(jobId)}`;
                    const {image} = await loadChatGeneratedImage(source, prompt);
                    const caption = document.createElement('figcaption');
                    caption.textContent = prompt;
                    const open = document.createElement('a');
                    open.href = source;
                    open.dataset.galleryItemId = jobId;
                    configureExternalOpenLink(open, 'image');
                    open.textContent = 'Open image';
                    caption.append(' · ', open);
                    card.replaceChildren(image, caption);
                    card.classList.remove('pending');
                    card.classList.add('completed');
                    return;
                } catch (_galleryError) { /* The job may still be starting. */ }
            }
            card.classList.add('failed');
            status.textContent = `Could not follow image generation: ${error.message}`;
            return;
        }
        await new Promise(resolve => window.setTimeout(resolve, 1000));
    }
    if (card.isConnected) status.textContent = 'Image generation is still running. Check Media for progress.';
}

function appendChatImageJobs(content, toolEvents) {
    for (const event of toolEvents || []) {
        if (event.name !== 'generate_image' || event.result?.status !== 'queued' || !event.result?.job_id) continue;
        const card = document.createElement('figure');
        card.className = 'chat-generated-image pending';
        const status = document.createElement('figcaption');
        status.className = 'chat-image-status';
        status.textContent = 'Image queued…';
        card.append(status);
        content.append(card);
        window.setTimeout(() => followChatImageJob(card, event), 0);
    }
}

function addMessage(role, text, options = {}) {
    const followLatest = options.forceScroll === true || distanceFromLatest() < 100;
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
    content.append(meta);
    if (text || options.typing) {
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        if (role === 'assistant' && !options.typing) {
            const artifactPath = '\\/api\\/addons\\/petey-opencode\\/artifacts\\/\\d+\\/\\d+';
            const galleryPath = '\\/api\\/desktop\\/gallery\\/file\\/[a-f0-9]{32}';
            const pattern = new RegExp(
                `\\[([^\\]\\n]+)\\]\\((https?:\\/\\/[^\\s<>()]+|${artifactPath}|${galleryPath})\\)`
                + `|(https?:\\/\\/[^\\s<>()\\[\\]]+|${artifactPath}|${galleryPath})`,
                'g',
            );
            let offset = 0;
            for (const match of String(text).matchAll(pattern)) {
                bubble.append(document.createTextNode(text.slice(offset, match.index)));
                const link = document.createElement('a');
                const originalHref = match[2] || match[3];
                let href = originalHref;
                let artifactHref = '';
                let galleryItemId = '';
                try {
                    const parsed = new URL(originalHref, window.location.href);
                    const artifact = /^\/api\/addons\/petey-opencode\/artifacts\/\d+\/\d+$/.test(parsed.pathname);
                    const galleryMatch = /^\/api\/desktop\/gallery\/file\/([a-f0-9]{32})$/.exec(parsed.pathname);
                    const localOrigin = ['127.0.0.1', 'localhost', '::1'].includes(parsed.hostname);
                    const sameOrigin = parsed.origin === window.location.origin;
                    if ((artifact || galleryMatch) && (localOrigin || sameOrigin)) {
                        artifactHref = `${parsed.pathname}${parsed.search}${parsed.hash}`;
                        if (galleryMatch) galleryItemId = galleryMatch[1];
                    }
                    if (artifactHref && localOrigin) {
                        href = artifactHref;
                    }
                } catch (_error) {
                    // Keep the displayed text; malformed links remain inert below.
                }
                link.href = href;
                if (galleryItemId) link.dataset.galleryItemId = galleryItemId;
                link.target = '_blank';
                link.rel = 'noopener';
                link.addEventListener('click', async event => {
                    if (galleryItemId && window.pywebview?.api?.open_gallery_item) {
                        event.preventDefault();
                        try {
                            const result = await window.pywebview.api.open_gallery_item(galleryItemId);
                            if (!result?.ok) window.alert(result?.error || 'Could not open this image.');
                        } catch (_error) {
                            window.alert('Could not open this image.');
                        }
                        return;
                    }
                    if (!window.pywebview?.api?.open_external_url) return;
                    event.preventDefault();
                    try {
                        if (!await window.pywebview.api.open_external_url(link.href)) {
                            window.alert('Could not open the default browser. Copy the link to open it manually.');
                        }
                    } catch (error) {
                        window.alert('Could not open the default browser. Copy the link to open it manually.');
                    }
                });
                link.textContent = artifactHref || match[1] || originalHref;
                bubble.append(link);
                offset = match.index + match[0].length;
            }
            bubble.append(document.createTextNode(text.slice(offset)));
        } else {
            bubble.textContent = text;
        }
        content.append(bubble);
    }

    if (options.attachmentPreviewUrl) {
        const attachment = document.createElement('figure');
        attachment.className = 'message-attachment';
        const image = document.createElement('img');
        image.src = options.attachmentPreviewUrl;
        image.alt = options.attachmentName ? `Attached image: ${options.attachmentName}` : 'Attached image';
        image.addEventListener('load', () => URL.revokeObjectURL(options.attachmentPreviewUrl), {once: true});
        const caption = document.createElement('figcaption');
        caption.textContent = options.attachmentName || 'Attached image';
        attachment.append(image, caption);
        content.append(attachment);
    }

    appendChatImageJobs(content, options.toolEvents);
    item.append(avatar, content);
    messages.append(item);
    if (followLatest) messages.scrollTop = messages.scrollHeight;
    updateJumpToLatest();
    if (role === 'assistant' && !options.typing && text) setLastPeteyCaption(text);
    return item;
}

window.addEventListener('petey:addon-notification', event => {
    const detail = event.detail || {};
    if (detail.addon !== 'petey-opencode' || typeof detail.message !== 'string') return;
    addMessage('assistant', detail.message, {forceScroll: true});
    if (!document.getElementById('temporary-mode').checked) {
        apiJson('/api/desktop/messages/notification', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                source: detail.addon,
                message: detail.message,
                conversation_id: activeConversationId,
                surface: mobileLayoutQuery.matches ? 'mobile_petey' : 'petey_desktop',
            }),
        }).catch(error => { statusText.textContent = `Could not save OpenCode notice: ${error.message}`; });
    }
});

function activeConversation() {
    return conversations.find(item => item.id === activeConversationId) || null;
}

function personaChoiceLabel(option) {
    if (option.system) return `System · ${option.name || 'Petey'}`;
    return `${option.slot}. ${option.name || `Profile ${option.slot}`}`;
}

function fillConversationPersonaSelect(select, selectedSlot = null) {
    select.replaceChildren();
    conversationPersonaOptions.forEach(option => {
        const item = document.createElement('option');
        item.value = option.slot === null ? 'system' : String(option.slot);
        item.textContent = personaChoiceLabel(option);
        item.title = option.role_tag || item.textContent;
        select.append(item);
    });
    if (!select.options.length) select.add(new Option('System · Petey', 'system'));
    const value = selectedSlot === null || selectedSlot === undefined ? 'system' : String(selectedSlot);
    select.value = [...select.options].some(option => option.value === value) ? value : 'system';
}

function updateChatHeader() {
    const conversation = activeConversation();
    chatNameText.textContent = conversation?.title || 'New chat';
    statusText.textContent = '';
    fillConversationPersonaSelect(chatPersonaSelect, conversation?.persona_slot);
    chatPersonaSelect.disabled = !conversation;
    fillConversationPersonaSelect(mobileChatPersonaSelect, conversation?.persona_slot);
    mobileChatPersonaSelect.disabled = !conversation;
}

function applyConversationContext(payload) {
    if (Array.isArray(payload.persona_options)) conversationPersonaOptions = payload.persona_options;
    if (payload.speech) speechConfiguration = payload.speech;
    if (payload.voice_cues) applyWakeCueConfiguration(payload.voice_cues);
    if (payload.speech && voiceResponseInitialized && !mobileLayoutQuery.matches
        && !preferences.visual_mode) {
        setVoiceResponseEnabled(Boolean(speechConfiguration.auto_speak));
    } else {
        renderVoiceResponseToggle();
    }
    updateChatHeader();
}

async function refreshConversationPersonaOptions() {
    const payload = await apiJson('/api/desktop/conversations');
    applyConversationContext(payload);
}

async function loadDesktop() {
    try {
        const bootstrap = await apiJson('/api/desktop/bootstrap');
        personName = bootstrap.person_name || 'User';
        document.getElementById('user-display-name').value = personName;
        activeConversationId = bootstrap.conversation_id;
        conversations = bootstrap.conversations || [];
        conversationPersonaOptions = bootstrap.persona_options || [];
        preferences = {...preferences, ...(bootstrap.preferences || {})};
        speechConfiguration = bootstrap.speech || {provider: 'automatic', auto_speak: false};
        voiceResponseEnabled = mobileLayoutQuery.matches
            ? Boolean(preferences.visual_mode)
            : Boolean(speechConfiguration.auto_speak);
        voiceResponseInitialized = true;
        voiceInputConfiguration = {...voiceInputConfiguration, ...(bootstrap.voice_input || {})};
        workspaces = bootstrap.workspaces || [];
        activeWorkspaceId = bootstrap.active_workspace_id || '';
        applyPreferences();
        renderConversations();
        updateChatHeader();
        await loadConversationMessages();
        if (mobileLayoutQuery.matches) {
            const emptyCopy = document.querySelector('#empty-state p');
            if (emptyCopy) emptyCopy.textContent = 'Start a conversation.';
        }
        configureVoiceInputUI();
        await loadWakeCues();
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
    history.forEach(item => addMessage(item.role, item.message, {
        toolEvents: item.metadata?.tool_events || [],
    }));
    if (!history.length) showEmptyState();
    scrollToLatest(false);
    updateChatHeader();
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
        if (conversation.id === activeConversationId) updateChatHeader();
    } catch (error) {
        window.alert(error.message);
    }
}

async function selectConversation(conversationId) {
    if (conversationId === activeConversationId && !document.getElementById('temporary-mode').checked) return;
    const payload = await apiJson(`/api/desktop/conversations/${encodeURIComponent(conversationId)}/select`, {method: 'PUT'});
    activeConversationId = conversationId;
    applyConversationContext(payload);
    leaveTemporaryMode();
    renderConversations();
    showView('chat');
    await loadConversationMessages();
}

async function deleteConversation(conversation) {
    pendingDeleteConversation = conversation;
    document.getElementById('delete-chat-name').textContent = conversation.title;
    document.getElementById('delete-chat-dialog').hidden = false;
    document.getElementById('delete-chat-cancel').focus();
}

function closeDeleteChatDialog() {
    pendingDeleteConversation = null;
    document.getElementById('delete-chat-dialog').hidden = true;
}

async function confirmDeleteConversation(preserveMemory) {
    const conversation = pendingDeleteConversation;
    if (!conversation) return;
    const dialog = document.getElementById('delete-chat-dialog');
    const buttons = dialog.querySelectorAll('button');
    buttons.forEach(button => { button.disabled = true; });
    try {
        const payload = await apiJson(
            `/api/desktop/conversations/${encodeURIComponent(conversation.id)}?preserve_memory=${preserveMemory ? 'true' : 'false'}`,
            {method: 'DELETE'},
        );
        closeDeleteChatDialog();
        conversations = payload.conversations;
        activeConversationId = payload.conversation_id;
        applyConversationContext(payload);
        leaveTemporaryMode();
        renderConversations();
        await loadConversationMessages();
    } catch (error) {
        window.alert(error.message);
    } finally {
        buttons.forEach(button => { button.disabled = false; });
    }
}

document.getElementById('delete-chat-cancel').addEventListener('click', closeDeleteChatDialog);
document.getElementById('delete-chat-cancel-x').addEventListener('click', closeDeleteChatDialog);
document.getElementById('delete-chat-keep-memory').addEventListener('click', () => confirmDeleteConversation(true));
document.getElementById('delete-chat-with-memory').addEventListener('click', () => confirmDeleteConversation(false));

function closeNewChatDialog() {
    newChatDialog.hidden = true;
}

async function openNewChatDialog() {
    try {
        const payload = await apiJson('/api/desktop/conversations');
        if (Array.isArray(payload.persona_options)) conversationPersonaOptions = payload.persona_options;
        fillConversationPersonaSelect(newChatPersona, null);
        newChatTitle.value = 'New chat';
        newChatDialog.hidden = false;
        newChatTitle.focus();
        newChatTitle.select();
    } catch (error) {
        window.alert(error.message);
    }
}

document.getElementById('new-chat').addEventListener('click', openNewChatDialog);
document.getElementById('new-chat-cancel').addEventListener('click', closeNewChatDialog);
document.getElementById('new-chat-cancel-x').addEventListener('click', closeNewChatDialog);
newChatDialog.addEventListener('click', event => {
    if (event.target === newChatDialog) closeNewChatDialog();
});
document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !newChatDialog.hidden) closeNewChatDialog();
});

document.getElementById('new-chat-form').addEventListener('submit', async event => {
    event.preventDefault();
    const title = newChatTitle.value.trim() || 'New chat';
    const personaSlot = newChatPersona.value === 'system' ? null : Number(newChatPersona.value);
    try {
        const payload = await apiJson('/api/desktop/conversations', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title, persona_slot: personaSlot}),
        });
        conversations = payload.conversations;
        activeConversationId = payload.conversation_id;
        applyConversationContext(payload);
        leaveTemporaryMode();
        renderConversations();
        showView('chat');
        showEmptyState(payload.conversation.title, 'This conversation will be saved to Petey’s local memory.');
        updateChatHeader();
        closeNewChatDialog();
        messageInput.focus();
    } catch (error) {
        window.alert(error.message);
    }
});

chatPersonaSelect.addEventListener('change', async () => {
    const conversation = activeConversation();
    if (!conversation) return;
    const previous = conversation.persona_slot ?? null;
    const personaSlot = chatPersonaSelect.value === 'system' ? null : Number(chatPersonaSelect.value);
    chatPersonaSelect.disabled = true;
    mobileChatPersonaSelect.disabled = true;
    try {
        const payload = await apiJson(`/api/desktop/conversations/${encodeURIComponent(conversation.id)}`, {
            method: 'PATCH', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({persona_slot: personaSlot}),
        });
        conversations = payload.conversations;
        applyConversationContext(payload);
        renderConversations();
        fillConversationPersonaSelect(mobileChatPersonaSelect, activeConversation()?.persona_slot);
    } catch (error) {
        fillConversationPersonaSelect(chatPersonaSelect, previous);
        fillConversationPersonaSelect(mobileChatPersonaSelect, previous);
        window.alert(error.message);
    } finally {
        const hasConversation = Boolean(activeConversation());
        chatPersonaSelect.disabled = !hasConversation;
        mobileChatPersonaSelect.disabled = !hasConversation;
    }
});
mobileChatPersonaSelect.addEventListener('change', () => {
    chatPersonaSelect.value = mobileChatPersonaSelect.value;
    chatPersonaSelect.dispatchEvent(new Event('change', {bubbles: true}));
});

let selectedAttachmentPreviewUrl = '';

function clearAttachmentPreview() {
    if (selectedAttachmentPreviewUrl) URL.revokeObjectURL(selectedAttachmentPreviewUrl);
    selectedAttachmentPreviewUrl = '';
    attachmentChip.replaceChildren();
    attachmentChip.hidden = true;
}

function renderAttachmentPreview(file) {
    clearAttachmentPreview();
    if (!file) return;
    if (!file.type.startsWith('image/')) {
        attachmentChip.textContent = `Attached: ${file.name}`;
        attachmentChip.hidden = false;
        return;
    }
    selectedAttachmentPreviewUrl = URL.createObjectURL(file);
    const image = document.createElement('img');
    image.src = selectedAttachmentPreviewUrl;
    image.alt = `Selected image: ${file.name}`;
    const details = document.createElement('span');
    const name = document.createElement('strong');
    name.textContent = file.name;
    const size = document.createElement('small');
    size.textContent = formatFileSize(file.size);
    details.append(name, size);
    attachmentChip.append(image, details);
    attachmentChip.hidden = false;
}

attachmentInput.addEventListener('change', () => {
    renderAttachmentPreview(attachmentInput.files[0]);
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

async function readChatStream(response, onEvent) {
    if (!response.body) throw new Error('Streaming is unavailable in this browser.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
        while (true) {
            const {value, done} = await reader.read();
            buffer += decoder.decode(value, {stream: !done});
            const lines = buffer.split('\n');
            buffer = lines.pop();
            if (done && buffer.trim()) lines.push(buffer);
            for (const line of lines) {
                if (!line.trim()) continue;
                const event = JSON.parse(line);
                if (event.type === 'error') throw new Error(event.error);
                if (event.type === 'done') return event;
                onEvent(event);
            }
            if (done) throw new Error('The connection ended before the reply was complete.');
        }
    } finally {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
    }
}

composer.addEventListener('submit', async event => {
    event.preventDefault();
    if (voiceResponseEnabled && speechConfiguration?.provider !== 'disabled') {
        primeSpeechPlayback();
    }
    const text = messageInput.value.trim();
    const file = attachmentInput.files[0];
    if (sendButton.disabled || (!text && !file)) return;
    const continueVoiceConversation = voiceInputConfiguration.mode === 'wake_word'
        && voiceConversationActive && voiceConversationAwaitingReply;

    const attachmentPreviewUrl = file?.type?.startsWith('image/') ? URL.createObjectURL(file) : '';
    const displayedText = text || (file && !attachmentPreviewUrl ? `Attached: ${file.name}` : '');
    const historyText = text || (file ? `[Attached ${file.name}]` : '');
    const temporary = document.getElementById('temporary-mode').checked;
    const priorTemporaryHistory = temporaryHistory.slice();
    addMessage('user', displayedText, {attachmentPreviewUrl, attachmentName: file?.name || '', forceScroll: true});
    const typing = addMessage('assistant', 'Typing…', {typing: true, forceScroll: true});
    const body = new FormData();
    body.append('message', text);
    body.append('stream', 'true');
    body.append('surface', mobileLayoutQuery.matches ? 'mobile_petey' : 'petey_desktop');
    if (file) body.append('attachment', file);
    if (temporary) {
        body.append('temporary', 'true');
        body.append('temporary_history', JSON.stringify(priorTemporaryHistory));
        temporaryHistory.push({role: 'user', content: historyText});
    }

    messageInput.value = '';
    messageInput.style.height = 'auto';
    attachmentInput.value = '';
    clearAttachmentPreview();
    sendButton.disabled = true;
    statusText.textContent = 'Petey is preparing a reply…';
    let partialText = '';
    let spokenPrefix = '';
    let autoSpeechChain = Promise.resolve();
    const autoSpeak = speechConfiguration?.provider !== 'disabled'
        && voiceResponseEnabled;
    try {
        const response = await fetch('/api/desktop/chat', {method: 'POST', body});
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Request failed');
        }
        const payload = await readChatStream(response, event => {
            if (event.type !== 'delta') return;
            const follow = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 100;
            partialText += event.text;
            typing.classList.remove('typing');
            typing.querySelector('.bubble').textContent = partialText;
            statusText.textContent = 'Petey is replying…';
            if (autoSpeak && !spokenPrefix) {
                const segment = firstStreamingSpeechSegment(partialText);
                if (segment && !/(?:^|\n)\s*Created files:/i.test(segment)) {
                    spokenPrefix = segment;
                    autoSpeechChain = autoSpeechChain.then(() => speakChatText(segment));
                }
            }
            if (follow) messages.scrollTop = messages.scrollHeight;
            updateJumpToLatest();
        });
        typing.remove();
        addMessage('assistant', payload.text || '', {
            toolEvents: payload.tool_events || [],
        });
        if (autoSpeak && payload.text) {
            const remainder = spokenPrefix && payload.text.startsWith(spokenPrefix)
                ? payload.text.slice(spokenPrefix.length).trim() : payload.text;
            if (!spokenPrefix || remainder) {
                autoSpeechChain = autoSpeechChain.then(() => speakChatText(remainder));
            }
        }
        if (continueVoiceConversation) {
            if (autoSpeak && payload.text) {
                autoSpeechChain.finally(openVoiceConversationFollowup);
            } else {
                openVoiceConversationFollowup();
            }
        }
        if (temporary) temporaryHistory.push({role: 'assistant', content: payload.text || ''});
        if (temporary) statusText.textContent = 'Temporary · nothing saved';
        else updateChatHeader();
    } catch (error) {
        if (partialText) {
            typing.classList.remove('typing');
            typing.querySelector('.bubble').textContent = `${partialText}\n\n[Reply interrupted]`;
        } else {
            typing.remove();
        }
        addMessage('assistant', `I hit a problem: ${error.message}`);
        statusText.textContent = 'Something went wrong';
        if (continueVoiceConversation) {
            if (spokenPrefix) autoSpeechChain.finally(openVoiceConversationFollowup);
            else openVoiceConversationFollowup();
        }
    } finally {
        sendButton.disabled = false;
        messageInput.focus();
    }
});

function firstStreamingSpeechSegment(text) {
    if (text.length < 28) return '';
    const sentence = text.match(/^([\s\S]{28,}?[.!?]["')\]]?)(?:\s|$)/);
    if (sentence) return sentence[1].trim();
    if (text.length < 180) return '';
    const boundary = text.lastIndexOf(' ', 170);
    return text.slice(0, boundary >= 100 ? boundary : 170).trim();
}

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

function renderVoiceResponseToggle() {
    const available = speechConfiguration?.provider !== 'disabled';
    const enabled = available && voiceResponseEnabled;
    voiceResponseButtons.forEach(button => {
        button.textContent = '🔊';
        button.classList.toggle('active', enabled);
        button.classList.toggle('muted', !enabled);
        button.setAttribute('aria-pressed', String(enabled));
        button.setAttribute('aria-label', enabled ? 'Turn voice responses off' : 'Turn voice responses on');
        button.title = available
            ? (enabled ? 'Voice responses on · click to mute' : 'Voice responses off · click to enable')
            : 'Choose a speech provider to enable voice responses';
        button.disabled = !available;
    });
}

function setVoiceResponseEnabled(enabled) {
    voiceResponseEnabled = Boolean(enabled) && speechConfiguration?.provider !== 'disabled';
    if (voiceResponseEnabled) {
        primeSpeechPlayback();
    } else {
        if (activeSpeechCancel) activeSpeechCancel();
        activeSpeechCancel = null;
        activeChatAudio = null;
        window.speechSynthesis?.cancel?.();
        resetSpeechButton(activeSpeechButton);
        setVoicePlaybackActive(false);
    }
    renderVoiceResponseToggle();
}

async function toggleVoiceResponse() {
    const previous = voiceResponseEnabled;
    const enabled = !previous;
    setVoiceResponseEnabled(enabled);
    if (mobileLayoutQuery.matches) return;
    voiceResponseButtons.forEach(button => { button.disabled = true; });
    try {
        const payload = await apiJson('/api/desktop/speech', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({auto_speak: enabled}),
        });
        speechConfiguration = payload.configuration;
        if (payload.voice_cues) applyWakeCueConfiguration(payload.voice_cues);
        setVoiceResponseEnabled(Boolean(speechConfiguration.auto_speak));
        if (speechSettingsLoaded) fillSpeechForm(speechConfiguration);
    } catch (error) {
        setVoiceResponseEnabled(previous);
        statusText.textContent = `Could not change voice responses: ${error.message}`;
    } finally {
        renderVoiceResponseToggle();
    }
}

voiceResponseButtons.forEach(button => button.addEventListener('click', toggleVoiceResponse));

function applyPreferences() {
    const theme = preferences.theme || 'midnight';
    document.documentElement.dataset.theme = theme;
    document.querySelectorAll('[name="interface-theme"]').forEach(input => { input.checked = input.value === theme; });
    const scale = Number(preferences.ui_scale) || 1;
    document.documentElement.style.setProperty('--ui-scale', scale);
    document.querySelector('.app-shell').classList.toggle('sidebar-collapsed', Boolean(preferences.sidebar_collapsed));
    document.getElementById('always-on-top').checked = Boolean(preferences.always_on_top);
    document.getElementById('sidebar-collapsed-setting').checked = Boolean(preferences.sidebar_collapsed);
    document.getElementById('ui-scale-value').textContent = `${Math.round(scale * 100)}%`;
    document.getElementById('collapse-sidebar').title = preferences.sidebar_collapsed ? 'Expand sidebar' : 'Collapse sidebar';
    const visualMode = Boolean(preferences.visual_mode);
    const enteringVisualMode = visualMode && lastAppliedVisualMode !== true;
    lastAppliedVisualMode = visualMode;
    document.getElementById('view-chat').classList.toggle('visual-mode', visualMode);
    messages.hidden = visualMode;
    document.getElementById('visual-chat').hidden = !visualMode;
    document.getElementById('visual-mode-toggle').classList.toggle('active', visualMode);
    document.getElementById('visual-mode-toggle').textContent = visualMode ? 'Show chat' : 'Visual mode';
    const styleSelect = document.getElementById('visual-style-select');
    styleSelect.hidden = !visualMode;
    styleSelect.value = preferences.visual_style || 'neural_core';
    document.getElementById('visual-fullscreen').hidden = !visualMode;
    document.getElementById('mobile-animation').value = preferences.visual_style || 'neural_core';
    if (voiceResponseInitialized && enteringVisualMode && !voiceResponseEnabled) {
        setVoiceResponseEnabled(true);
    } else {
        renderVoiceResponseToggle();
    }
    if (visualMode) {
        ensureNeuralVisualizationRunning();
    } else setMobileVisualMenuOpen(false);
}

let themeSaving = false;
document.querySelectorAll('[name="interface-theme"]').forEach(input => {
    input.addEventListener('change', async () => {
        if (!input.checked || themeSaving) return;
        themeSaving = true;
        const previous = preferences.theme || 'midnight';
        const controls = document.querySelectorAll('[name="interface-theme"]');
        controls.forEach(control => { control.disabled = true; });
        document.documentElement.dataset.theme = input.value;
        const feedback = document.getElementById('theme-status');
        setFeedback(feedback, 'Saving theme…');
        try {
            const payload = await apiJson('/api/desktop/preferences', {
                method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({theme: input.value}),
            });
            preferences = {...preferences, theme: payload.preferences.theme};
            setFeedback(feedback, 'Theme saved. Make yourself at home.', 'success');
        } catch (error) {
            preferences.theme = previous;
            setFeedback(feedback, `Could not save theme: ${error.message}`, 'error');
        } finally {
            themeSaving = false;
            controls.forEach(control => { control.disabled = false; });
            applyPreferences();
        }
    });
});

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
    if (!preferences.visual_mode) setVoiceResponseEnabled(true);
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
        showVisualCaption(captionExcerpt(lastPeteyCaption));
        scheduleVisualCaptionFade();
    }
}

function showVisualCaption(text) {
    const caption = document.getElementById('visual-caption');
    caption.textContent = text;
    caption.classList.toggle('is-visible', Boolean(text));
}

function scheduleVisualCaptionFade() {
    window.clearTimeout(visualCaptionHideTimer);
    visualCaptionHideTimer = window.setTimeout(() => {
        document.getElementById('visual-caption').classList.remove('is-visible');
        visualCaptionHideTimer = null;
    }, 5000);
}

function startVisualCaption(text) {
    window.clearInterval(visualCaptionTimer);
    window.clearTimeout(visualCaptionHideTimer);
    visualCaptionHideTimer = null;
    const words = String(text || '').trim().split(/\s+/).filter(Boolean);
    lastPeteyCaption = String(text || '').trim();
    let cursor = 1;
    const render = () => {
        const start = Math.max(0, cursor - 16);
        showVisualCaption(words.slice(start, cursor).join(' '));
        cursor = Math.min(words.length, cursor + 1);
    };
    render();
    visualCaptionTimer = window.setInterval(render, 330);
}

function finishVisualCaption() {
    window.clearInterval(visualCaptionTimer);
    visualCaptionTimer = null;
    showVisualCaption(captionExcerpt(lastPeteyCaption));
    scheduleVisualCaptionFade();
}

async function toggleVisualFullscreen() {
    if (!preferences.visual_mode) return;
    const visual = document.getElementById('visual-chat');
    const fullscreenTarget = mobileLayoutQuery.matches
        ? document.getElementById('view-chat') : visual;
    if (document.fullscreenElement) {
        await document.exitFullscreen();
        return;
    }
    if (nativeVisualFullscreen && window.pywebview?.api?.toggle_fullscreen) {
        const result = await window.pywebview.api.toggle_fullscreen();
        nativeVisualFullscreen = Boolean(result?.fullscreen);
        document.body.classList.toggle('native-visual-fullscreen', nativeVisualFullscreen);
        syncFullscreenControls();
        return;
    }
    try {
        if (!fullscreenTarget.requestFullscreen) throw new Error('Fullscreen API unavailable');
        await fullscreenTarget.requestFullscreen();
    } catch (_error) {
        if (!window.pywebview?.api?.toggle_fullscreen) {
            setVoiceInputStatus('Full screen is unavailable in this browser.');
            return;
        }
        const result = await window.pywebview.api.toggle_fullscreen();
        nativeVisualFullscreen = Boolean(result?.fullscreen);
        document.body.classList.toggle('native-visual-fullscreen', nativeVisualFullscreen);
        syncFullscreenControls();
    }
}

document.getElementById('visual-fullscreen').addEventListener('click', toggleVisualFullscreen);
document.getElementById('mobile-visual-fullscreen').addEventListener('click', toggleVisualFullscreen);
const mobileVisualActions = document.getElementById('mobile-visual-actions');
const mobileVisualMenuToggle = document.getElementById('mobile-visual-menu-toggle');
function setMobileVisualMenuOpen(open) {
    mobileVisualActions.hidden = !open;
    mobileVisualMenuToggle.setAttribute('aria-expanded', String(open));
    mobileVisualMenuToggle.setAttribute('aria-label', open ? 'Hide visual controls' : 'Show visual controls');
}
mobileVisualMenuToggle.addEventListener('click', () => {
    if (mobileLayoutQuery.matches) setMobileVisualMenuOpen(mobileVisualActions.hidden);
});
function syncFullscreenControls() {
    const active = Boolean(document.fullscreenElement || nativeVisualFullscreen);
    document.getElementById('visual-fullscreen').textContent = active
        ? 'Exit full screen' : '⛶ Full screen';
    const mobileButton = document.getElementById('mobile-visual-fullscreen');
    mobileButton.textContent = active ? '×' : '⛶';
    mobileButton.title = active ? 'Exit fullscreen' : 'Enter fullscreen';
    mobileButton.setAttribute('aria-label', mobileButton.title);
}
document.addEventListener('fullscreenchange', () => {
    syncFullscreenControls();
});

const mobileSettingsPanel = document.getElementById('mobile-settings-panel');
const mobileSettingsToggle = document.getElementById('mobile-settings-toggle');
const mobilePersonaSelect = document.getElementById('mobile-persona');
const mobileVoiceSelect = document.getElementById('mobile-voice');
const mobileVoiceMethod = document.getElementById('mobile-voice-method');
let mobileSpeechCatalogLoaded = false;

function syncMobileSettings() {
    const method = ['always_on', 'wake_word', 'push_to_talk'].includes(voiceInputConfiguration.mode)
        ? voiceInputConfiguration.mode : 'push_to_talk';
    mobileVoiceMethod.value = method;
    document.getElementById('mobile-animation').value = preferences.visual_style || 'neural_core';
}

function fillMobileVoiceChoices(configuration = speechConfiguration) {
    const provider = configuration?.provider || 'automatic';
    const gemini = provider === 'automatic' || provider === 'gemini';
    const choices = gemini ? geminiSpeechVoices : provider === 'openai' ? openaiSpeechVoices : [];
    const selected = gemini
        ? configuration?.gemini_voice : configuration?.openai_voice;
    mobileVoiceSelect.innerHTML = '';
    if (!choices.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = provider === 'disabled' ? 'Speech is disabled on desktop' : 'No voices available';
        mobileVoiceSelect.append(option);
        mobileVoiceSelect.disabled = true;
        return;
    }
    mobileVoiceSelect.disabled = false;
    choices.forEach(voice => {
        const value = typeof voice === 'string' ? voice : voice.name;
        const description = typeof voice === 'string' ? '' : voice.description;
        const option = document.createElement('option');
        option.value = value;
        option.textContent = description ? `${value} — ${description}` : value[0].toUpperCase() + value.slice(1);
        mobileVoiceSelect.append(option);
    });
    mobileVoiceSelect.value = selected || mobileVoiceSelect.options[0]?.value || '';
}

function selectedMobileProfile() {
    const match = mobilePersonaSelect.value.match(/^slot:(\d)$/);
    return match ? savedPersonas[Number(match[1]) - 1] || null : null;
}

async function loadMobileProfiles() {
    const payload = await apiJson('/api/desktop/personality');
    savedPersonas = payload.saved_personas || [];
    mobilePersonaSelect.innerHTML = '';
    const current = document.createElement('option');
    current.value = 'current';
    current.textContent = `Current — ${payload.persona?.name || 'Petey'}`;
    mobilePersonaSelect.append(current);
    savedPersonas.forEach((profile, index) => {
        if (!profile) return;
        const option = document.createElement('option');
        option.value = `slot:${index + 1}`;
        option.textContent = `${index + 1}. ${profile.name || `Profile ${index + 1}`}`;
        mobilePersonaSelect.append(option);
    });
    mobilePersonaSelect.value = 'current';
    mobilePersonaSelect.disabled = mobilePersonaSelect.options.length === 1;
}

async function loadMobileSpeechCatalog() {
    if (mobileSpeechCatalogLoaded) {
        fillMobileVoiceChoices();
        return;
    }
    const payload = await apiJson('/api/desktop/speech');
    speechConfiguration = payload.configuration;
    geminiSpeechVoices = payload.gemini_voices || [];
    openaiSpeechVoices = payload.openai_voices || [];
    mobileSpeechCatalogLoaded = true;
    fillMobileVoiceChoices();
}

async function openMobileSettings() {
    syncMobileSettings();
    const conversation = activeConversation();
    fillConversationPersonaSelect(mobileChatPersonaSelect, conversation?.persona_slot);
    mobileChatPersonaSelect.disabled = !conversation;
    mobileSettingsPanel.hidden = false;
    mobileSettingsToggle.setAttribute('aria-expanded', 'true');
    try {
        await Promise.all([loadMobileSpeechCatalog(), loadMobileProfiles()]);
        fillMobileVoiceChoices();
    } catch (error) {
        setFeedback(document.getElementById('mobile-settings-status'), error.message, 'error');
    }
}

function closeMobileSettings() {
    mobileSettingsPanel.hidden = true;
    mobileSettingsToggle.setAttribute('aria-expanded', 'false');
}

mobileSettingsToggle.addEventListener('click', () => {
    if (mobileSettingsPanel.hidden) openMobileSettings();
    else closeMobileSettings();
});
document.getElementById('mobile-visual-settings').addEventListener('click', openMobileSettings);
document.getElementById('mobile-settings-close').addEventListener('click', closeMobileSettings);
mobilePersonaSelect.addEventListener('change', () => {
    fillMobileVoiceChoices(selectedMobileProfile()?.speech || speechConfiguration);
});
document.getElementById('mobile-visual-mode').addEventListener('click', async () => {
    setVoiceResponseEnabled(true);
    await savePreferences({visual_mode: true});
});
document.getElementById('mobile-show-chat').addEventListener('click', async () => {
    if (document.fullscreenElement) await document.exitFullscreen();
    closeMobileSettings();
    await savePreferences({visual_mode: false});
});
document.getElementById('mobile-settings-save').addEventListener('click', async () => {
    const button = document.getElementById('mobile-settings-save');
    const feedback = document.getElementById('mobile-settings-status');
    button.disabled = true;
    setFeedback(feedback, 'Saving…');
    try {
        const selectedProfile = selectedMobileProfile();
        if (selectedProfile) {
            const slot = Number(mobilePersonaSelect.value.split(':')[1]);
            const profilePayload = await apiJson(`/api/desktop/personality/slots/${slot}`, {
                method: 'POST',
            });
            speechConfiguration = profilePayload.speech;
            savedPersonas = profilePayload.saved_personas || savedPersonas;
            applyWakeCueConfiguration(profilePayload.voice_cues);
        }
        const speechUpdate = {};
        if (!mobileVoiceSelect.disabled && mobileVoiceSelect.value) {
            const provider = speechConfiguration?.provider || 'automatic';
            speechUpdate[provider === 'openai' ? 'openai_voice' : 'gemini_voice'] = mobileVoiceSelect.value;
        }
        if (Object.keys(speechUpdate).length) {
            const speechPayload = await apiJson('/api/desktop/speech', {
                method: 'PUT', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(speechUpdate),
            });
            speechConfiguration = speechPayload.configuration;
            applyWakeCueConfiguration(speechPayload.voice_cues);
            renderVoiceResponseToggle();
        }
        const voicePayload = await apiJson('/api/desktop/voice-input', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: mobileVoiceMethod.value}),
        });
        await stopVoiceInput();
        voiceInputConfiguration = {...voiceInputConfiguration, ...voicePayload.configuration};
        configureVoiceInputUI();
        if (['always_on', 'wake_word'].includes(voiceInputConfiguration.mode)) {
            await startContinuousVoiceInput();
        }
        await savePreferences({
            visual_style: document.getElementById('mobile-animation').value,
        });
        setFeedback(feedback, 'Saved.', 'success');
        window.setTimeout(closeMobileSettings, 500);
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
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

let addonsLoaded = false;

function renderAddons(payload) {
    const list = document.getElementById('addons-list');
    list.replaceChildren();
    document.getElementById('addons-directory').textContent = payload.directory || '';
    for (const addon of payload.addons || []) {
        const row = document.createElement('article');
        row.className = 'addon-row';
        const copy = document.createElement('div');
        const heading = document.createElement('div');
        heading.className = 'addon-heading';
        const name = document.createElement('strong');
        name.textContent = addon.name;
        const version = document.createElement('small');
        version.textContent = [addon.version, addon.source].filter(Boolean).join(' · ');
        heading.append(name, version);
        const description = document.createElement('p');
        description.textContent = addon.description;
        copy.append(heading, description);
        if (addon.error) {
            const error = document.createElement('small');
            error.className = 'addon-error';
            error.textContent = addon.error;
            copy.append(error);
        } else if (addon.restart_required) {
            const restart = document.createElement('small');
            restart.className = 'addon-restart';
            restart.textContent = 'Restart PETEY to apply this change.';
            copy.append(restart);
        }
        const controls = document.createElement('div');
        controls.className = 'addon-controls';
        const enabledLabel = document.createElement('label');
        enabledLabel.className = 'addon-toggle';
        const enabledText = document.createElement('span');
        enabledText.textContent = addon.configurable_enabled === false ? 'Available' : 'Enabled';
        const toggle = document.createElement('input');
        toggle.type = 'checkbox';
        toggle.role = 'switch';
        toggle.checked = Boolean(addon.enabled);
        // A broken enabled add-on must remain switchable off. Broken disabled
        // manifests cannot be enabled until their files are repaired.
        toggle.disabled = addon.configurable_enabled === false
            || Boolean(addon.error && !addon.enabled);
        toggle.setAttribute('aria-label', `Enable ${addon.name}`);
        toggle.addEventListener('change', async () => {
            if (toggle.checked && addon.source === 'user'
                    && !window.confirm(`Enable ${addon.name}? Installed add-ons run trusted Python code when PETEY restarts.`)) {
                toggle.checked = false;
                return;
            }
            toggle.disabled = true;
            try {
                await apiJson(`/api/desktop/addons/${encodeURIComponent(addon.id)}`, {
                    method: 'PUT', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({enabled: toggle.checked}),
                });
                document.getElementById('addons-status').textContent = 'Saved. Restart PETEY to apply add-on changes.';
                await loadAddons(true);
            } catch (error) {
                toggle.checked = !toggle.checked;
                document.getElementById('addons-status').textContent = error.message;
            } finally { toggle.disabled = false; }
        });
        enabledLabel.append(enabledText, toggle);
        controls.append(enabledLabel);
        const control = addon.petey_control;
        if (control) {
            const controlPanel = document.createElement('section');
            controlPanel.className = 'addon-control-panel';
            const saveControl = async (changes, success) => {
                try {
                    await apiJson(`/api/desktop/addons/${encodeURIComponent(addon.id)}`, {
                        method: 'PUT', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({petey_control: changes}),
                    });
                    document.getElementById('addons-status').textContent = success;
                    await loadAddons(true);
                } catch (error) {
                    document.getElementById('addons-status').textContent = error.message;
                    await loadAddons(true);
                }
            };
            const controlLabel = document.createElement('label');
            controlLabel.className = 'addon-toggle addon-control-master';
            const controlCopy = document.createElement('span');
            const controlTitle = document.createElement('strong');
            controlTitle.textContent = 'Allow Petey to control';
            const controlHint = document.createElement('small');
            controlHint.textContent = 'Lets the model invoke the enabled capabilities below.';
            controlCopy.append(controlTitle, controlHint);
            const controlToggle = document.createElement('input');
            controlToggle.type = 'checkbox';
            controlToggle.role = 'switch';
            controlToggle.checked = Boolean(control.enabled);
            controlToggle.disabled = !addon.enabled || Boolean(addon.error);
            controlToggle.addEventListener('change', () => saveControl(
                {enabled: controlToggle.checked},
                controlToggle.checked
                    ? `Petey can now control ${addon.name} on the selected surfaces.`
                    : `Petey can no longer control ${addon.name}.`,
            ));
            controlLabel.append(controlCopy, controlToggle);
            controlPanel.append(controlLabel);

            const surfaces = document.createElement('fieldset');
            surfaces.className = 'addon-control-surfaces';
            surfaces.disabled = !control.enabled;
            const legend = document.createElement('legend');
            legend.textContent = 'Allowed from';
            surfaces.append(legend);
            const surfaceLabels = {
                petey_desktop: 'Desktop', mobile_petey: 'Mobile',
                discord: 'Discord', petey_life: 'Petey Life',
            };
            for (const [surface, label] of Object.entries(surfaceLabels)) {
                const option = document.createElement('label');
                const input = document.createElement('input');
                input.type = 'checkbox';
                input.checked = Boolean(control.surfaces?.[surface]);
                input.addEventListener('change', () => saveControl(
                    {surfaces: {[surface]: input.checked}},
                    `${addon.name} ${label} access updated.`,
                ));
                option.append(input, document.createTextNode(label));
                surfaces.append(option);
            }
            controlPanel.append(surfaces);

            for (const capability of control.capabilities || []) {
                const capabilityRow = document.createElement('div');
                capabilityRow.className = 'addon-capability';
                const capabilityLabel = document.createElement('label');
                const capabilityToggle = document.createElement('input');
                capabilityToggle.type = 'checkbox';
                capabilityToggle.checked = Boolean(capability.enabled);
                capabilityToggle.disabled = !control.enabled;
                capabilityToggle.addEventListener('change', () => saveControl(
                    {capabilities: {[capability.id]: {enabled: capabilityToggle.checked}}},
                    `${capability.label} permission updated.`,
                ));
                capabilityLabel.append(capabilityToggle, document.createTextNode(capability.label));
                capabilityRow.append(capabilityLabel);
                if (capability.metered) {
                    const limitLabel = document.createElement('label');
                    limitLabel.className = 'addon-daily-limit';
                    limitLabel.append(document.createTextNode('Autonomous daily limit'));
                    const limit = document.createElement('input');
                    limit.type = 'number';
                    limit.min = '0';
                    limit.max = '1000';
                    limit.value = String(capability.daily_limit);
                    limit.disabled = !control.enabled || !capability.enabled;
                    limit.addEventListener('change', () => saveControl(
                        {capabilities: {[capability.id]: {daily_limit: Number(limit.value)}}},
                        `${capability.label} daily limit updated.`,
                    ));
                    const usage = document.createElement('small');
                    usage.textContent = `${capability.used_today} used today · direct requests bypass this limit`;
                    limitLabel.append(limit, usage);
                    capabilityRow.append(limitLabel);
                }
                controlPanel.append(capabilityRow);
            }
            controls.append(controlPanel);
        }
        row.append(copy, controls);
        list.append(row);
    }
    if (!(payload.addons || []).length) list.innerHTML = '<p class="muted">No add-ons are installed.</p>';
}

async function loadAddons(force = false) {
    if (addonsLoaded && !force) return;
    try {
        renderAddons(await apiJson('/api/desktop/addons'));
        addonsLoaded = true;
    } catch (error) {
        document.getElementById('addons-status').textContent = error.message;
    }
}

document.getElementById('open-addons-folder').addEventListener('click', async () => {
    const status = document.getElementById('addons-status');
    if (window.pywebview?.api?.open_addons_folder) {
        const result = await window.pywebview.api.open_addons_folder();
        status.textContent = result.ok ? `Opened ${result.path}` : result.error;
    } else {
        status.textContent = `Add add-on folders under ${document.getElementById('addons-directory').textContent}`;
    }
});

document.getElementById('restart-petey').addEventListener('click', async event => {
    const button = event.currentTarget;
    const status = document.getElementById('addons-status');
    if (!window.pywebview?.api?.restart_petey) {
        status.textContent = 'Restart PETEY from its launcher or stop and rerun the browser development command.';
        return;
    }
    button.disabled = true;
    status.textContent = 'Restarting PETEY…';
    try {
        const result = await window.pywebview.api.restart_petey();
        if (!result.ok) {
            status.textContent = result.error;
            button.disabled = false;
        }
    } catch (error) {
        status.textContent = error.message || 'Could not restart PETEY.';
        button.disabled = false;
    }
});

function showView(view) {
    if (mobileLayoutQuery.matches && view !== 'chat') view = 'chat';
    if (!document.getElementById(`view-${view}`)) return;
    document.querySelectorAll('.nav-button').forEach(item => item.classList.remove('active'));
    document.querySelectorAll('.app-view').forEach(item => item.classList.remove('active-view'));
    document.getElementById(`view-${view}`).classList.add('active-view');
    if (view === 'chat') ensureNeuralVisualizationRunning();
    const navView = document.getElementById(`view-${view}`).classList.contains('settings-view') ? 'settings' : view;
    document.querySelector(`.nav-button[data-view="${navView}"]`)?.classList.add('active');
    window.location.hash = view === 'settings' ? 'settings' : view;
    if (['providers', 'personality'].includes(view) && !personalityLoaded) loadPersonality();
    if (['providers', 'personality'].includes(view) && !speechSettingsLoaded) loadSpeechSettings();
    if (view === 'providers') {
        if (!aiProviderLoaded) loadAIProvider();
        else loadModelCatalogs();
    }
    if (['providers', 'microphone'].includes(view) && !voiceInputSettingsLoaded) loadVoiceInputSettings();
    if (view === 'providers' && !memoryProviderLoaded) loadMemoryProvider();
    if (view === 'providers' && !providerKeysLoaded) loadProviderKeys();
    if (view === 'media' && !mediaCatalogLoaded) loadMediaCatalog();
    if (view === 'media') loadMediaJobs();
    if (view === 'gallery') loadGallery();
    if (view === 'workspace' && !workspaceLoaded) loadWorkspaces();
    if (view === 'plan' && !planBuilderLoaded) loadPlanBuilder();
    if (view === 'tools' && !toolsLoaded) loadTools();
    if (view === 'discord' && typeof loadDiscord === 'function') loadDiscord();
    if (view === 'addons') loadAddons();
    if (view === 'knowledge') loadKnowledge();
    if (view === 'memory') {
        loadMemoryStats();
        if (!memoryProviderLoaded) loadMemoryProvider();
    }
    window.dispatchEvent(new CustomEvent('petey:view', {detail: {view}}));
}

const planCategories = ['chat', 'images', 'video', 'voice'];

function readPlanForm() {
    return {
        monthly_budget: Number(document.getElementById('plan-budget').value),
        quality: document.querySelector('.quality-option.active')?.dataset.planQuality || 'balanced',
        mix: Object.fromEntries(planCategories.map(category => [
            category, Number(document.getElementById(`plan-${category}`).value),
        ])),
        overage_mode: document.getElementById('plan-overage').value,
    };
}

function writePlanForm(plan) {
    document.getElementById('plan-budget').value = plan.monthly_budget;
    document.querySelectorAll('.quality-option').forEach(option => {
        const selected = option.dataset.planQuality === plan.quality;
        option.classList.toggle('active', selected);
        option.setAttribute('aria-checked', String(selected));
    });
    document.getElementById('plan-overage').value = plan.overage_mode || 'stop';
    for (const category of planCategories) {
        document.getElementById(`plan-${category}`).value = plan.mix[category];
    }
    updatePlanLabels();
}

function updatePlanLabels() {
    const plan = readPlanForm();
    document.getElementById('plan-budget-value').innerHTML = `$${plan.monthly_budget}<small>/month</small>`;
    let total = 0;
    for (const category of planCategories) {
        total += plan.mix[category];
        document.getElementById(`plan-${category}-value`).textContent = `${plan.mix[category]}%`;
    }
    document.getElementById('plan-mix-total').textContent = `${total}%`;
}

function rebalancePlanMix(changedCategory) {
    const changed = document.getElementById(`plan-${changedCategory}`);
    const changedValue = Number(changed.value);
    const others = planCategories.filter(category => category !== changedCategory);
    const available = 100 - changedValue;
    const currentTotal = others.reduce((total, category) => total + Number(document.getElementById(`plan-${category}`).value), 0);
    let assigned = 0;
    others.forEach((category, index) => {
        const control = document.getElementById(`plan-${category}`);
        const proposed = index === others.length - 1
            ? available - assigned
            : Math.round(available * (currentTotal ? Number(control.value) / currentTotal : 1 / others.length));
        control.value = Math.max(0, Math.min(available - assigned, proposed));
        assigned += Number(control.value);
    });
    updatePlanLabels();
}

function formatPlanUnits(value) {
    return Number(value || 0).toLocaleString(undefined, {maximumFractionDigits: 0});
}

function renderPlanEstimate(estimate) {
    const icons = {chat: '●', images: '◆', video: '▶', voice: '◖'};
    const qualityName = estimate.plan.quality.charAt(0).toUpperCase() + estimate.plan.quality.slice(1);
    document.getElementById('plan-impact-title').textContent = `${qualityName} at $${estimate.plan.monthly_budget} adds about`;
    for (const category of planCategories) {
        document.getElementById(`plan-impact-${category}`).textContent = formatPlanUnits(
            estimate.capabilities[category].estimated_units,
        );
    }
    document.getElementById('plan-live-impact').classList.remove('updating');
    const container = document.getElementById('plan-capabilities');
    container.replaceChildren(...planCategories.map(category => {
        const item = estimate.capabilities[category];
        const article = document.createElement('article');
        const icon = document.createElement('span');
        const amount = document.createElement('strong');
        const label = document.createElement('small');
        icon.textContent = icons[category];
        amount.textContent = `~${formatPlanUnits(item.estimated_units)}`;
        label.textContent = item.unit_label;
        article.append(icon, amount, label);
        return article;
    }));
    const breakdown = estimate.breakdown;
    const monthly = Math.max(1, breakdown.monthly_payment);
    document.getElementById('plan-ai-amount').textContent = `$${breakdown.ai_usage.toFixed(2)}`;
    document.getElementById('plan-platform-amount').textContent = `$${breakdown.platform_and_support.toFixed(2)}`;
    document.getElementById('plan-reserve-amount').textContent = `$${breakdown.payments_and_reserve.toFixed(2)}`;
    document.getElementById('plan-ai-bar').style.width = `${breakdown.ai_usage / monthly * 100}%`;
    document.getElementById('plan-platform-bar').style.width = `${breakdown.platform_and_support / monthly * 100}%`;
    document.getElementById('plan-reserve-bar').style.width = `${breakdown.payments_and_reserve / monthly * 100}%`;
    document.getElementById('plan-estimate-notice').textContent = estimate.estimate_notice;
}

async function requestPlanEstimate() {
    const requestNumber = ++planEstimateRequest;
    try {
        const estimate = await apiJson('/api/desktop/plan', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(readPlanForm()),
        });
        if (requestNumber === planEstimateRequest) renderPlanEstimate(estimate);
    } catch (error) {
        if (requestNumber === planEstimateRequest) setFeedback(document.getElementById('plan-save-status'), error.message, 'error');
    }
}

function schedulePlanEstimate() {
    clearTimeout(planEstimateTimer);
    const plan = readPlanForm();
    const qualityName = plan.quality.charAt(0).toUpperCase() + plan.quality.slice(1);
    document.getElementById('plan-impact-title').textContent = `${qualityName} estimate updating…`;
    document.getElementById('plan-live-impact').classList.add('updating');
    planEstimateTimer = setTimeout(requestPlanEstimate, 120);
}

async function loadPlanBuilder() {
    try {
        const estimate = await apiJson('/api/desktop/plan');
        writePlanForm(estimate.plan);
        renderPlanEstimate(estimate);
        planBuilderLoaded = true;
    } catch (error) {
        setFeedback(document.getElementById('plan-save-status'), error.message, 'error');
    }
}

const aiProviderSelect = document.getElementById('ai-provider');
const aiModelSelect = document.getElementById('ai-model-select');
const aiBaseUrlInput = document.getElementById('ai-base-url');

const aiProviderDefaults = {
    gemini: {model: 'gemini-2.5-flash', base_url: ''},
    openai: {model: 'gpt-4.1-mini', base_url: ''},
    local: {model: '', base_url: 'http://localhost:1234/v1'},
};

function configureAIProvider(provider = aiProviderSelect.value) {
    const saved = aiProviderConfiguration?.providers?.[provider] || aiProviderDefaults[provider];
    fillModelChoices(aiModelSelect, aiModelCatalogs.get(provider) || [], saved.model || aiProviderDefaults[provider].model);
    aiBaseUrlInput.value = saved.base_url || aiProviderDefaults.local.base_url;
    document.getElementById('ai-base-url-field').hidden = provider !== 'local';
    document.getElementById('local-provider-presets').hidden = provider !== 'local';
    document.getElementById('ai-thinking-enabled').checked = saved.thinking_enabled !== false;
    document.getElementById('ai-provider-badge').textContent = {gemini: 'Gemini', openai: 'OpenAI', local: 'Local'}[provider];
    document.getElementById('ai-provider-note').textContent = provider === 'local'
        ? 'Compatible with LM Studio, Ollama, and other servers exposing /v1/chat/completions.'
        : provider === 'openai'
            ? 'Requires an OpenAI API key; a ChatGPT subscription does not supply API credits.'
            : 'The shared Gemini key powers Gemini chat, vision, speech, and embeddings when selected.';
}

const aiModelCatalogs = new Map();
let modelCatalogRequest = 0;
function fillModelChoices(select, names, current = select.value) {
    select.replaceChildren();
    for (const name of [...new Set([current, ...names].filter(Boolean))]) {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        select.append(option);
    }
    if (!select.options.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No models available';
        select.append(option);
    }
    if (current) select.value = current;
}
async function loadModelCatalogs() {
    const requestNumber = ++modelCatalogRequest;
    const provider = aiProviderSelect.value;
    const feedback = document.getElementById('model-catalog-status');
    setFeedback(feedback, 'Loading models…');
    const providers = [provider];
    const results = await Promise.allSettled(providers.map(async name => {
        const params = new URLSearchParams({provider: name});
        if (name === 'local') params.set('base_url', aiBaseUrlInput.value.trim());
        const payload = await apiJson(`/api/desktop/ai-provider/models?${params}`);
        return {name, models: payload.models};
    }));
    if (requestNumber !== modelCatalogRequest) return;
    const errors = [];
    results.forEach((result, index) => {
        const name = providers[index];
        if (result.status === 'fulfilled') {
            aiModelCatalogs.set(name, result.value.models);
            if (name === provider) fillModelChoices(aiModelSelect, result.value.models);
            if (!result.value.models.length) errors.push(`${name}: no models returned.`);
        } else {
            errors.push(`${name}: ${result.reason.message}`);
        }
    });
    setFeedback(feedback, errors.join(' '), errors.length ? 'error' : '');
}

async function loadAIProvider() {
    const feedback = document.getElementById('ai-provider-status');
    try {
        const payload = await apiJson('/api/desktop/ai-provider');
        aiProviderConfiguration = payload.configuration;
        aiProviderSelect.value = payload.configuration.provider;
        configureAIProvider();
        aiProviderLoaded = true;
        loadModelCatalogs();
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
        model: aiModelSelect.value,
        base_url: aiBaseUrlInput.value.trim(),
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

aiProviderSelect.addEventListener('change', () => {
    configureAIProvider();
    loadModelCatalogs();
});
aiBaseUrlInput.addEventListener('change', loadModelCatalogs);
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
        loadModelCatalogs();
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

const voiceInputButton = document.getElementById('voice-input-button');
const visualVoiceInputButton = document.getElementById('visual-voice-input-button');
const visualVoiceInputLabel = document.getElementById('visual-voice-input-label');
const visualMicMuteButton = document.getElementById('visual-mic-mute-button');
const visualDictationForm = document.getElementById('visual-dictation-form');
const visualDictationInput = document.getElementById('visual-dictation-input');
const voiceInputModeSelect = document.getElementById('voice-input-mode');
const voiceInputProviderSelect = document.getElementById('voice-input-provider');

function setVoiceInputStatus(message) {
    document.getElementById('voice-input-status').textContent = message;
}

function configureVoiceInputUI() {
    const mode = voiceInputConfiguration?.mode || 'disabled';
    voiceInputButton.hidden = mode === 'disabled';
    visualVoiceInputButton.hidden = mode !== 'push_to_talk';
    visualMicMuteButton.hidden = mode === 'disabled';
    voiceInputButton.classList.toggle('muted', mobileLayoutQuery.matches && mobileVisualMicMuted);
    visualMicMuteButton.classList.toggle('muted', mobileVisualMicMuted);
    visualVoiceInputButton.classList.toggle('muted', mobileVisualMicMuted);
    visualMicMuteButton.setAttribute('aria-pressed', String(mobileVisualMicMuted));
    visualMicMuteButton.setAttribute('aria-label', mobileVisualMicMuted ? 'Unmute microphone' : 'Mute microphone');
    visualMicMuteButton.title = mobileVisualMicMuted ? 'Unmute microphone' : 'Mute microphone';
    if (mode !== 'push_to_talk') visualDictationForm.hidden = true;
    [voiceInputButton, visualVoiceInputButton].forEach(button => {
        button.classList.toggle('listening', voiceInputRunning && !microphoneCapturing);
        button.classList.toggle('recording', microphoneCapturing);
        button.classList.toggle('processing', voiceInputBusy);
        button.disabled = voiceInputBusy || (button === visualVoiceInputButton && mobileVisualMicMuted);
    });
    visualVoiceInputLabel.textContent = mobileVisualMicMuted
        ? 'Muted'
        : voiceInputBusy
        ? 'Transcribing…'
        : microphoneCapturing
            ? 'Release to send'
            : navigator.mediaDevices?.getUserMedia
                ? 'Hold to talk'
                : 'Keyboard mic';
    visualVoiceInputButton.setAttribute('aria-label', navigator.mediaDevices?.getUserMedia
        ? 'Hold to talk to Petey'
        : 'Open keyboard dictation');
    voiceInputButton.title = {
        push_to_talk: 'Hold to talk to Petey',
        always_on: voiceInputRunning ? 'Microphone is listening; click to stop' : 'Click to start microphone',
        wake_word: voiceInputRunning ? `Listening for ${voiceInputConfiguration.wake_word || 'Petey'}; click to stop` : 'Click to start wake-name listening',
    }[mode] || 'Microphone input';
    if (mobileLayoutQuery.matches && mobileVisualMicMuted && mode !== 'disabled') {
        voiceInputButton.title = 'Microphone muted · tap to unmute';
        voiceInputButton.setAttribute('aria-label', 'Unmute microphone');
    } else {
        voiceInputButton.setAttribute('aria-label', voiceInputButton.title);
    }
    if (mode !== 'disabled' && mobileVisualMicMuted && mobileLayoutQuery.matches) {
        setVoiceInputStatus('Microphone muted · tap the crossed-out mic to unmute');
    } else if (mode === 'disabled') {
        setVoiceInputStatus('Ready');
    } else if (voiceInputBusy) {
        setVoiceInputStatus('Transcribing…');
    } else if (microphoneCapturing) {
        const heardWake = mode !== 'wake_word' || voiceConversationActive;
        setVoiceInputStatus(mode === 'push_to_talk'
            ? 'Recording · release to send'
            : heardWake
                ? 'Listening to you…'
                : `Speech detected · waiting to hear “${voiceInputConfiguration.wake_word || 'Petey'}”…`);
    } else if (mode === 'push_to_talk') {
        setVoiceInputStatus('Hold the mic or Space to talk · Enter to send');
    } else if (voiceInputRunning && mode === 'wake_word' && voiceConversationAwaitingReply) {
        setVoiceInputStatus('Petey is responding · microphone stays ready for follow-up…');
    } else if (voiceInputRunning && mode === 'wake_word' && voiceConversationActive) {
        setVoiceInputStatus('Listening for your request…');
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
    const provider = voiceInputProviderSelect.value || 'deapi';
    const modelSelect = document.getElementById('voice-input-model');
    const availableModels = voiceInputModels[provider] || [];
    const selectedModel = provider === voiceInputConfiguration.provider
        ? voiceInputConfiguration.model
        : provider === 'gemini'
            ? voiceInputConfiguration.gemini_model
            : 'WhisperLargeV3';
    if (Array.from(modelSelect.options, option => option.value).join('|') !== availableModels.join('|')) {
        fillSelect(modelSelect, availableModels, selectedModel);
    }
    voiceInputProviderSelect.disabled = false;
    modelSelect.disabled = false;
    document.getElementById('voice-input-device').disabled = !enabled;
    document.getElementById('voice-input-sensitivity').disabled = !enabled;
    document.getElementById('voice-wake-word-field').hidden = mode !== 'wake_word';
    document.getElementById('voice-wake-delay-field').hidden = mode !== 'wake_word';
    document.getElementById('voice-submit-delay-field').hidden = !['always_on', 'wake_word'].includes(mode);
    document.getElementById('voice-follow-up-field').hidden = mode !== 'wake_word';
    document.getElementById('voice-input-badge').textContent = {
        disabled: 'Off', push_to_talk: 'Push to talk', always_on: 'Always on', wake_word: 'Wake name',
    }[mode];
    document.getElementById('voice-input-note').textContent = {
        disabled: 'Audio stays off until microphone input is enabled.',
        push_to_talk: 'Hold the mic button or Space outside the message box, speak, then release to transcribe and send.',
        always_on: 'Petey records each utterance and sends it to your selected transcription provider after the selected silence.',
        wake_word: `Say “${document.getElementById('voice-wake-word').value.trim() || 'Petey'}” and pause for an acknowledgement, then speak naturally. PETEY keeps listening briefly after each answer.`,
    }[mode];
}

async function loadVoiceInputSettings() {
    const feedback = document.getElementById('voice-input-settings-status');
    try {
        const payload = await apiJson('/api/desktop/voice-input');
        voiceInputConfiguration = {...voiceInputConfiguration, ...payload.configuration};
        voiceInputModels = payload.models || voiceInputModels;
        voiceInputModeSelect.value = voiceInputConfiguration.mode;
        voiceInputProviderSelect.value = voiceInputConfiguration.provider || 'deapi';
        document.getElementById('voice-wake-word').value = voiceInputConfiguration.wake_word || 'Petey';
        document.getElementById('voice-input-sensitivity').value = voiceInputConfiguration.sensitivity || 'normal';
        document.getElementById('voice-wake-delay').value = voiceInputConfiguration.wake_ack_delay_ms || 500;
        document.getElementById('voice-submit-delay').value = voiceInputConfiguration.submit_silence_ms || 800;
        document.getElementById('voice-follow-up-seconds').value = voiceInputConfiguration.follow_up_seconds || 8;
        await refreshMicrophoneDevices();
        configureVoiceInputSettings();
        configureVoiceInputUI();
        voiceInputSettingsLoaded = true;
        if (voiceInputConfiguration.mode !== 'disabled' && voiceInputConfiguration.provider === 'deapi' && !payload.deapi_has_api_key) {
            setFeedback(feedback, 'Add a media service key in Models & API keys before using media transcription.', 'error');
        } else if (voiceInputConfiguration.mode !== 'disabled' && voiceInputConfiguration.provider === 'gemini' && !payload.gemini_has_api_key) {
            setFeedback(feedback, 'Add a Gemini API key in Models & API keys before using the microphone.', 'error');
        }
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
}

document.getElementById('open-voice-cues-folder').addEventListener('click', async () => {
    const status = document.getElementById('voice-cues-status');
    await loadWakeCues(true);
    if (window.pywebview?.api?.open_voice_cues_folder) {
        const result = await window.pywebview.api.open_voice_cues_folder();
        status.textContent = result.ok
            ? `Opened ${result.path}. PETEY reloads clips when this window regains focus.`
            : result.error;
    } else {
        status.textContent = `Add clips on the PETEY computer under ${wakeCueConfiguration.directory}, then reload this page.`;
    }
});
window.addEventListener('focus', () => loadWakeCues());

voiceInputModeSelect.addEventListener('change', configureVoiceInputSettings);
voiceInputProviderSelect.addEventListener('change', configureVoiceInputSettings);
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
                provider: voiceInputProviderSelect.value,
                model: document.getElementById('voice-input-model').value,
                gemini_model: voiceInputProviderSelect.value === 'gemini'
                    ? document.getElementById('voice-input-model').value
                    : voiceInputConfiguration.gemini_model,
                wake_word: document.getElementById('voice-wake-word').value,
                device_id: document.getElementById('voice-input-device').value,
                sensitivity: document.getElementById('voice-input-sensitivity').value,
                wake_ack_delay_ms: Number(document.getElementById('voice-wake-delay').value),
                submit_silence_ms: Number(document.getElementById('voice-submit-delay').value),
                follow_up_seconds: Number(document.getElementById('voice-follow-up-seconds').value),
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
    if (microphoneStream?.active && microphoneContext && microphoneProcessor) return;
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
    try {
        microphoneContext = new AudioContextClass({sampleRate: 16000, latencyHint: 'interactive'});
    } catch (_error) {
        microphoneContext = new AudioContextClass({latencyHint: 'interactive'});
    }
    await microphoneContext.resume();
    microphoneSource = microphoneContext.createMediaStreamSource(microphoneStream);
    microphoneProcessor = microphoneContext.createScriptProcessor(2048, 1, 1);
    microphoneSilentOutput = microphoneContext.createGain();
    microphoneSilentOutput.gain.value = 0;
    microphoneProcessor.onaudioprocess = handleMicrophoneAudio;
    microphoneSource.connect(microphoneProcessor);
    microphoneProcessor.connect(microphoneSilentOutput);
    microphoneSilentOutput.connect(microphoneContext.destination);
    prepareWakeCueBuffers().catch(() => {});
    refreshMicrophoneDevices();
}

function handleMicrophoneAudio(event) {
    microphoneFrameCount += 1;
    const samples = event.inputBuffer.getChannelData(0);
    const now = performance.now();
    let energy = 0;
    for (let index = 0; index < samples.length; index += 1) energy += samples[index] * samples[index];
    const rms = Math.sqrt(energy / samples.length);
    const threshold = {high: .006, normal: .012, low: .025}[
        voiceInputConfiguration.sensitivity || 'normal'
    ];
    if (wakeCuePendingTimer && rms >= threshold * .55
        && performance.now() > wakeCuePendingAfter) {
        cancelPendingWakeAcknowledgement();
    }
    visualAudioEnergy = Math.max(visualAudioEnergy, Math.min(1, rms * 35));
    document.getElementById('voice-input-meter').style.width = `${Math.min(100, Math.max(1, rms * 900))}%`;
    if (microphoneTestActive) {
        document.getElementById('voice-input-test-status').textContent = rms > .006
            ? 'Input detected — microphone is working.' : 'Listening… speak into the microphone.';
    }
    if (voiceInputRunning && voiceInputConfiguration.mode === 'wake_word'
        && !voiceInputPlaybackBlocked && !voiceConversationActive
        && !voiceConversationAwaitingReply) {
        queueLocalWakeAudio(samples);
    }
    if (!voiceInputRunning || voiceInputBusy || voiceInputPlaybackBlocked) return;
    const mode = voiceInputConfiguration.mode;
    if (mode === 'push_to_talk') {
        if (microphoneCapturing) microphoneCapture.push(new Float32Array(samples));
        return;
    }
    if (mode === 'wake_word' && voiceConversationAwaitingReply) return;
    if (!microphoneCapturing) {
        microphonePreRoll.push(new Float32Array(samples));
        const preRollLimit = Math.max(2, Math.ceil((microphoneContext.sampleRate * .35) / samples.length));
        if (microphonePreRoll.length > preRollLimit) microphonePreRoll.shift();
        if (rms >= threshold) {
            microphoneCapture = microphonePreRoll.splice(0);
            microphoneCapturing = true;
            microphoneCaptureStartedAt = now;
            microphoneLastVoiceAt = now;
            if (mode === 'wake_word' && voiceConversationActive) {
                clearVoiceConversationFollowup();
            }
            configureVoiceInputUI();
        }
        return;
    }
    microphoneCapture.push(new Float32Array(samples));
    if (rms >= threshold * .55) microphoneLastVoiceAt = now;
    if ((now - microphoneLastVoiceAt > Number(voiceInputConfiguration.submit_silence_ms || 800)
            && now - microphoneCaptureStartedAt > 300)
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
    for (const chunk of chunks) {
        for (let index = 0; index < chunk.length; index += 1) {
            const clipped = Math.max(-1, Math.min(1, chunk[index]));
            view.setInt16(offset, clipped < 0 ? clipped * 32768 : clipped * 32767, true);
            offset += 2;
        }
    }
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
        const expression = wakeWordExpression(wakeWord);
        const match = transcript.match(new RegExp(`\\b(?:${expression})\\b[\\s,.:;!?—-]*(.*)$`, 'i'));
        if (match) {
            command = match[1].trim();
            beginVoiceConversation();
            if (!command) {
                if (Date.now() >= wakeCueAcknowledgedUntil) {
                    scheduleWakeAcknowledgement(performance.now(), 0);
                }
                setVoiceInputStatus(`Heard “${wakeWord}” · listening for your request…`);
                return;
            }
            cancelPendingWakeAcknowledgement();
        } else if (voiceConversationActive) {
            clearVoiceConversationFollowup();
        } else {
            setVoiceInputStatus(`Ignored speech without “${wakeWord}”.`);
            return;
        }
    }
    const existing = messageInput.value.trim();
    messageInput.value = existing ? `${existing} ${command}` : command;
    messageInput.dispatchEvent(new Event('input'));
    if (!sendButton.disabled) {
        if (voiceInputConfiguration.mode === 'wake_word') markVoiceConversationRequest();
        composer.requestSubmit();
    }
    else setVoiceInputStatus('Transcript added to the message box; Petey is still replying.');
}

function applyWakeCueConfiguration(payload, showStatus = false) {
    if (!payload) return;
    const status = document.getElementById('voice-cues-status');
    stopWakeAcknowledgement();
    wakeCueAudios.forEach(audio => {
        audio.onended = null;
        audio.onerror = null;
        audio.pause();
    });
    wakeCueConfiguration = payload;
    wakeCueBuffers = [];
    wakeCueAudios = (payload.clips || []).map(clip => {
        const audio = new Audio(clip.url);
        audio.preload = 'auto';
        audio.load();
        return audio;
    });
    prepareWakeCueBuffers();
    document.getElementById('voice-cues-directory').textContent = payload.directory;
    if (showStatus) {
        const source = payload.source_voice === payload.voice
            ? payload.voice : `${payload.source_voice} fallback`;
        status.textContent = wakeCueAudios.length
            ? `${wakeCueAudios.length} acknowledgement clip${wakeCueAudios.length === 1 ? '' : 's'} loaded from ${source}.`
            : 'Using the built-in spoken acknowledgements until audio files are added.';
    }
}

async function prepareWakeCueBuffers() {
    if (!microphoneContext || !wakeCueConfiguration?.clips?.length) return;
    const configuration = wakeCueConfiguration;
    const results = await Promise.all(configuration.clips.map(async clip => {
        try {
            const response = await fetch(clip.url);
            if (!response.ok) return null;
            const encoded = await response.arrayBuffer();
            return await microphoneContext.decodeAudioData(encoded.slice(0));
        } catch (_error) {
            return null;
        }
    }));
    if (wakeCueConfiguration === configuration) wakeCueBuffers = results;
}

async function loadWakeCues(showStatus = false) {
    const status = document.getElementById('voice-cues-status');
    try {
        const payload = await apiJson('/api/desktop/voice-cues');
        applyWakeCueConfiguration(payload, showStatus);
    } catch (error) {
        if (showStatus) status.textContent = error.message;
    }
}

function setWakeCuePlaybackActive(active, preserveCapture = false) {
    wakeCuePlaying = Boolean(active);
    voiceInputPlaybackBlocked = wakeCuePlaying || Boolean(activeSpeechCancel || activeChatAudio);
    if (active && !preserveCapture && microphoneCapturing && voiceInputConfiguration.mode !== 'push_to_talk') {
        finishVoiceCapture(true);
    }
    if (!active && microphoneCapturing) microphoneLastVoiceAt = performance.now();
}

function finishWakeCuePlayback() {
    wakeCueAudio = null;
    setWakeCuePlaybackActive(false);
    if (voiceConversationActive && !voiceConversationAwaitingReply) {
        armVoiceConversationListening('Listening for your request…');
    }
}

function stopWakeAcknowledgement() {
    cancelPendingWakeAcknowledgement();
    const audio = wakeCueAudio;
    wakeCueAudio = null;
    if (audio) {
        audio.onended = null;
        audio.onerror = null;
        if (typeof audio.stop === 'function') {
            try { audio.stop(); } catch (_error) { /* already stopped */ }
        } else {
            audio.pause();
            audio.currentTime = 0;
        }
    }
    if (wakeCuePlaying) window.speechSynthesis?.cancel?.();
    setWakeCuePlaybackActive(false);
}

function cancelPendingWakeAcknowledgement() {
    if (wakeCuePendingTimer) window.clearTimeout(wakeCuePendingTimer);
    wakeCuePendingTimer = null;
    wakeCuePendingAfter = 0;
}

function scheduleWakeAcknowledgement(continuedSpeechAfter, delay = Number(voiceInputConfiguration.wake_ack_delay_ms || 500)) {
    cancelPendingWakeAcknowledgement();
    wakeCuePendingAfter = Number(continuedSpeechAfter || performance.now());
    wakeCuePendingTimer = window.setTimeout(() => {
        wakeCuePendingTimer = null;
        if (microphoneLastVoiceAt > wakeCuePendingAfter
            || Date.now() < wakeCueAcknowledgedUntil) {
            wakeCuePendingAfter = 0;
            return;
        }
        wakeCuePendingAfter = 0;
        playWakeAcknowledgement(true);
    }, delay);
}

function clearVoiceConversationFollowup() {
    if (voiceConversationFollowupTimer) window.clearTimeout(voiceConversationFollowupTimer);
    voiceConversationFollowupTimer = null;
}

function scheduleVoiceConversationIdleTimeout() {
    clearVoiceConversationFollowup();
    if (!voiceConversationActive || voiceConversationAwaitingReply) return;
    const seconds = Number(voiceInputConfiguration.follow_up_seconds || 8);
    wakeWordArmedUntil = Date.now() + seconds * 1000;
    voiceConversationFollowupTimer = window.setTimeout(() => {
        voiceConversationFollowupTimer = null;
        if (microphoneCapturing || voiceInputBusy) {
            scheduleVoiceConversationIdleTimeout();
            return;
        }
        voiceConversationActive = false;
        voiceConversationAwaitingReply = false;
        wakeWordArmedUntil = 0;
        setVoiceInputStatus(`Listening for “${voiceInputConfiguration.wake_word || 'Petey'}”…`);
    }, seconds * 1000);
}

function beginVoiceConversation() {
    armVoiceConversationListening('Listening for your request…');
}

function markVoiceConversationRequest() {
    clearVoiceConversationFollowup();
    voiceConversationActive = true;
    voiceConversationAwaitingReply = true;
    wakeWordArmedUntil = 0;
    setVoiceInputStatus('Petey is responding · microphone stays ready for follow-up…');
}

function armVoiceConversationListening(statusMessage) {
    clearVoiceConversationFollowup();
    voiceConversationActive = true;
    voiceConversationAwaitingReply = false;
    setVoiceInputStatus(statusMessage);
    scheduleVoiceConversationIdleTimeout();
}

function openVoiceConversationFollowup() {
    if (!voiceConversationActive || !voiceInputRunning
        || voiceInputConfiguration.mode !== 'wake_word') return;
    armVoiceConversationListening('Listening for your follow-up…');
}

function stopVoiceConversation() {
    clearVoiceConversationFollowup();
    voiceConversationActive = false;
    voiceConversationAwaitingReply = false;
    wakeWordArmedUntil = 0;
}

function wakeWordExpression(wakeWord) {
    const variants = [String(wakeWord || 'Petey').trim() || 'Petey'];
    if (variants[0].toLowerCase() === 'petey') variants.push('Pete', 'Petty', 'Pity');
    return variants
        .map(value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
        .join('|');
}

function speakFallbackWakeCue() {
    const phrases = wakeCueConfiguration.fallback_phrases || ['Yeah?'];
    const phrase = phrases[Math.floor(Math.random() * phrases.length)] || 'Yeah?';
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) {
        finishWakeCuePlayback();
        return;
    }
    const utterance = new window.SpeechSynthesisUtterance(phrase);
    utterance.rate = 1.08;
    utterance.pitch = .92;
    utterance.onend = finishWakeCuePlayback;
    utterance.onerror = finishWakeCuePlayback;
    window.speechSynthesis.speak(utterance);
}

function playWakeAcknowledgement(preserveCapture = false) {
    cancelPendingWakeAcknowledgement();
    if (wakeCuePlaying || voiceInputPlaybackBlocked || activeSpeechCancel || activeChatAudio) return;
    wakeCueAcknowledgedUntil = Date.now() + 8000;
    setWakeCuePlaybackActive(true, preserveCapture);
    if (!wakeCueAudios.length) {
        speakFallbackWakeCue();
        return;
    }
    let index = Math.floor(Math.random() * wakeCueAudios.length);
    if (wakeCueAudios.length > 1 && index === lastWakeCueIndex) {
        index = (index + 1) % wakeCueAudios.length;
    }
    lastWakeCueIndex = index;
    const decoded = wakeCueBuffers[index];
    if (decoded && microphoneContext?.state === 'running') {
        const source = microphoneContext.createBufferSource();
        source.buffer = decoded;
        source.connect(microphoneContext.destination);
        source.onended = finishWakeCuePlayback;
        wakeCueAudio = source;
        source.start();
        return;
    }
    wakeCueAudio = wakeCueAudios[index];
    wakeCueAudio.currentTime = 0;
    wakeCueAudio.onended = finishWakeCuePlayback;
    const useFallback = () => {
        if (!wakeCueAudio) return;
        wakeCueAudio = null;
        speakFallbackWakeCue();
    };
    wakeCueAudio.onerror = useFallback;
    wakeCueAudio.play().catch(useFallback);
}

function queueLocalWakeAudio(samples) {
    if (!wakeDetectorSessionId) return;
    wakeDetectorChunks.push(new Float32Array(samples));
    wakeDetectorSampleCount += samples.length;
    while (wakeDetectorSampleCount > 32000 && wakeDetectorChunks.length > 1) {
        wakeDetectorSampleCount -= wakeDetectorChunks.shift().length;
    }
    if (wakeDetectorSampleCount >= 2048 && !wakeDetectorBusy) flushLocalWakeAudio();
}

async function flushLocalWakeAudio() {
    if (!wakeDetectorSessionId || wakeDetectorBusy || !wakeDetectorChunks.length) return;
    const sessionId = wakeDetectorSessionId;
    const chunks = wakeDetectorChunks;
    const sampleCount = wakeDetectorSampleCount;
    const audioSentAt = performance.now();
    wakeDetectorChunks = [];
    wakeDetectorSampleCount = 0;
    const pcm = new Int16Array(sampleCount);
    let offset = 0;
    for (const chunk of chunks) {
        for (let index = 0; index < chunk.length; index += 1) {
            const sample = Math.max(-1, Math.min(1, chunk[index]));
            pcm[offset] = sample < 0 ? sample * 32768 : sample * 32767;
            offset += 1;
        }
    }
    wakeDetectorBusy = true;
    try {
        const response = await fetch(`/api/desktop/voice-input/wake/${encodeURIComponent(sessionId)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/octet-stream',
                'X-Petey-Sample-Rate': String(microphoneContext?.sampleRate || 16000),
            },
            body: pcm.buffer,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || 'Local wake detector stopped.');
        if (payload.detected && Date.now() >= wakeCueAcknowledgedUntil
            && !wakeCuePendingTimer
            && !voiceInputPlaybackBlocked && !activeSpeechCancel && !activeChatAudio
            && !voiceConversationActive && !voiceConversationAwaitingReply) {
            beginVoiceConversation();
            setVoiceInputStatus(`Heard “${voiceInputConfiguration.wake_word || 'Petey'}” · listening for your request…`);
            scheduleWakeAcknowledgement(
                audioSentAt + 100,
                Number(voiceInputConfiguration.wake_ack_delay_ms || 500),
            );
        }
    } catch (_error) {
        if (wakeDetectorSessionId === sessionId) wakeDetectorSessionId = '';
    } finally {
        wakeDetectorBusy = false;
        if (wakeDetectorSampleCount >= 2048 && wakeDetectorSessionId) flushLocalWakeAudio();
    }
}

async function startLocalWakeDetector() {
    if (wakeDetectorStarting || wakeDetectorSessionId
        || voiceInputConfiguration.mode !== 'wake_word') return;
    wakeDetectorStarting = true;
    try {
        const payload = await apiJson('/api/desktop/voice-input/wake', {method: 'POST'});
        if (voiceInputRunning && voiceInputConfiguration.mode === 'wake_word') {
            wakeDetectorSessionId = payload.session_id || '';
            if (wakeDetectorSessionId) {
                setVoiceInputStatus(`Listening for “${voiceInputConfiguration.wake_word || 'Petey'}”…`);
            }
        }
    } catch (_error) {
        setVoiceInputStatus(`Listening for “${voiceInputConfiguration.wake_word || 'Petey'}”…`);
    } finally {
        wakeDetectorStarting = false;
    }
}

function stopLocalWakeDetector() {
    cancelPendingWakeAcknowledgement();
    const sessionId = wakeDetectorSessionId;
    wakeDetectorSessionId = '';
    wakeDetectorChunks = [];
    wakeDetectorSampleCount = 0;
    if (sessionId) {
        fetch(`/api/desktop/voice-input/wake/${encodeURIComponent(sessionId)}`, {
            method: 'DELETE', keepalive: true,
        }).catch(() => {});
    }
}

async function startContinuousVoiceInput() {
    if (!['always_on', 'wake_word'].includes(voiceInputConfiguration.mode)
        || (mobileLayoutQuery.matches && mobileVisualMicMuted)) return;
    try {
        await ensureMicrophone();
        if (mobileLayoutQuery.matches && mobileVisualMicMuted) {
            await stopVoiceInput();
            return;
        }
        voiceInputRunning = true;
        await startLocalWakeDetector();
        configureVoiceInputUI();
    } catch (error) {
        voiceInputRunning = false;
        configureVoiceInputUI();
        setVoiceInputStatus(`Microphone unavailable: ${error.message}`);
    }
}

async function stopVoiceInput() {
    voiceInputRunning = false;
    stopVoiceConversation();
    stopLocalWakeDetector();
    pushToTalkHeld = false;
    microphoneTestActive = false;
    if (microphoneCapturing) await finishVoiceCapture(true);
    if (microphoneSource) microphoneSource.disconnect();
    microphoneSource = null;
    if (microphoneProcessor) microphoneProcessor.disconnect();
    microphoneProcessor = null;
    if (microphoneSilentOutput) microphoneSilentOutput.disconnect();
    microphoneSilentOutput = null;
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
        status.textContent = 'Requesting microphone access…';
        const framesBeforeTest = microphoneFrameCount;
        await ensureMicrophone(document.getElementById('voice-input-device').value);
        microphoneTestActive = true;
        button.textContent = 'Stop test';
        status.textContent = 'Listening… speak into the microphone.';
        window.setTimeout(() => {
            if (microphoneTestActive && microphoneFrameCount === framesBeforeTest) {
                status.textContent = 'Microphone opened, but no audio is arriving. Check the selected input and system microphone permission.';
            }
        }, 1500);
    } catch (error) {
        status.textContent = `Microphone unavailable: ${error.message}`;
    } finally {
        button.disabled = false;
    }
});

navigator.mediaDevices?.addEventListener?.('devicechange', refreshMicrophoneDevices);

function setVoicePlaybackActive(active) {
    if (active && wakeCuePlaying) stopWakeAcknowledgement();
    voiceInputPlaybackBlocked = Boolean(active || wakeCuePlaying);
    if (!active) finishVisualCaption();
    if (active && microphoneCapturing && voiceInputConfiguration.mode !== 'push_to_talk') {
        finishVoiceCapture(true);
    }
}

voiceInputButton.addEventListener('click', async () => {
    if (mobileLayoutQuery.matches && mobileVisualMicMuted) {
        mobileVisualMicMuted = false;
        configureVoiceInputUI();
        if (['always_on', 'wake_word'].includes(voiceInputConfiguration.mode)) {
            await startContinuousVoiceInput();
        }
        return;
    }
    if (voiceInputConfiguration.mode === 'push_to_talk') return;
    if (voiceInputRunning) await stopVoiceInput();
    else await startContinuousVoiceInput();
});

visualMicMuteButton.addEventListener('click', async () => {
    visualMicMuteButton.disabled = true;
    mobileVisualMicMuted = !mobileVisualMicMuted;
    try {
        if (mobileVisualMicMuted) await stopVoiceInput();
        else if (['always_on', 'wake_word'].includes(voiceInputConfiguration.mode)) {
            await startContinuousVoiceInput();
        }
    } finally {
        visualMicMuteButton.disabled = false;
        configureVoiceInputUI();
    }
});

async function beginPushToTalk(event) {
    if (voiceInputConfiguration.mode !== 'push_to_talk' || voiceInputBusy
        || (mobileLayoutQuery.matches && mobileVisualMicMuted)) return;
    event.preventDefault();
    primeSpeechPlayback();
    if (!navigator.mediaDevices?.getUserMedia) {
        visualVoiceInputButton.hidden = true;
        visualDictationForm.hidden = false;
        visualDictationInput.focus();
        setVoiceInputStatus('Use the microphone on your phone keyboard, then choose Send.');
        return;
    }
    pushToTalkHeld = true;
    const sourceButton = event.currentTarget instanceof Element ? event.currentTarget : voiceInputButton;
    if (Number.isInteger(event.pointerId)) {
        try { sourceButton.setPointerCapture?.(event.pointerId); } catch (_error) { /* Pointer already released. */ }
    }
    try {
        await ensureMicrophone();
        if (!pushToTalkHeld) return;
        voiceInputRunning = true;
        beginVoiceCapture();
    } catch (error) {
        pushToTalkHeld = false;
        if (!window.isSecureContext) {
            setVoiceInputStatus('Microphone blocked: the phone does not trust this HTTPS certificate yet.');
        } else if (error?.name === 'NotAllowedError') {
            setVoiceInputStatus('Microphone blocked: allow it for this PETEY site and for your browser app, then try again.');
        } else {
            setVoiceInputStatus(`Microphone unavailable: ${error.message}`);
        }
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
visualVoiceInputButton.addEventListener('pointerdown', beginPushToTalk);
visualVoiceInputButton.addEventListener('pointerup', endPushToTalk);
visualVoiceInputButton.addEventListener('pointercancel', endPushToTalk);
voiceInputButton.addEventListener('keydown', event => {
    if (event.repeat || ![' ', 'Enter'].includes(event.key)) return;
    beginPushToTalk(event);
});
voiceInputButton.addEventListener('keyup', event => {
    if (![' ', 'Enter'].includes(event.key)) return;
    endPushToTalk(event);
});
visualVoiceInputButton.addEventListener('keydown', event => {
    if (event.repeat || ![' ', 'Enter'].includes(event.key)) return;
    beginPushToTalk(event);
});
visualVoiceInputButton.addEventListener('keyup', event => {
    if (![' ', 'Enter'].includes(event.key)) return;
    endPushToTalk(event);
});
visualDictationForm.addEventListener('submit', event => {
    event.preventDefault();
    const transcript = visualDictationInput.value.trim();
    if (!transcript) {
        visualDictationInput.focus();
        return;
    }
    visualDictationInput.value = '';
    visualDictationForm.hidden = true;
    visualVoiceInputButton.hidden = false;
    handleVoiceTranscript(transcript);
});
document.getElementById('visual-dictation-cancel').addEventListener('click', () => {
    visualDictationInput.value = '';
    visualDictationForm.hidden = true;
    visualVoiceInputButton.hidden = false;
    visualVoiceInputButton.focus();
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
const builtInOpenAISpeechModels = Array.from(
    document.getElementById('speech-openai-model').options,
    option => option.value,
);
const builtInOpenAISpeechVoices = Array.from(
    document.getElementById('speech-openai-voice').options,
    option => option.value,
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
    speechProviderSelect.value = configuration.provider || 'automatic';
    document.getElementById('speech-gemini-model').value = configuration.gemini_model || 'gemini-3.1-flash-tts-preview';
    document.getElementById('speech-gemini-voice').value = configuration.gemini_voice || 'Kore';
    document.getElementById('speech-openai-model').value = configuration.openai_model || 'gpt-4o-mini-tts';
    document.getElementById('speech-openai-voice').value = configuration.openai_voice || 'marin';
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
        openai_model: document.getElementById('speech-openai-model').value,
        openai_voice: document.getElementById('speech-openai-voice').value,
        style: document.getElementById('speech-style').value,
        consistent_voice: document.getElementById('speech-consistent-voice').checked,
        auto_speak: document.getElementById('speech-auto-speak').checked,
    };
}

function configureSpeechSettings() {
    const provider = speechProviderSelect.value;
    const automatic = provider === 'automatic';
    const gemini = provider === 'gemini' || automatic;
    const openai = provider === 'openai' || automatic;
    document.getElementById('speech-gemini-model-field').hidden = !gemini;
    document.getElementById('speech-gemini-voice-field').hidden = !gemini;
    document.getElementById('speech-openai-model-field').hidden = !openai;
    document.getElementById('speech-openai-voice-field').hidden = !openai;
    document.getElementById('speech-style-field').hidden = provider === 'disabled';
    document.getElementById('speech-consistent-voice-row').hidden = !gemini;
    document.getElementById('speech-auto-speak').disabled = provider === 'disabled';
    if (provider === 'disabled') document.getElementById('speech-auto-speak').checked = false;
    document.getElementById('speech-provider-badge').textContent = {
        automatic: 'Automatic', gemini: 'Gemini', openai: 'OpenAI', disabled: 'Disabled',
    }[provider];
    document.getElementById('speech-provider-note').textContent = provider === 'gemini'
        ? 'Gemini generates 24 kHz speech and follows natural-language directions for style, accent, pace, and tone.'
        : provider === 'openai'
            ? 'OpenAI uses GPT-4o Mini TTS and follows the delivery directions above.'
        : provider === 'disabled'
            ? 'Text to speech is unavailable on the Media page while disabled.'
            : 'Petey streams Gemini speech first and uses OpenAI only if Gemini fails.';
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
        openaiSpeechModels = payload.openai_models?.length
            ? payload.openai_models : builtInOpenAISpeechModels;
        openaiSpeechVoices = payload.openai_voices?.length
            ? payload.openai_voices : builtInOpenAISpeechVoices;
        fillSelect(document.getElementById('speech-gemini-model'), geminiSpeechModels, speechConfiguration.gemini_model);
        fillSelect(
            document.getElementById('speech-gemini-voice'), geminiSpeechVoices,
            speechConfiguration.gemini_voice,
            voice => `${voice.name} — ${voice.description}`,
        );
        fillSelect(document.getElementById('speech-openai-model'), openaiSpeechModels, speechConfiguration.openai_model);
        fillSelect(document.getElementById('speech-openai-voice'), openaiSpeechVoices, speechConfiguration.openai_voice, voice => voice[0].toUpperCase() + voice.slice(1));
        fillSpeechForm(speechConfiguration);
        speechSettingsLoaded = true;
        if (speechConfiguration.provider === 'gemini' && !payload.gemini_has_api_key) {
            setFeedback(feedback, 'Add a Gemini API key in AI provider settings before generating speech.', 'error');
        } else if (speechConfiguration.provider === 'openai' && !payload.openai_has_api_key) {
            setFeedback(feedback, 'Add an OpenAI API key in AI provider settings before generating speech.', 'error');
        }
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
}

speechProviderSelect.addEventListener('change', configureSpeechSettings);

function resetSpeechButton(button) {
    if (!button) return;
    button.disabled = false;
    button.textContent = 'Speak';
    button.classList.remove('speaking');
}

function getSpeechPlaybackContext() {
    if (!speechPlaybackContext || speechPlaybackContext.state === 'closed') {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) throw new Error('Audio playback is not supported by this browser.');
        try {
            speechPlaybackContext = new AudioContextClass({sampleRate: 24000});
        } catch (_error) {
            speechPlaybackContext = new AudioContextClass();
        }
    }
    return speechPlaybackContext;
}

function primeSpeechPlayback() {
    if (speechConfiguration?.provider === 'disabled') return;
    try {
        const context = getSpeechPlaybackContext();
        context.resume().catch(() => {});
        const buffer = context.createBuffer(1, 1, context.sampleRate);
        const source = context.createBufferSource();
        source.buffer = buffer;
        source.connect(context.destination);
        source.start();

        if (!speechUnlockAudio) {
            const silent = wavBlob([new Float32Array(160)], 16000);
            const url = URL.createObjectURL(silent);
            speechUnlockAudio = new Audio(url);
            speechUnlockAudio.volume = 0;
            speechUnlockAudio.addEventListener('ended', () => URL.revokeObjectURL(url), {once: true});
        }
        speechUnlockAudio.play().catch(() => {});
    } catch (_error) {
        // The visible speech action will report a useful error if playback is unavailable.
    }
}

function textForChatSpeech(text) {
    const source = String(text || '');
    const firstLine = source.split(/\r?\n/, 1)[0].trim();
    if (/^OpenCode run #\d+\b/.test(firstLine)) return firstLine;
    const heading = /(?:^|\r?\n)\s*Created files:\s*(?=\r?\n|$)/i.exec(source);
    const prose = heading ? source.slice(0, heading.index) : source;
    const spoken = prose.split(/\r?\n/)
        .filter(line => !/\/api\/addons\/petey-opencode\/artifacts\/\d+\/\d+/.test(line))
        .join('\n').trim();
    return spoken || (heading ? 'Created files are linked in chat.' : '');
}

async function speakChatText(text, button = null) {
    text = textForChatSpeech(text);
    if (!text) return;
    primeSpeechPlayback();
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
        let skipGemini = false;
        if (
            ['automatic', 'gemini'].includes(speechConfiguration?.provider)
            && String(speechConfiguration.gemini_model || '').startsWith('gemini-3.1-')
        ) {
            startVisualCaption(text);
            setVoicePlaybackActive(true);
            try {
                await playGeminiSpeechStream(text, button);
                return;
            } catch (error) {
                const automatic = speechConfiguration?.provider === 'automatic';
                if (!automatic && !/without returning audio/i.test(String(error?.message || error))) throw error;
                skipGemini = automatic;
                if (activeSpeechCancel) activeSpeechCancel();
                activeSpeechCancel = null;
                if (button) button.textContent = 'Preparing…';
                statusText.textContent = automatic
                    ? 'Gemini speech unavailable · trying OpenAI…'
                    : 'Speech stream was empty · retrying once…';
            } finally {
                setVoicePlaybackActive(false);
            }
        }
        const queued = await apiJson('/api/desktop/chat/speech', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text, skip_gemini: skipGemini}),
        });
        let job = queued.job;
        for (let attempt = 0; attempt < 300; attempt += 1) {
            if (job.status === 'completed' || job.status === 'failed') break;
            await new Promise(resolve => window.setTimeout(resolve, 1000));
            job = (await apiJson(`/api/desktop/media/jobs/${encodeURIComponent(job.id)}`)).job;
            const elapsed = attempt + 1;
            const phase = job.status === 'queued' ? 'Voice queued' : 'Generating voice';
            if (button) button.textContent = `${phase} · ${elapsed}s`;
            statusText.textContent = `Speech: ${phase.toLowerCase()} with ${speechConfiguration?.provider || 'automatic'}…`;
        }
        if (job.status === 'failed') throw new Error(job.error || 'Speech generation failed.');
        if (job.status !== 'completed') throw new Error('Speech generation timed out.');
        const source = job.result?.result_url
            || `/api/desktop/media/jobs/${encodeURIComponent(job.id)}/file`;
        const response = await fetch(source);
        if (!response.ok) throw new Error(`Could not load generated speech (${response.status}).`);
        const encodedAudio = await response.arrayBuffer();
        const context = getSpeechPlaybackContext();
        await context.resume();
        if (context.state !== 'running') {
            throw new Error('Chrome paused audio playback. Press the microphone once and try again.');
        }
        const audio = await context.decodeAudioData(encodedAudio.slice(0));
        const sourceNode = context.createBufferSource();
        sourceNode.buffer = audio;
        sourceNode.connect(context.destination);
        activeChatAudio = sourceNode;
        activeSpeechCancel = () => {
            try { sourceNode.stop(); } catch (_error) { /* already stopped */ }
            activeChatAudio = null;
            setVoicePlaybackActive(false);
        };
        if (button) {
            button.disabled = false;
            button.textContent = 'Stop';
            button.classList.add('speaking');
        }
        let resolvePlayback;
        const playbackFinished = new Promise(resolve => { resolvePlayback = resolve; });
        sourceNode.addEventListener('ended', () => {
            if (activeChatAudio === sourceNode) activeChatAudio = null;
            activeSpeechCancel = null;
            setVoicePlaybackActive(false);
            if (activeSpeechButton === button) activeSpeechButton = null;
            resetSpeechButton(button);
            resolvePlayback();
        }, {once: true});
        startVisualCaption(text);
        setVoicePlaybackActive(true);
        sourceNode.start();
        await playbackFinished;
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
    const context = getSpeechPlaybackContext();
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
        setVoicePlaybackActive(false);
        resolvePlayback();
    };
    if (button) {
        button.textContent = 'Stop';
        button.classList.add('speaking');
    }
    await context.resume();
    if (context.state !== 'running') {
        throw new Error('Chrome paused audio playback. Press the microphone once and try again.');
    }
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
    activeSpeechCancel = null;
    if (activeSpeechButton === button) activeSpeechButton = null;
    resetSpeechButton(button);
}

document.querySelectorAll('.nav-button').forEach(button => {
    button.addEventListener('click', () => showView(button.dataset.view));
});

document.getElementById('plan-budget').addEventListener('input', () => {
    updatePlanLabels();
    schedulePlanEstimate();
});
for (const category of planCategories) {
    document.getElementById(`plan-${category}`).addEventListener('input', () => {
        rebalancePlanMix(category);
        schedulePlanEstimate();
    });
}
document.querySelectorAll('.quality-option').forEach(control => {
    control.addEventListener('click', () => {
        document.querySelectorAll('.quality-option').forEach(option => {
            const selected = option === control;
            option.classList.toggle('active', selected);
            option.setAttribute('aria-checked', String(selected));
        });
        schedulePlanEstimate();
    });
});
document.getElementById('plan-overage').addEventListener('change', schedulePlanEstimate);
document.getElementById('save-plan-preview').addEventListener('click', async event => {
    const button = event.currentTarget;
    const feedback = document.getElementById('plan-save-status');
    button.disabled = true;
    setFeedback(feedback, 'Saving your plan preview…');
    try {
        const estimate = await apiJson('/api/desktop/plan', {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(readPlanForm()),
        });
        writePlanForm(estimate.plan);
        renderPlanEstimate(estimate);
        setFeedback(feedback, 'Plan preview saved on this device.', 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
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
        const provider = persona?.speech?.provider || '';
        const providerName = {
            automatic: 'Automatic', gemini: 'Gemini', openai: 'OpenAI', disabled: 'No speech',
        }[provider] || '';
        const voice = provider === 'openai'
            ? persona?.speech?.openai_voice : persona?.speech?.gemini_voice;
        description.textContent = persona
            ? [persona.role_tag, providerName, provider === 'disabled' ? '' : voice]
                .filter(Boolean).join(' · ')
            : 'Empty';
        description.title = description.textContent;
        const actions = document.createElement('div');
        actions.className = 'persona-slot-actions';
        const load = document.createElement('button');
        load.type = 'button';
        load.textContent = 'Load';
        load.disabled = !persona;
        load.addEventListener('click', () => activatePersonaSlot(index + 1, load));
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
            clear.setAttribute('aria-label', clear.title);
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
        await refreshConversationPersonaOptions();
        setFeedback(feedback, `Saved the complete Petey profile to slot ${slot}.`, 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
}

async function activatePersonaSlot(slot, button) {
    const feedback = document.getElementById('personality-status');
    button.disabled = true;
    try {
        const result = await apiJson(`/api/desktop/personality/slots/${slot}`, {method: 'POST'});
        speechConfiguration = result.speech;
        fillPersona({...result.persona, speech: result.speech, preset_key: ''});
        speechSettingsLoaded = true;
        mediaCatalogLoaded = false;
        mediaModelsCache.delete('txt2audio');
        applyWakeCueConfiguration(result.voice_cues);
        await refreshConversationPersonaOptions();
        setFeedback(feedback, `Petey profile ${slot} is now active.`, 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
}

async function clearPersonaSlot(slot) {
    if (!window.confirm(`Clear saved persona slot ${slot}?`)) return;
    const feedback = document.getElementById('personality-status');
    try {
        const result = await apiJson(`/api/desktop/personality/slots/${slot}`, {method: 'DELETE'});
        savedPersonas = result.saved_personas || [];
        renderSavedPersonaSlots();
        await refreshConversationPersonaOptions();
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
        mediaModelsCache.delete('txt2audio');
        applyWakeCueConfiguration(result.voice_cues);
        await refreshConversationPersonaOptions();
        setFeedback(feedback, 'Petey profile saved — instructions, style, and voice are active.', 'success');
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
const mediaNonimageSource = document.getElementById('media-nonimage-source');
const mediaPrompt = document.getElementById('media-prompt');
const mediaStatus = document.getElementById('media-status');
let mediaModelRequest = 0;
let selectedVisualImage = null;
let selectedMediaImageFile = null;
let mediaSelectionUrl = '';
let mediaPriceTimer = null;
let mediaPriceRequest = 0;
let mediaPriceController = null;
const pricedMediaOperations = new Set(['txt2img', 'img2img', 'txt2video', 'img2video', 'img-rmbg', 'img-upscale']);
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
        openaiSpeechModels = speechPayload.openai_models?.length
            ? speechPayload.openai_models : builtInOpenAISpeechModels;
        openaiSpeechVoices = speechPayload.openai_voices?.length
            ? speechPayload.openai_voices : builtInOpenAISpeechVoices;
        speechSettingsLoaded = true;
        mediaSelectedModels = payload.selected_models || {};
        const speechOption = mediaOperation.querySelector('option[value="txt2audio"]');
        speechOption.disabled = speechConfiguration.provider === 'disabled';
        if (speechOption.disabled && mediaOperation.value === 'txt2audio') mediaOperation.value = 'txt2img';
        mediaCatalogLoaded = true;
        configureMediaOperation(true);
        startMediaPolling();
        refreshDeapiBalance();
        setFeedback(connection, payload.configured ? 'Media service connected' : 'Media service not configured', payload.configured ? 'success' : 'error');
    } catch (error) {
        setFeedback(connection, error.message, 'error');
    }
}

function configureMediaOperation(preserveSource = false) {
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
        if (!isImage) mediaNonimageSource.accept = accepts[config.source];
    }
    if (!preserveSource) clearMediaSourceSelection();
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
    const gemini = ['automatic', 'gemini'].includes(speechConfiguration?.provider);
    const openai = speechConfiguration?.provider === 'openai';
    const voiceSelect = document.getElementById('media-voice');
    if (gemini) {
        fillSelect(
            voiceSelect, geminiSpeechVoices, speechConfiguration.gemini_voice,
            voice => `${voice.name} — ${voice.description}`,
        );
    } else if (openai) {
        fillSelect(
            voiceSelect, openaiSpeechVoices,
            speechConfiguration.openai_voice || 'marin',
            voice => voice[0].toUpperCase() + voice.slice(1),
        );
    }
    document.getElementById('media-speed-field').hidden = gemini || openai;
    document.getElementById('media-speech-style-field').hidden = false;
    document.getElementById('media-speech-style').value = speechConfiguration.style || '';
}

async function loadMediaModels(operation) {
    const requestNumber = ++mediaModelRequest;
    const renderModels = models => {
        mediaModel.innerHTML = '<option value="">Auto — first available</option>';
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.slug;
            option.textContent = model.name || model.slug;
            mediaModel.append(option);
        });
        const preferredModel = operation === 'txt2audio'
            ? speechConfiguration?.provider === 'openai'
                ? speechConfiguration.openai_model
                : speechConfiguration.gemini_model
            : mediaSelectedModels[operation];
        mediaModel.value = preferredModel || '';
        mediaModel.disabled = false;
        scheduleMediaEstimate();
        if (!models.length) setFeedback(mediaStatus, 'No compatible models were returned. Check the media service configuration.', 'error');
    };
    if (operation === 'txt2audio') {
        const speechModels = speechConfiguration?.provider === 'openai'
            ? openaiSpeechModels : geminiSpeechModels;
        renderModels(speechModels.map(model => ({slug: model, name: model})));
        return;
    }
    if (mediaModelsCache.has(operation)) {
        renderModels(mediaModelsCache.get(operation));
        return;
    }
    mediaModel.disabled = true;
    mediaModel.innerHTML = '<option value="">Loading compatible models…</option>';
    scheduleMediaEstimate();
    try {
        const payload = await apiJson(`/api/desktop/media/models/${encodeURIComponent(operation)}`);
        if (requestNumber !== mediaModelRequest) return;
        const models = payload.models || [];
        mediaModelsCache.set(operation, models);
        renderModels(models);
    } catch (error) {
        if (requestNumber !== mediaModelRequest) return;
        mediaModel.innerHTML = '<option value="">Models unavailable</option>';
        scheduleMediaEstimate();
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
    selectedMediaImageFile = null;
    mediaNonimageSource.value = '';
    if (mediaSelectionUrl?.startsWith('blob:')) URL.revokeObjectURL(mediaSelectionUrl);
    mediaSelectionUrl = '';
    document.getElementById('media-image-selection').hidden = true;
    document.getElementById('clear-media-image').hidden = true;
    scheduleMediaEstimate();
}

function showMediaImageSelection(file, previewUrl) {
    if (mediaSelectionUrl?.startsWith('blob:')) URL.revokeObjectURL(mediaSelectionUrl);
    mediaSelectionUrl = previewUrl;
    document.getElementById('media-image-selection-preview').src = previewUrl;
    document.getElementById('media-image-selection-name').textContent = `${file.name} · ${formatFileSize(file.size)}`;
    document.getElementById('media-image-selection').hidden = false;
    document.getElementById('clear-media-image').hidden = false;
    scheduleMediaEstimate();
}

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
        selectedMediaImageFile = null;
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
            scheduleMediaEstimate();
            setFeedback(mediaStatus, 'Prompt enhanced. Review it, then generate.', 'success');
        }
    } catch (error) {
        setFeedback(mediaStatus, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

function mediaParameters() {
    const [width, height] = document.getElementById('media-size').value.split('x');
    return {
        width,
        height,
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

function scheduleMediaEstimate() {
    window.clearTimeout(mediaPriceTimer);
    mediaPriceController?.abort();
    const requestNumber = ++mediaPriceRequest;
    const button = document.getElementById('generate-media');
    const note = document.getElementById('media-price-note');
    button.textContent = 'Generate';
    button.title = '';
    note.hidden = true;
    note.textContent = '';
    const operation = mediaOperation.value;
    if (['txt2audio', 'txt2music'].includes(operation)) return;
    note.hidden = false;
    if (!pricedMediaOperations.has(operation)) {
        note.textContent = 'Estimate unavailable for this operation.';
        return;
    }
    if (mediaModel.disabled) {
        note.textContent = 'Select an available model to estimate cost.';
        return;
    }
    if (['img-rmbg', 'img-upscale'].includes(operation) && !selectedVisualImage && !selectedMediaImageFile) {
        note.textContent = 'Choose a source image to estimate cost.';
        return;
    }
    button.textContent = 'Generate · estimating…';
    note.textContent = 'Looking up the price for these settings…';
    mediaPriceTimer = window.setTimeout(async () => {
        const controller = new AbortController();
        mediaPriceController = controller;
        const body = new FormData();
        body.append('operation', operation);
        body.append('model_slug', mediaModel.value);
        body.append('parameters', JSON.stringify(mediaParameters()));
        body.append('prompt', mediaPrompt.value);
        if (['img-rmbg', 'img-upscale'].includes(operation)) {
            if (selectedMediaImageFile) body.append('source', selectedMediaImageFile);
            if (selectedVisualImage) {
                body.append('source_browser_token', selectedVisualImage.token);
                body.append('source_browser_path', selectedVisualImage.path);
            }
        }
        try {
            const quote = await apiJson('/api/desktop/media/estimate', {method: 'POST', body, signal: controller.signal});
            if (requestNumber !== mediaPriceRequest) return;
            const price = Number(quote.price);
            if (quote.price == null || !Number.isFinite(price) || price < 0 || quote.currency !== 'USD') throw new Error('Invalid price estimate.');
            const amount = price > 0 && price < 0.000001 ? '<$0.000001'
                : `$${price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 6})}`;
            button.textContent = `Generate · ~${amount}`;
            const model = mediaModelsCache.get(operation)?.find(item => item.slug === quote.model_slug);
            note.textContent = `Estimate for ${model?.name || quote.model_slug}. A fallback model may cost differently.`;
            const parameters = quote.parameters || {};
            button.title = [
                parameters.width && parameters.height ? `${parameters.width} × ${parameters.height}` : '',
                parameters.steps ? `${parameters.steps} steps` : '',
                parameters.frames ? `${parameters.frames} frames at ${parameters.fps} FPS` : '',
            ].filter(Boolean).join(' · ');
        } catch (error) {
            if (requestNumber !== mediaPriceRequest || error.name === 'AbortError') return;
            button.textContent = 'Generate';
            note.textContent = 'Estimate unavailable. You can still generate.';
            button.title = error.message;
        }
    }, 450);
}

mediaModel.addEventListener('change', scheduleMediaEstimate);
for (const id of ['media-size', 'media-steps', 'media-guidance', 'media-frames', 'media-fps', 'media-scale', 'media-prompt']) {
    document.getElementById(id).addEventListener('input', scheduleMediaEstimate);
    document.getElementById(id).addEventListener('change', scheduleMediaEstimate);
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
    if (localItem?.local_filename && localItem.id) {
        openLink.dataset.galleryItemId = String(localItem.id);
    } else {
        delete openLink.dataset.galleryItemId;
    }
    openLink.hidden = !localUrl && !payload.result_url;
}

configureExternalOpenLink(document.getElementById('media-open-result'), 'generated file');

document.getElementById('generate-media').addEventListener('click', async () => {
    const operation = mediaOperation.value;
    const config = mediaOperationUI[operation];
    const file = config.source === 'image'
        ? selectedMediaImageFile
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

function stopMediaPolling() {
    if (!mediaPollTimer) return;
    window.clearInterval(mediaPollTimer);
    mediaPollTimer = null;
}

async function loadMediaJobs() {
    if (mediaJobsLoading) return;
    mediaJobsLoading = true;
    const container = document.getElementById('media-jobs');
    try {
        const payload = await apiJson('/api/desktop/media/jobs');
        const jobs = payload.jobs || [];
        const hasActiveJobs = jobs.some(job => ['queued', 'running'].includes(job.status));
        if (!hasActiveJobs) stopMediaPolling();
        const signature = JSON.stringify(jobs.slice(0, 12).map(job => [
            job.id, job.status, job.provider_status, job.progress, job.preview_url, job.error,
        ]));
        if (signature === lastMediaJobsSignature) return;
        lastMediaJobsSignature = signature;
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
    } finally {
        mediaJobsLoading = false;
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

async function useGalleryImage(item, operation, button) {
    button.disabled = true;
    try {
        const response = await fetch(`/api/desktop/gallery/file/${encodeURIComponent(item.id)}`);
        if (!response.ok) throw new Error('This local image is unavailable. Refresh the gallery and try again.');
        const blob = await response.blob();
        if (blob.size > 25 * 1024 * 1024) throw new Error('This image exceeds the 25 MB source limit.');
        const file = new File([blob], item.local_filename, {type: blob.type || item.content_type});
        rememberMediaPrompt(activeMediaOperation);
        mediaOperation.value = operation;
        activeMediaOperation = operation;
        configureMediaOperation();
        selectedMediaImageFile = file;
        showMediaImageSelection(file, URL.createObjectURL(file));
        showView('media');
        setFeedback(mediaStatus, 'Source image selected. Review the settings, then generate.', 'success');
        if (mediaOperationUI[operation].prompt) mediaPrompt.focus();
        else document.getElementById('generate-media').focus();
    } catch (error) {
        window.alert(error.message);
    } finally {
        button.disabled = false;
    }
}

document.addEventListener('click', event => {
    document.querySelectorAll('.gallery-menu[open]').forEach(menu => {
        if (!menu.contains(event.target)) menu.open = false;
    });
});
document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    document.querySelectorAll('.gallery-menu[open]').forEach(menu => {
        menu.open = false;
        menu.querySelector('summary').focus();
    });
});

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
    if (item.kind === 'image') {
        const menu = document.createElement('details');
        menu.className = 'gallery-menu';
        const toggle = document.createElement('summary');
        toggle.textContent = '☰';
        toggle.setAttribute('aria-label', 'Use image in media generation');
        toggle.title = 'Use image…';
        const options = document.createElement('div');
        options.className = 'gallery-menu-options';
        for (const [operation, label] of [
            ['img2img', 'Restyle image (img2img)'],
            ['img2video', 'Animate image (img2vid)'],
            ['img-rmbg', 'Remove background'],
            ['img-upscale', 'Upscale image'],
        ]) {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = label;
            button.disabled = !item.local_filename;
            button.addEventListener('click', async () => {
                await useGalleryImage(item, operation, button);
                menu.open = false;
            });
            options.append(button);
        }
        if (!item.local_filename) {
            const hint = document.createElement('p');
            hint.textContent = 'A local copy is needed to reuse this image.';
            options.append(hint);
        }
        menu.append(toggle, options);
        preview.append(menu);
    }

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
    const frameInterval = 1000 / (reducedMotion ? 20 : 40);

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
        neuralAnimationFrame = null;
        const chatVisible = document.getElementById('view-chat').classList.contains('active-view');
        if (document.hidden || document.getElementById('visual-chat').hidden || !chatVisible) return;
        if (time - previousTime < frameInterval) {
            neuralAnimationFrame = window.requestAnimationFrame(draw);
            return;
        }
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
        neuralAnimationFrame = window.requestAnimationFrame(draw);
    };
    neuralDraw = draw;
    ensureNeuralVisualizationRunning();
}

startNeuralVisualization();
document.addEventListener('visibilitychange', ensureNeuralVisualizationRunning);


let providerKeysLoaded = false;
const credentialNames = {gemini: 'Google Gemini', openai: 'OpenAI', local: 'Local / compatible server', deapi: 'deAPI media'};
function renderProviderKeyStatus(providers) {
    for (const [provider, status] of Object.entries(providers)) {
        document.getElementById(`credential-status-${provider}`).textContent = {
            saved: 'Saved in local settings', environment: 'Configured by environment', none: 'Not configured',
        }[status.source];
        document.getElementById(`credential-clear-${provider}`).disabled = !status.has_saved_key;
    }
}
async function loadProviderKeys() {
    try {
        const payload = await apiJson('/api/desktop/provider-keys');
        renderProviderKeyStatus(payload.providers);
        providerKeysLoaded = true;
    } catch (error) {
        setFeedback(document.getElementById('provider-keys-status'), error.message, 'error');
    }
}
for (const [provider, name] of Object.entries(credentialNames)) {
    const card = document.createElement('div');
    card.className = 'credential-card';
    const label = document.createElement('label');
    const title = document.createElement('span'); title.textContent = name;
    const status = document.createElement('small'); status.id = `credential-status-${provider}`;
    status.textContent = 'Loading…';
    const input = document.createElement('input');
    input.id = `credential-key-${provider}`; input.type = 'password'; input.autocomplete = 'new-password';
    input.maxLength = 4096; input.placeholder = 'Leave blank to keep existing key';
    label.append(title, status, input);
    const actions = document.createElement('div'); actions.className = 'inline-actions';
    for (const clear of [false, true]) {
        const button = document.createElement('button'); button.type = 'button';
        button.id = `credential-${clear ? 'clear' : 'save'}-${provider}`;
        button.className = clear ? 'text-button' : 'secondary-button';
        button.textContent = clear ? 'Clear saved key' : 'Save key';
        if (clear) button.disabled = true;
        button.addEventListener('click', async () => {
            if (clear && !window.confirm(`Clear the saved ${name} key? Environment keys are unaffected.`)) return;
            const feedback = document.getElementById('provider-keys-status');
            button.disabled = true;
            try {
                const payload = await apiJson('/api/desktop/provider-keys', {
                    method: 'PUT', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({provider, api_key: input.value, clear_api_key: clear}),
                });
                input.value = '';
                renderProviderKeyStatus(payload.providers);
                mediaModelsCache.clear(); mediaCatalogLoaded = false;
                // Refresh credential indicators without overwriting unsaved provider/model choices.
                const ai = await apiJson('/api/desktop/ai-provider');
                aiProviderConfiguration = ai.configuration;
                loadModelCatalogs();
                setFeedback(feedback, `${name} key ${clear ? 'cleared' : 'saved'}.`, 'success');
            } catch (error) { setFeedback(feedback, error.message, 'error'); }
            finally { if (!clear) button.disabled = false; else await loadProviderKeys(); }
        });
        actions.append(button);
    }
    card.append(label, actions);
    document.getElementById('provider-key-fields').append(card);
}
document.querySelector('[data-open-media]').addEventListener('click', () => showView('media'));

function renderFilesystemTool(filesystem) {
    const enabled = Boolean(filesystem.enabled);
    const connected = Boolean(filesystem.connected);
    const toggle = document.getElementById('filesystem-tool-enabled');
    toggle.checked = enabled;
    const badge = document.getElementById('filesystem-tool-badge');
    badge.textContent = connected ? 'Connected' : enabled ? 'Enabled' : 'Off';
    badge.classList.toggle('success', connected);
    badge.classList.toggle('error', Boolean(filesystem.error));

    const roots = document.getElementById('filesystem-tool-roots');
    roots.replaceChildren();
    for (const folder of filesystem.approved_folders || []) {
        const item = document.createElement('div');
        const name = document.createElement('strong'); name.textContent = folder.name;
        const path = document.createElement('small'); path.textContent = folder.path;
        item.append(name, path); roots.append(item);
    }
    if (!roots.children.length) {
        const empty = document.createElement('span'); empty.className = 'muted';
        empty.textContent = 'No approved folders yet.'; roots.append(empty);
    }

    const tools = filesystem.tools || [];
    document.getElementById('filesystem-tool-count').textContent = tools.length
        ? `${tools.length} read-only tools` : connected ? 'No supported tools' : 'Not connected';
    const list = document.getElementById('filesystem-tool-list');
    list.replaceChildren();
    for (const tool of tools) {
        const row = document.createElement('div');
        const name = document.createElement('strong'); name.textContent = tool.name.replaceAll('_', ' ');
        const description = document.createElement('small'); description.textContent = tool.description || 'Read-only filesystem capability.';
        row.append(name, description); list.append(row);
    }
    if (!tools.length) {
        const empty = document.createElement('p'); empty.className = 'muted';
        empty.textContent = 'Test or enable the connection to discover its tools.'; list.append(empty);
    }
    const feedback = document.getElementById('filesystem-tool-status');
    if (filesystem.error) setFeedback(feedback, filesystem.error, 'error');
    else if (!filesystem.available) setFeedback(feedback, 'Install Node.js to use the official Filesystem MCP server.', 'error');
    else if (connected) setFeedback(feedback, 'Filesystem MCP is connected with read-only access.', 'success');
    else if (enabled) setFeedback(feedback, 'Filesystem will connect when Petey needs a file tool.');
    else feedback.textContent = '';
}

async function loadTools() {
    const feedback = document.getElementById('filesystem-tool-status');
    try {
        const payload = await apiJson('/api/desktop/tools');
        renderFilesystemTool(payload.filesystem);
        toolsLoaded = true;
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    }
}

document.getElementById('filesystem-tool-enabled').addEventListener('change', async event => {
    const toggle = event.target;
    const feedback = document.getElementById('filesystem-tool-status');
    toggle.disabled = true;
    setFeedback(feedback, toggle.checked ? 'Connecting to Filesystem MCP…' : 'Turning Filesystem off…');
    try {
        const payload = await apiJson('/api/desktop/tools/filesystem', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({enabled: toggle.checked}),
        });
        renderFilesystemTool(payload.filesystem);
    } catch (error) {
        toggle.checked = !toggle.checked;
        setFeedback(feedback, error.message, 'error');
        await loadTools();
    } finally {
        toggle.disabled = false;
    }
});

document.getElementById('test-filesystem-tool').addEventListener('click', async event => {
    const button = event.currentTarget;
    const feedback = document.getElementById('filesystem-tool-status');
    button.disabled = true;
    setFeedback(feedback, 'Testing the Filesystem MCP connection…');
    try {
        const payload = await apiJson('/api/desktop/tools/filesystem/test', {method: 'POST'});
        renderFilesystemTool(payload.filesystem);
        setFeedback(feedback, `Connection successful · ${payload.filesystem.tools.length} read-only tools found.`, 'success');
    } catch (error) {
        setFeedback(feedback, error.message, 'error');
    } finally {
        button.disabled = false;
    }
});

document.getElementById('open-tools-workspace').addEventListener('click', () => showView('workspace'));

for (const [id, endpoint, statusId, read] of [
    ['save-speech-models', '/api/desktop/speech', 'speech-model-save-status', () => ({
        gemini_model: document.getElementById('speech-gemini-model').value,
        openai_model: document.getElementById('speech-openai-model').value,
    })],
    ['save-transcription-provider', '/api/desktop/voice-input', 'transcription-provider-status', () => ({
        provider: voiceInputProviderSelect.value,
        model: document.getElementById('voice-input-model').value,
        gemini_model: voiceInputProviderSelect.value === 'gemini' ? document.getElementById('voice-input-model').value : voiceInputConfiguration.gemini_model,
    })],
]) {
    const button = document.getElementById(id);
    button.addEventListener('click', async () => {
        button.disabled = true;
        const feedback = document.getElementById(statusId);
        try {
            const payload = await apiJson(endpoint, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(read())});
            if (id === 'save-speech-models') {
                speechConfiguration = payload.configuration;
                mediaCatalogLoaded = false; mediaModelsCache.delete('txt2audio');
            } else {
                voiceInputConfiguration = {...voiceInputConfiguration, ...payload.configuration};
            }
            setFeedback(feedback, id === 'save-speech-models' ? 'Speech models saved.' : 'Provider settings saved.', 'success');
        } catch (error) { setFeedback(feedback, error.message, 'error'); }
        finally { button.disabled = false; }
    });
}

const requestedView = window.location.hash.replace('#', '');
const knownViews = [...document.querySelectorAll('.app-view[id]')].map(page => page.id.replace('view-', ''));
if (mobileLayoutQuery.matches) showView('chat');
else if (knownViews.includes(requestedView)) showView(requestedView);
window.addEventListener('hashchange', () => {
    const view = window.location.hash.slice(1) || 'chat';
    if (knownViews.includes(view) && !document.getElementById(`view-${view}`).classList.contains('active-view')) showView(view);
});
mobileLayoutQuery.addEventListener('change', event => {
    if (event.matches) showView('chat');
});
