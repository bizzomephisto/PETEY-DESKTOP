/* Discord bot controls. Tokens never leave the password-field request. */
let discordState = {phase: 'disconnected', paused: false, credential: {has_token: false}};
let discordCatalogReady = false;
let discordCatalogLoading = false;
let discordActionPending = false;
let discordPollTimer = null;
let discordStatusLoading = false;
let discordMutationVersion = 0;
let discordCatalogVersion = 0;
let discordCatalogError = '';
const discordPaces = ['auto', 'relaxed', 'balanced', 'lively', 'fast'];
const discordPaceLabels = ['Auto', 'Relaxed', 'Balanced', 'Lively', 'Fast'];

function discordControls() {
    const busy = ['connecting', 'connected', 'stopping'].includes(discordState.phase);
    const connected = discordState.phase === 'connected';
    const hasToken = Boolean(discordState.credential?.has_token);
    document.getElementById('discord-token').disabled = busy || discordActionPending;
    document.getElementById('discord-save-token').disabled = busy || discordActionPending;
    document.getElementById('discord-clear-token').disabled = busy || discordActionPending || !discordState.credential?.has_saved_token;
    document.getElementById('discord-refresh').disabled = busy || discordActionPending || discordCatalogLoading || !hasToken;
    document.getElementById('discord-guild').disabled = busy || discordActionPending || discordCatalogLoading || !discordCatalogReady;
    document.getElementById('discord-channel').disabled = busy || discordActionPending || discordCatalogLoading || !discordCatalogReady;
    document.getElementById('discord-connect').disabled = busy || discordActionPending || !discordCatalogReady || !document.getElementById('discord-channel').value;
    document.getElementById('discord-disconnect').disabled = !busy || discordState.phase === 'stopping' || discordActionPending;
    document.getElementById('discord-pause').disabled = !connected || discordActionPending;
    document.getElementById('discord-pause').textContent = discordState.paused ? 'Resume PETEY' : 'Pause PETEY';
    document.getElementById('discord-instruction').disabled = !connected;
    document.getElementById('discord-instruct').disabled = !connected || discordActionPending;
    document.getElementById('discord-pace').disabled = discordActionPending;
    document.getElementById('discord-topics').disabled = discordActionPending;
    document.getElementById('discord-save-topics').disabled = discordActionPending;
    document.getElementById('discord-room-prompt').disabled = discordActionPending;
    document.getElementById('discord-save-room-prompt').disabled = discordActionPending;
    document.getElementById('discord-reset-room-prompt').disabled = discordActionPending;
    document.getElementById('discord-enhance-room-prompt').disabled = discordActionPending;
    document.getElementById('discord-auto-connect').disabled = discordActionPending;
}

