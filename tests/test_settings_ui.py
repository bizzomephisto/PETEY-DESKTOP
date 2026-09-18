"""Settings structure and link contracts, without providers or user data."""
from collections import Counter
from html.parser import HTMLParser
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
        for name in ('save-user-display-name', 'save-personality', 'save-speech-settings',
                     'save-ai-provider', 'save-voice-input', 'save-memory-provider',
                     'save-transcription-provider', 'save-speech-provider',
                     'filesystem-tool-enabled', 'upload-knowledge', 'reset-all-memory'):
            self.assertIn(name, ids)
        tag, attrs = ids['data-removal-settings']
        self.assertEqual(tag, 'details')
        self.assertNotIn('open', attrs)
