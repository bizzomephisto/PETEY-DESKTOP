"""Settings structure and link contracts, without providers or user data."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from petey.desktop_state import DesktopState
from web.desktop_app import create_desktop_app
from web.settings_pages import SETTINGS_GROUPS, SETTINGS_PAGES


class PageMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class SettingsUITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        app = create_desktop_app(state=DesktopState(self.directory.name), memory=MagicMock())
        self.html = app.test_client().get('/').get_data(as_text=True)
        self.markup = PageMarkup()
        self.markup.feed(self.html)

    def test_catalog_pages_render_once_with_shared_accessible_shell(self):
        ids = Counter(attrs['id'] for _, attrs in self.markup.elements if 'id' in attrs)
        self.assertFalse([key for key, count in ids.items() if count != 1])
        for page in SETTINGS_PAGES:
            self.assertEqual(ids['view-' + page['id']], 1)
            self.assertEqual(ids['settings-title-' + page['id']], 1)
            if page['group']:
                self.assertIn(page['group'], SETTINGS_GROUPS)
        searches = [a for _, a in self.markup.elements if 'data-settings-search' in a]
        self.assertEqual(len(searches), len(SETTINGS_PAGES))
        self.assertTrue(all(a.get('aria-label') == 'Find a setting' for a in searches))
        self.assertIn('settings.js', self.html)

    def test_settings_links_and_section_targets_resolve(self):
        ids = {attrs['id'] for _, attrs in self.markup.elements if 'id' in attrs}
        for _, attrs in self.markup.elements:
            if 'data-settings-view' in attrs:
                self.assertIn('view-' + attrs['data-settings-view'], ids)
            if 'data-settings-target' in attrs:
                self.assertIn(attrs['data-settings-target'], ids)
        for name in ('theme-settings', 'api-key-settings', 'speech-settings-card',
                     'microphone-settings', 'embedding-settings', 'data-removal-settings'):
            self.assertIn(name, ids)

    def test_essential_controls_and_destructive_disclosure_preserved(self):
        ids = {attrs.get('id'): (tag, attrs) for tag, attrs in self.markup.elements if 'id' in attrs}
        for name in ('save-user-display-name', 'save-personality', 'save-speech-models',
                     'save-ai-provider', 'save-voice-input', 'save-memory-provider',
                     'save-transcription-provider',
                     'filesystem-tool-enabled', 'upload-knowledge', 'reset-all-memory'):
            self.assertIn(name, ids)
        self.assertIn('voice-wake-delay', ids)
        self.assertIn('voice-submit-delay', ids)
        self.assertIn('voice-follow-up-seconds', ids)
        self.assertIn('voice-response-toggle', ids)
        self.assertIn('visual-voice-response-toggle', ids)
        self.assertIn('speech-provider', ids)
        self.assertNotIn('save-speech-settings', ids)
        self.assertNotIn('save-speech-provider', ids)
        self.assertIn('open-voice-cues-folder', ids)
        tag, attrs = ids['data-removal-settings']
        self.assertEqual(tag, 'details')
        self.assertNotIn('open', attrs)

    def test_visual_fullscreen_includes_phone_voice_controls(self):
        ids = {attrs.get('id'): (tag, attrs) for tag, attrs in self.markup.elements if 'id' in attrs}
        button_tag, button = ids['visual-voice-input-button']
        form_tag, _form = ids['visual-dictation-form']
        input_tag, dictation_input = ids['visual-dictation-input']

        self.assertEqual(button_tag, 'button')
        self.assertEqual(button.get('type'), 'button')
        self.assertIn('Hold to talk', button.get('aria-label', ''))
        self.assertEqual(form_tag, 'form')
        self.assertEqual(input_tag, 'input')
        self.assertEqual(dictation_input.get('type'), 'text')
        self.assertEqual(dictation_input.get('enterkeyhint'), 'send')
        mute_tag, mute_button = ids['visual-mic-mute-button']
        self.assertEqual(mute_tag, 'button')
        self.assertEqual(mute_button.get('aria-pressed'), 'false')
        self.assertEqual(mute_button.get('aria-label'), 'Mute microphone')
        self.assertNotIn('visual-voice-drag-handle', ids)
        menu_tag, menu_button = ids['mobile-visual-menu-toggle']
        self.assertEqual(menu_tag, 'button')
        self.assertEqual(menu_button.get('aria-expanded'), 'false')
        self.assertEqual(menu_button.get('aria-controls'), 'mobile-visual-actions')
        self.assertIn('hidden', ids['mobile-visual-actions'][1])

    def test_mobile_shell_keeps_essentials_first_with_full_settings_access(self):
        ids = {attrs.get('id'): (tag, attrs) for tag, attrs in self.markup.elements if 'id' in attrs}
        for name in (
            'mobile-settings-toggle', 'mobile-visual-mode', 'mobile-show-chat',
            'mobile-visual-fullscreen',
            'mobile-chat-persona', 'mobile-persona', 'mobile-voice', 'mobile-voice-method', 'mobile-animation',
            'mobile-settings-save', 'mobile-show-all-settings', 'mobile-settings-advanced',
            'mobile-chat-dock', 'mobile-chat-dock-toggle', 'mobile-chat-dock-actions',
            'mobile-quick-actions-slot',
        ):
            self.assertIn(name, ids)
        self.assertEqual(ids['mobile-voice-method'][0], 'select')
        self.assertEqual(ids['mobile-persona'][0], 'select')
        self.assertEqual(ids['mobile-chat-persona'][0], 'select')
        self.assertEqual(ids['mobile-visual-fullscreen'][0], 'button')
        self.assertEqual(ids['mobile-show-all-settings'][1].get('role'), 'switch')
        self.assertIn('hidden', ids['mobile-settings-advanced'][1])

    def test_desktop_chat_controls_collapse_behind_chevron_menu(self):
        ids = {attrs.get('id'): (tag, attrs) for tag, attrs in self.markup.elements if 'id' in attrs}
        self.assertEqual(ids['chat-header-menu'][0], 'details')
        self.assertIn('visual-style-field', ids)
        self.assertIn('hidden', ids['visual-style-field'][1])
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        stylesheet = (Path(__file__).parents[1] / 'web/static/desktop.css').read_text(
            encoding='utf-8'
        )
        self.assertIn("const chatHeaderMenu = document.getElementById('chat-header-menu');", javascript)
        self.assertIn("if (chatHeaderMenu.open && !chatHeaderMenu.contains(event.target))", javascript)
        self.assertIn("document.getElementById('visual-style-field').hidden = !visualMode;", javascript)
        self.assertIn('.chat-header-menu-panel {', stylesheet)
        self.assertIn('.chat-header-menu[open] > summary span', stylesheet)

    def test_version_sits_below_desktop_sidebar_links(self):
        template = (Path(__file__).parents[1] / 'web/templates/desktop.html').read_text(
            encoding='utf-8'
        )
        footer_start = template.index('<div class="coming-next">')
        footer_end = template.index('</div>', footer_start)
        footer = template[footer_start:footer_end]
        self.assertLess(footer.index('id="project-link"'), footer.index('id="media-provider-link"'))
        self.assertLess(footer.index('id="media-provider-link"'), footer.index('class="sidebar-version"'))
        self.assertEqual(template.count('PETEY v{{ app_version }}'), 1)

    def test_mobile_composer_exposes_attachment_and_tap_to_mute_push_to_talk(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        stylesheet = (Path(__file__).parents[1] / 'web/static/desktop.css').read_text(
            encoding='utf-8'
        )
        self.assertIn('function composerMicPointerDown(event)', javascript)
        self.assertIn('function composerMicPointerUp(event)', javascript)
        self.assertIn('await toggleMobileMicrophoneMute()', javascript)
        self.assertIn("'Hold to talk · tap to mute'", javascript)
        self.assertNotIn('.composer .attach-button, .composer > small { display: none !important; }', stylesheet)
        self.assertIn('.composer .attach-button, .composer .mic-button, .composer .voice-response-button', stylesheet)

    def test_pending_attachment_can_be_removed_on_desktop_and_mobile(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        stylesheet = (Path(__file__).parents[1] / 'web/static/desktop.css').read_text(
            encoding='utf-8'
        )
        self.assertIn('function clearSelectedAttachment()', javascript)
        self.assertIn("attachmentInput.value = '';", javascript)
        self.assertIn("remove.className = 'attachment-remove'", javascript)
        self.assertIn("remove.addEventListener('click', clearSelectedAttachment)", javascript)
        self.assertNotIn('.composer > small, .attachment-chip { display: none', stylesheet)
        self.assertIn('.attachment-chip[hidden] { display: none !important; }', stylesheet)

    def test_addon_event_speech_uses_a_global_queue_and_respects_mute(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        poll_start = javascript.index('async function pollAddonEvents()')
        poll_end = javascript.index('loadDesktop().finally(', poll_start)
        poller = javascript[poll_start:poll_end]
        self.assertIn('let addonEventSpeechChain = Promise.resolve();', javascript)
        self.assertIn('event.speak && voiceResponseEnabled', poller)
        self.assertIn('addonEventSpeechChain = addonEventSpeechChain', poller)
        self.assertIn('speakChatText(event.text, null, true)', poller)
        self.assertNotIn('autoSpeechChain', poller)

    def test_mobile_automatic_speech_is_single_and_rechecks_mute(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        submit_start = javascript.index("composer.addEventListener('submit'")
        submit_end = javascript.index('function firstStreamingSpeechSegment', submit_start)
        submit = javascript[submit_start:submit_end]
        speech_start = javascript.index('async function speakChatText(')
        speech_end = javascript.index('async function playGeminiSpeechStream', speech_start)
        speech = javascript[speech_start:speech_end]
        self.assertIn('const streamSpeechEarly = autoSpeak && !mobileLayoutQuery.matches;', submit)
        self.assertIn('speakChatText(remainder, null, true)', submit)
        self.assertIn('automatic && !voiceResponseEnabled', speech)
        self.assertIn('stopWakeAcknowledgement();', javascript)
        self.assertIn('if (!voiceResponseEnabled) return;', javascript)

    def test_addons_share_media_devices_and_conference_owns_the_core_microphone(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        self.assertIn('window.peteyMediaDevices = (() => {', javascript)
        self.assertIn('findShareable(kind, deviceId', javascript)
        self.assertIn("window.peteyMediaDevices.register('petey-core-voice'", javascript)
        self.assertIn("window.peteyMediaDevices.release('petey-core-voice')", javascript)
        self.assertIn('window.peteyConferenceAudio = {', javascript)
        self.assertIn("new CustomEvent('petey:voice-playback'", javascript)

    def test_addon_rows_are_collapsed_and_refresh_without_losing_position(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        stylesheet = (Path(__file__).parents[1] / 'web/static/desktop.css').read_text(
            encoding='utf-8'
        )
        self.assertIn('const expandedAddonIds = new Set()', javascript)
        self.assertIn('details.hidden = !expandedAddonIds.has(addon.id)', javascript)
        self.assertIn("summaryButton.setAttribute('aria-controls', details.id)", javascript)
        self.assertIn('const scrollTop = view.scrollTop', javascript)
        self.assertIn('view.scrollTop = scrollTop', javascript)
        self.assertIn('.addon-details[hidden] { display: none; }', stylesheet)

    def test_voice_response_toggle_is_session_aware_on_mobile(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        self.assertIn("voiceResponseEnabled = mobileLayoutQuery.matches", javascript)
        self.assertIn("? Boolean(preferences.visual_mode)", javascript)
        self.assertIn("if (voiceResponseEnabled && speechConfiguration?.provider !== 'disabled')", javascript)
        self.assertIn("const enteringVisualMode = visualMode && lastAppliedVisualMode !== true", javascript)
        self.assertIn("if (voiceResponseInitialized && enteringVisualMode && !voiceResponseEnabled)", javascript)
        self.assertIn("if (mobileLayoutQuery.matches) return;", javascript)

    def test_mobile_visual_mute_and_bottom_menu(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        stylesheet = (Path(__file__).parents[1] / 'web/static/desktop.css').read_text(
            encoding='utf-8'
        )
        self.assertIn("if (mobileVisualMicMuted) await stopVoiceInput();", javascript)
        self.assertIn("(mobileLayoutQuery.matches && mobileVisualMicMuted)) return;", javascript)
        self.assertIn("mobileVisualActions.hidden = !open;", javascript)
        self.assertIn("setMobileVisualMenuOpen(mobileVisualActions.hidden)", javascript)
        self.assertNotIn('visualVoiceDragHandle', javascript)
        self.assertIn(".visual-mic-mute-button.muted::after", stylesheet)
        self.assertIn(".voice-response-button.muted::after", stylesheet)
        self.assertIn(".mobile-visual-actions[hidden] { display: none; }", stylesheet)

    def test_opencode_artifact_links_keep_the_current_remote_origin(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        self.assertIn("['127.0.0.1', 'localhost', '::1']", javascript)
        self.assertIn("const artifactPath =", javascript)
        self.assertIn("artifactHref = `${parsed.pathname}${parsed.search}${parsed.hash}`", javascript)
        self.assertIn("link.textContent = artifactHref ||", javascript)

    def test_mobile_viewport_and_core_assets_are_cache_safe(self):
        metas = [attrs for tag, attrs in self.markup.elements
                 if tag == 'meta' and attrs.get('name') == 'viewport']
        self.assertEqual(len(metas), 1)
        self.assertIn('width=device-width', metas[0].get('content', ''))
        self.assertIn('viewport-fit=cover', metas[0].get('content', ''))
        self.assertIn('interactive-widget=resizes-content', metas[0].get('content', ''))

        asset_urls = [attrs.get('href', '') for tag, attrs in self.markup.elements
                      if tag == 'link' and 'desktop.css' in attrs.get('href', '')]
        asset_urls += [attrs.get('src', '') for tag, attrs in self.markup.elements
                       if tag == 'script' and '/static/' in attrs.get('src', '')]
        self.assertTrue(asset_urls)
        self.assertTrue(all('?v=' in url for url in asset_urls))

    def test_model_generated_images_are_followed_in_the_chat_feed(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        self.assertIn('function appendChatImageJobs(content, toolEvents)', javascript)
        self.assertIn('/api/desktop/media/jobs/${encodeURIComponent(jobId)}', javascript)
        self.assertIn('appendChatImageJobs(content, options.toolEvents);', javascript)
        self.assertIn("card.replaceChildren(image, caption);", javascript)
        self.assertIn("const response = await fetch(source, {cache: 'no-store'});", javascript)
        self.assertIn("if (!blob.type.startsWith('image/'))", javascript)
        self.assertIn("function configureExternalOpenLink(link, label = 'file')", javascript)
        self.assertGreaterEqual(javascript.count("configureExternalOpenLink(open, 'image')"), 2)
        self.assertIn("window.pywebview.api.open_external_url(link.href)", javascript)
        self.assertIn("window.pywebview.api.open_gallery_item(galleryItemId)", javascript)
        self.assertIn("open.dataset.galleryItemId = String(galleryItem.id)", javascript)
        self.assertIn("const galleryPath =", javascript)
        self.assertIn("if (galleryItemId) link.dataset.galleryItemId = galleryItemId", javascript)

    def test_wake_acknowledgement_cannot_overlap_petey_speech(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        self.assertIn(
            'wakeCuePlaying || voiceInputPlaybackBlocked || activeSpeechCancel || activeChatAudio',
            javascript,
        )
        self.assertIn('if (active && wakeCuePlaying) stopWakeAcknowledgement();', javascript)
        self.assertIn(
            '&& !voiceInputPlaybackBlocked && !activeSpeechCancel && !activeChatAudio',
            javascript,
        )
        self.assertIn('prepareWakeCueBuffers().catch(() => {});', javascript)
        self.assertIn('microphoneContext.createBufferSource()', javascript)
        self.assertIn('function playInstantWakeCue()', javascript)
        self.assertIn("voiceInputConfiguration.wake_ack_style || 'fast'", javascript)

    def test_wake_acknowledgement_waits_for_a_pause_after_the_name(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        self.assertIn('voiceInputConfiguration.wake_ack_delay_ms || 300', javascript)
        self.assertIn('voiceInputConfiguration.submit_silence_ms || 600', javascript)
        self.assertNotIn("apiJson('/api/desktop/voice-input/local'", javascript)
        microphone_start = javascript.index('function handleMicrophoneAudio(event)')
        microphone_end = javascript.index('function wavBlob(', microphone_start)
        self.assertIn('wakeCuePendingTimer && rms', javascript[microphone_start:microphone_end])
        acknowledgement_start = javascript.index('function scheduleWakeAcknowledgement(')
        acknowledgement_end = javascript.index('function clearVoiceConversationFollowup()', acknowledgement_start)
        self.assertIn('microphoneLastVoiceAt > wakeCuePendingAfter', javascript[acknowledgement_start:acknowledgement_end])
        microphone_code = javascript[microphone_start:microphone_end]
        self.assertNotIn('scheduleLocalSpeechSubmit', javascript)
        self.assertIn('await transcribeVoiceInput(wavBlob(chunks, microphoneContext.sampleRate))', javascript)
        self.assertIn("variants.push('Pete', 'Petty', 'Pity')", javascript)
        self.assertIn('Speech detected · waiting to hear', javascript)
        command_start = javascript.index('command = match[1].trim()')
        submit_start = javascript.index('const existing = messageInput.value.trim()', command_start)
        self.assertIn(
            'cancelPendingWakeAcknowledgement();',
            javascript[command_start:submit_start],
        )
        self.assertIn('continueVoiceConversation ? 12 : 28', javascript)
        self.assertIn('attempt < 20 ? 250', javascript)

    def test_expensive_visual_and_wake_audio_assets_initialize_lazily(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        self.assertNotIn('\nstartNeuralVisualization();', javascript)
        self.assertIn('if (!neuralDraw) {\n        startNeuralVisualization();', javascript)
        self.assertIn("audio.preload = 'none';", javascript)
        self.assertNotIn("audio.preload = 'auto';", javascript)
        self.assertIn("microphoneSettingsVisible || voiceInputConfiguration.mode === 'wake_word'", javascript)

    def test_visual_animations_track_live_voice_states(self):
        root = Path(__file__).parents[1]
        javascript = (root / 'web/static/desktop.js').read_text(encoding='utf-8')
        template = (root / 'web/templates/desktop.html').read_text(encoding='utf-8')
        stylesheet = (root / 'web/static/desktop.css').read_text(encoding='utf-8')
        self.assertIn('<option value="neural_core">Neural Core</option>', template)
        self.assertIn('<option value="aurora_flow">Aurora Flow</option>', template)
        self.assertIn('<option value="constellation_field">Constellation Field</option>', template)
        self.assertIn('id="visual-state-heading"', template)
        self.assertIn('src="/static/petey_avatar.png"', template)
        self.assertIn('aurora_flow: drawAuroraFlow', javascript)
        self.assertIn('constellation_field: drawConstellationField', javascript)
        self.assertIn("context.fillStyle = '#000';", javascript)
        for renderer in (
            'drawNeuralCore', 'drawSynapseDrift', 'drawOrbitalMind',
            'drawSignalBloom', 'drawAuroraFlow', 'drawConstellationField',
        ):
            self.assertIn(f'const {renderer} =', javascript)
        self.assertIn("listening: {primary: [255, 133, 31]", javascript)
        self.assertIn("speaking: {primary: [26, 137, 255]", javascript)
        self.assertIn("if (visualThinking || voiceInputBusy) return 'thinking';", javascript)
        self.assertIn("if (mobileVisualMicMuted) return 'muted';", javascript)
        self.assertIn("if (time < visualErrorUntil) return 'error';", javascript)
        self.assertIn('.visual-state-heading {', stylesheet)
        self.assertIn('body.native-visual-fullscreen .visual-caption', stylesheet)

    def test_media_catalog_reuses_its_embedded_speech_configuration(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        start = javascript.index('async function loadMediaCatalog()')
        end = javascript.index('function configureMediaOperation(', start)
        loader = javascript[start:end]
        self.assertIn("apiJson('/api/desktop/media')", loader)
        self.assertNotIn("apiJson('/api/desktop/speech')", loader)
        self.assertNotIn('speechSettingsLoaded = true', loader)

    def test_saved_chat_history_is_rendered_in_one_dom_batch(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        start = javascript.index('function renderConversationMessages(history)')
        end = javascript.index('async function loadConversationMessages()', start)
        renderer = javascript[start:end]
        self.assertIn('document.createDocumentFragment()', renderer)
        self.assertIn('deferLayout: true', renderer)
        self.assertIn('messages.append(fragment)', renderer)

    def test_wake_conversation_reopens_for_timed_followups(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        self.assertIn('function markVoiceConversationRequest()', javascript)
        self.assertIn('function openVoiceConversationFollowup()', javascript)
        self.assertIn('function scheduleVoiceConversationIdleTimeout()', javascript)
        self.assertIn('voiceInputConfiguration.follow_up_seconds || 8', javascript)
        self.assertIn("if (microphoneCapturing || voiceInputBusy)", javascript)
        self.assertIn("else if (voiceConversationActive)", javascript)
        self.assertIn('clearVoiceConversationFollowup();', javascript)
        self.assertIn('autoSpeechChain.finally(openVoiceConversationFollowup)', javascript)
        self.assertIn('mode === \'wake_word\' && voiceConversationAwaitingReply', javascript)
        self.assertNotIn('function stopPeteySpeechFromVoice()', javascript)
        self.assertNotIn('Local wake detector unavailable:', javascript)
        self.assertNotIn('provider transcription ready', javascript)