function renderDiscord(state) {
    discordState = state;
    const badge = document.getElementById('discord-badge');
    badge.textContent = state.paused && state.phase === 'connected' ? 'Paused' : state.phase;
    const labels = {
        disconnected: 'Disconnected. Choose a server and text channel when ready.',
        connecting: 'Connecting PETEY to Discord…',
        connected: `${state.bot_name} is in ${state.guild} ${state.channel}. ${state.paused ? 'Listening; all replies are paused.' : 'Following the channel’s pace.'}`,
        stopping: 'Stopping replies and disconnecting…',
        error: state.error || 'The Discord connection stopped.',
    };
    document.getElementById('discord-status').textContent = discordCatalogError || labels[state.phase] || state.phase;
    const credential = state.credential || {};
    const paceIndex = Math.max(0, discordPaces.indexOf(state.pace || 'auto'));
    document.getElementById('discord-pace').value = String(paceIndex);
    document.getElementById('discord-pace-label').textContent = discordPaceLabels[paceIndex];
    document.getElementById('discord-auto-connect').checked = Boolean(state.auto_connect);
    const topics = state.watched_topics || [];
    const topicsInput = document.getElementById('discord-topics');
    if (document.activeElement !== topicsInput) topicsInput.value = topics.join(', ');
    document.getElementById('discord-topics-status').textContent = topics.length
        ? `Always responding to: ${topics.join(', ')}`
        : 'No watched topics.';
    const roomPrompt = document.getElementById('discord-room-prompt');
    if (document.activeElement !== roomPrompt) roomPrompt.value = state.room_prompt || '';
    document.getElementById('discord-token-status').textContent = {
        saved: 'Bot token saved in protected local settings.',
        environment: 'Bot token configured by DISCORD_BOT_TOKEN.',
        none: 'No bot token configured.',
    }[credential.source] || 'No bot token configured.';

    const instructions = document.getElementById('discord-instructions');
    instructions.replaceChildren();
    for (const item of state.instructions || []) {
        const line = document.createElement('li');
        const status = document.createElement('strong');
        status.textContent = `${item.status}: `;
        line.append(status, document.createTextNode(item.text));
        instructions.append(line);
    }
    const proposals = document.getElementById('discord-admin-proposals');
    proposals.replaceChildren();
    const pendingProposals = (state.admin_proposals || []).filter(item => item.status === 'pending');
    document.getElementById('discord-admin-status').textContent = pendingProposals.length
        ? `Approval required: ${pendingProposals.at(-1).summary}`
        : '';
    for (const proposal of state.admin_proposals || []) {
        const card = document.createElement('div');
        card.className = 'discord-admin-proposal';
        const description = document.createElement('strong');
        description.textContent = proposal.summary;
        const status = document.createElement('small');
        status.textContent = proposal.error
            ? `${proposal.status}: ${proposal.error}`
            : proposal.status;
        card.append(description, status);
        if (proposal.status === 'pending') {
            const actions = document.createElement('div');
            actions.className = 'proposal-actions';
            const approve = document.createElement('button');
            approve.className = 'primary-button';
            approve.type = 'button';
            approve.textContent = proposal.action === 'create_channel' ? 'Approve creation' : 'Approve destructive action';
            approve.addEventListener('click', () => discordAction('admin-approve', {id: proposal.id}));
            const reject = document.createElement('button');
            reject.className = 'secondary-button';
            reject.type = 'button';
            reject.textContent = 'Reject';
            reject.addEventListener('click', () => discordAction('admin-reject', {id: proposal.id}));
            actions.append(approve, reject);
            card.append(actions);
        }
        proposals.append(card);
    }
    if (!(state.admin_proposals || []).length) proposals.innerHTML = '<p class="muted">No pending server actions.</p>';
    const activity = document.getElementById('discord-activity');
    const atBottom = activity.scrollHeight - activity.scrollTop - activity.clientHeight < 40;
    const events = state.events || [];
    const signature = events.length ? `${events[0].id}:${events.at(-1).id}` : 'empty';
    if (activity.dataset.signature !== signature) {
        activity.replaceChildren();
        for (const event of events) {
            const line = document.createElement('p');
            line.className = event.kind === 'sent' ? 'discord-sent' : '';
            const speaker = document.createElement('strong');
            speaker.textContent = `${event.nickname || 'Connection'}: `;
            line.append(speaker, document.createTextNode(event.text));
            activity.append(line);
        }
        if (!events.length) activity.textContent = 'New channel messages will appear here.';
        activity.dataset.signature = signature;
        if (atBottom) activity.scrollTop = activity.scrollHeight;
    }
    discordControls();
}

function applyDiscordCatalog(catalog, previousGuild = '', previousChannel = '') {
    const guild = document.getElementById('discord-guild');
    guild.replaceChildren();
    for (const row of catalog.guilds || []) guild.add(new Option(row.label, row.id));
    guild.value = (catalog.guilds || []).some(row => row.id === previousGuild) ? previousGuild : catalog.guild_id || '';
    const channel = document.getElementById('discord-channel');
    channel.replaceChildren();
    for (const row of catalog.channels || []) channel.add(new Option(row.label, row.id));
    if ((catalog.channels || []).some(row => row.id === previousChannel)) channel.value = previousChannel;
    if (!(catalog.channels || []).length) channel.add(new Option('No available text channels', ''));
    const invite = document.getElementById('discord-invite');
    const inviteUrl = String(catalog.identity?.invite_url || '');
    if (inviteUrl.startsWith('https://discord.com/oauth2/authorize?')) {
        invite.href = inviteUrl;
        invite.textContent = `Add ${catalog.identity.name || 'PETEY'} to a Discord server ↗`;
        invite.hidden = false;
    } else {
        invite.hidden = true;
        invite.removeAttribute('href');
    }
    discordCatalogReady = (catalog.guilds || []).length > 0 && (catalog.channels || []).length > 0;
}

