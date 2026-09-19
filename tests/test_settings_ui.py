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

    def test_mobile_shell_exposes_only_focused_chat_settings(self):
        ids = {attrs.get('id'): (tag, attrs) for tag, attrs in self.markup.elements if 'id' in attrs}
        for name in (
            'mobile-settings-toggle', 'mobile-visual-mode', 'mobile-show-chat',
            'mobile-visual-fullscreen',
            'mobile-persona', 'mobile-voice', 'mobile-voice-method', 'mobile-animation',
            'mobile-settings-save',
        ):
            self.assertIn(name, ids)
        self.assertEqual(ids['mobile-voice-method'][0], 'select')
        self.assertEqual(ids['mobile-persona'][0], 'select')
        self.assertEqual(ids['mobile-visual-fullscreen'][0], 'button')

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

    def test_wake_acknowledgement_waits_for_a_pause_after_the_name(self):
        javascript = (Path(__file__).parents[1] / 'web/static/desktop.js').read_text(
            encoding='utf-8'
        )
        self.assertIn('scheduleWakeAcknowledgement(audioSentAt + 100);', javascript)
        self.assertIn('wakeCuePendingTimer && rms >= threshold * .55', javascript)
        command_start = javascript.index('command = match[1].trim()')
        submit_start = javascript.index('const existing = messageInput.value.trim()', command_start)
        self.assertIn(
            'cancelPendingWakeAcknowledgement();',
            javascript[command_start:submit_start],
        )