async function loadDiscordCatalog(guildId = '') {
    const version = ++discordCatalogVersion;
    const previousGuild = guildId || document.getElementById('discord-guild').value;
    const previousChannel = document.getElementById('discord-channel').value;
    discordCatalogLoading = true;
    discordCatalogReady = false;
    discordControls();
    try {
        const query = previousGuild ? `?guild_id=${encodeURIComponent(previousGuild)}` : '';
        const catalog = await apiJson(`/api/desktop/discord/catalog${query}`);
        if (version !== discordCatalogVersion) return;
        applyDiscordCatalog(catalog, previousGuild, previousChannel);
        discordCatalogError = '';
        if (!(catalog.guilds || []).length) {
            document.getElementById('discord-status').textContent = 'The bot is not in any servers yet. Use the Add button, authorize a server, then refresh.';
        }
    } catch (error) {
        if (version === discordCatalogVersion) {
            discordCatalogError = error.message;
            document.getElementById('discord-status').textContent = error.message;
        }
    } finally {
        if (version === discordCatalogVersion) {
            discordCatalogLoading = false;
            discordControls();
        }
    }
}

async function pollDiscord() {
    clearTimeout(discordPollTimer);
    if (discordStatusLoading) return;
    discordStatusLoading = true;
    const version = discordMutationVersion;
    try {
        const state = await apiJson('/api/desktop/discord');
        if (!discordActionPending && version === discordMutationVersion) renderDiscord(state);
    } catch (error) {
        document.getElementById('discord-status').textContent = error.message;
    } finally {
        discordStatusLoading = false;
        discordPollTimer = setTimeout(() => {
            if (document.getElementById('view-discord').classList.contains('active-view')) pollDiscord();
        }, 3000);
    }
}

async function loadDiscord() {
    await pollDiscord();
    const busy = ['connecting', 'connected', 'stopping'].includes(discordState.phase);
    if (!busy && discordState.credential?.has_token && !discordCatalogReady && !discordCatalogLoading) loadDiscordCatalog();
}

async function discordAction(action, payload = {}) {
    discordMutationVersion++;
    discordActionPending = true;
    discordControls();
    try {
        const state = await apiJson(`/api/desktop/discord/${action}`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
        });
        renderDiscord(state);
        return true;
    } catch (error) {
        document.getElementById('discord-status').textContent = error.message;
        return false;
    } finally {
        discordActionPending = false;
        discordControls();
    }
}

document.getElementById('discord-save-token').addEventListener('click', async () => {
    const input = document.getElementById('discord-token');
    if (!input.value.trim()) {
        document.getElementById('discord-token-status').textContent = 'Paste a bot token to save it.';
        return;
    }
    discordActionPending = true; discordControls();
    try {
        const payload = await apiJson('/api/desktop/discord/token', {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token: input.value}),
        });
        input.value = '';
        discordState.credential = payload.credential;
        discordCatalogError = '';
        renderDiscord(discordState);
        await loadDiscordCatalog();
    } catch (error) {
        document.getElementById('discord-token-status').textContent = error.message;
    } finally { discordActionPending = false; discordControls(); }
});
for (const id of ['discord-developer-link', 'discord-invite']) {
    document.getElementById(id).addEventListener('click', async event => {
        if (!window.pywebview?.api?.open_discord_url) return;
        event.preventDefault();
        await window.pywebview.api.open_discord_url(event.currentTarget.href);
    });
}
document.getElementById('discord-clear-token').addEventListener('click', async () => {
    if (!window.confirm('Clear the saved Discord bot token? An environment token is unaffected.')) return;
    discordActionPending = true; discordControls();
    try {
        const payload = await apiJson('/api/desktop/discord/token', {
            method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({clear_token: true}),
        });
        discordState.credential = payload.credential;
        discordCatalogReady = false;
        document.getElementById('discord-invite').hidden = true;
        renderDiscord(discordState);
    } catch (error) { document.getElementById('discord-token-status').textContent = error.message; }
    finally { discordActionPending = false; discordControls(); }
});
document.getElementById('discord-refresh').addEventListener('click', () => loadDiscordCatalog());
document.getElementById('discord-guild').addEventListener('change', event => loadDiscordCatalog(event.target.value));
document.getElementById('discord-channel').addEventListener('change', discordControls);
document.getElementById('discord-pace').addEventListener('input', event => {
    document.getElementById('discord-pace-label').textContent = discordPaceLabels[Number(event.target.value)];
});
document.getElementById('discord-pace').addEventListener('change', event => {
    discordAction('pace', {pace: discordPaces[Number(event.target.value)]});
});
document.getElementById('discord-auto-connect').addEventListener('change', event => {
    discordAction('auto-connect', {enabled: event.target.checked});
});
document.getElementById('discord-topics-form').addEventListener('submit', async event => {
    event.preventDefault();
    const input = document.getElementById('discord-topics');
    const topics = input.value.split(',').map(topic => topic.trim()).filter(Boolean);
    await discordAction('topics', {topics});
});
document.getElementById('discord-room-prompt-form').addEventListener('submit', async event => {
    event.preventDefault();
    const prompt = document.getElementById('discord-room-prompt').value.trim();
    const status = document.getElementById('discord-room-prompt-status');
    if (!prompt) {
        status.textContent = 'Enter a room prompt or restore the default.';
        return;
    }
    if (await discordAction('room-prompt', {prompt})) status.textContent = 'Room prompt saved.';
});
document.getElementById('discord-reset-room-prompt').addEventListener('click', async () => {
    if (await discordAction('room-prompt', {reset: true})) {
        document.getElementById('discord-room-prompt-status').textContent = 'Default room prompt restored.';
    }
});
document.getElementById('discord-enhance-room-prompt').addEventListener('click', async () => {
    const input = document.getElementById('discord-room-prompt');
    const status = document.getElementById('discord-room-prompt-status');
    const prompt = input.value.trim();
    if (!prompt) {
        status.textContent = 'Enter a room prompt to enhance.';
        return;
    }
    discordMutationVersion++;
    discordActionPending = true;
    discordControls();
    status.textContent = 'Enhancing room prompt…';
    try {
        const result = await apiJson('/api/desktop/discord/enhance-room-prompt', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({prompt}),
        });
        input.value = result.prompt;
        input.focus();
        status.textContent = 'Enhanced. Review the result, then save it.';
    } catch (error) {
        status.textContent = error.message;
    } finally {
        discordActionPending = false;
        discordControls();
    }
});
document.getElementById('discord-connect').addEventListener('click', () => {
    const guild = document.getElementById('discord-guild');
    const channel = document.getElementById('discord-channel');
    discordAction('connect', {
        guild_id: guild.value, channel_id: channel.value,
        guild: guild.selectedOptions[0]?.textContent || '',
        channel: channel.selectedOptions[0]?.textContent || '',
    });
});
document.getElementById('discord-disconnect').addEventListener('click', () => discordAction('disconnect'));
document.getElementById('discord-pause').addEventListener('click', () => discordAction('pause', {paused: !discordState.paused}));
document.getElementById('discord-instruction-form').addEventListener('submit', async event => {
    event.preventDefault();
    const input = document.getElementById('discord-instruction');
    const text = input.value.trim();
    if (text && await discordAction('instruct', {text})) {
        if (input.value.trim() === text) input.value = '';
        if ((discordState.admin_proposals || []).some(item => item.status === 'pending')) {
            document.getElementById('discord-admin-proposals').scrollIntoView({behavior: 'smooth', block: 'center'});
        }
    }
});
