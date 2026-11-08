import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch, Mock

from petey.desktop_state import DesktopState
from petey.tools.registry import ToolError, ToolRegistry
from petey.web_browser import WebBrowserManager, VisibleBrowser, web_url, blocked_page


class FakeBrowser:
    def __init__(self, profile):
        self.profile = profile
        self.alive = True
        self.calls = []
        self.threads = [threading.get_ident()]
    def perform(self, args):
        self.calls.append(args)
        self.threads.append(threading.get_ident())
        return {'url': 'https://example.com', 'text': 'A page', 'elements': []}
    def close(self):
        self.threads.append(threading.get_ident())
        self.alive = False


class BrowserPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = DesktopState(self.temp.name)
        self.manager = WebBrowserManager(self.state, FakeBrowser)
        self.addCleanup(self.manager.close)

    def test_off_by_default_and_no_browser_launched(self):
        self.assertFalse(self.manager.enabled)
        self.assertEqual(self.manager.tool_specs(), [])
        with self.assertRaisesRegex(ToolError, 'access is off'):
            self.manager.execute({'action': 'open'})
        self.assertIsNone(self.manager.driver)

    def test_toggle_persists_without_changing_filesystem(self):
        self.state.update_tool('filesystem', True)
        self.manager.set_enabled(True)
        restored = DesktopState(self.temp.name)
        self.assertTrue(restored.tools['web_browser']['enabled'])
        self.assertTrue(restored.tools['filesystem']['enabled'])
        with self.assertRaises(ToolError):
            self.manager.set_enabled('yes')

    def test_search_engine_survives_toggle_and_restart(self):
        self.manager.set_search_engine('duckduckgo')
        self.manager.set_enabled(True)
        self.manager.set_enabled(False)
        self.assertEqual(DesktopState(self.temp.name).tools['web_browser']['search_engine'], 'duckduckgo')
        self.manager.set_enabled(True)
        self.manager.execute({'action': 'search', 'text': 'Blender documentation'})
        self.assertEqual(self.manager.driver.calls[-1]['engine'], 'duckduckgo')
        with self.assertRaises(ValueError):
            self.manager.set_search_engine('unknown')

    def test_challenge_detection(self):
        self.assertTrue(blocked_page('https://google.com/sorry/index', '', ''))
        self.assertTrue(blocked_page('https://google.com/search', '', 'Our systems have detected unusual traffic'))
        self.assertTrue(blocked_page('https://example.com', 'Just a moment...', 'Checking...'))
        self.assertFalse(blocked_page('https://example.com/article', 'How bots work', 'An article about CAPTCHA and browser robots.'))

    def test_search_falls_back_after_blocked_provider(self):
        driver = VisibleBrowser.__new__(VisibleBrowser)
        page = Mock()
        driver._current = Mock(return_value=page)
        driver.snapshot = Mock(side_effect=[{'blocked': True}, {'blocked': False}])
        page.locator.return_value.evaluate_all.side_effect = [[], [{'title': 'Manual', 'url': 'https://docs.blender.org/'}]]
        result = driver.search('Blender documentation')
        self.assertTrue(result['search_completed'])
        self.assertEqual(result['search_engine'], 'duckduckgo')
        self.assertEqual([a['engine'] for a in result['search_attempts']], ['brave', 'duckduckgo'])
        self.assertIn('search.brave.com', page.goto.call_args_list[0].args[0])
        self.assertIn('duckduckgo.com', page.goto.call_args_list[1].args[0])

    def test_blocked_search_never_claims_success(self):
        driver = VisibleBrowser.__new__(VisibleBrowser)
        page = Mock()
        driver._current = Mock(return_value=page)
        driver.snapshot = Mock(return_value={'blocked': True})
        page.locator.return_value.evaluate_all.return_value = []
        result = driver.search('Example')
        self.assertFalse(result['search_completed'])
        self.assertEqual(result['search_results'], [])
        self.assertIn('do not claim', result['message'])

    def test_disable_revokes_stale_registry_and_closes_window(self):
        self.manager.set_enabled(True)
        registry = ToolRegistry(self.manager.tool_specs())
        self.assertEqual(len(registry.schemas_for('browse this website')), 1)
        registry.execute('web_browser', {'action': 'open'}, 'browse this website')
        driver = self.manager.driver
        self.manager.set_enabled(False)
        self.assertFalse(driver.alive)
        self.assertFalse(self.manager.public_status()['open'])
        self.assertEqual(registry.schemas_for('browse this website'), [])
        with self.assertRaises(ToolError):
            registry.execute('web_browser', {'action': 'read'}, 'browse this website')

    def test_single_worker_and_separate_profile(self):
        self.manager.set_enabled(True)
        self.manager.execute({'action': 'open'})
        driver = self.manager.driver
        self.manager.execute({'action': 'read'})
        self.manager.close_window()
        self.assertEqual(len(set(driver.threads)), 1)
        self.assertNotEqual(driver.threads[0], threading.get_ident())
        self.assertEqual(driver.profile, Path(self.temp.name) / 'browser-profile')

    def test_surfaces_and_conversational_followup(self):
        self.manager.set_enabled(True)
        self.assertEqual(self.manager.tool_specs('discord'), [])
        self.assertEqual(len(self.manager.tool_specs('mobile_petey')), 1)
        registry = ToolRegistry(self.manager.tool_specs())
        self.assertEqual(registry.schemas_for('tell me a joke'), [])
        self.assertFalse(registry.requires_tool('What is a web browser?'))
        self.assertTrue(registry.requires_tool('Search the web for Blender documentation'))
        self.manager.execute({'action': 'open'})
        self.assertEqual(len(registry.schemas_for('click the first link')), 1)

    def test_transient_page_error_keeps_window_for_read_retry(self):
        self.manager.set_enabled(True)
        self.manager.execute({'action': 'open'})
        driver = self.manager.driver
        with patch.object(driver, 'perform', side_effect=RuntimeError('private details')):
            with self.assertRaisesRegex(ToolError, 'Read the page again'):
                self.manager.execute({'action': 'read'})
        self.assertIs(self.manager.driver, driver)
        self.assertTrue(self.manager.public_status()['open'])
        self.assertNotIn('private details', self.manager.public_status()['error'])
        self.manager.execute({'action': 'read'})

    def test_manually_closed_window_can_reopen(self):
        self.manager.set_enabled(True)
        self.manager.execute({'action': 'open'})
        old = self.manager.driver
        old.alive = False
        self.assertFalse(self.manager.public_status()['open'])
        self.manager.execute({'action': 'open'})
        self.assertIsNot(old, self.manager.driver)
        self.assertTrue(self.manager.public_status()['open'])

    def test_url_and_action_validation_before_launch(self):
        self.manager.set_enabled(True)
        for url in ['file:///etc/passwd', 'javascript:alert(1)', 'https://u:secret@example.com', 'bad']:
            with self.assertRaises(ToolError):
                self.manager.execute({'action': 'open', 'url': url})
        with self.assertRaises(ToolError):
            self.manager.execute({'action': 'evaluate', 'text': 'alert(1)'})
        self.assertIsNone(self.manager.driver)
        self.assertEqual(web_url('https://example.com'), 'https://example.com')

    def test_disable_revokes_a_queued_action(self):
        self.manager.set_enabled(True)
        entered, release = threading.Event(), threading.Event()
        self.manager.worker.submit(lambda: (entered.set(), release.wait(2)))
        entered.wait(1)
        pending = self.manager.worker.submit(self.manager._execute, {'action': 'open'})
        self.state.update_tool('web_browser', False)
        release.set()
        with self.assertRaises(ToolError):
            pending.result(timeout=2)
        self.assertIsNone(self.manager.driver)

    def test_settings_routes(self):
        from web.desktop_app import create_desktop_app
        app = create_desktop_app(state=self.state, browser_manager=self.manager)
        for key in ['PETEY_RUNTIME', 'PETEY_MCP', 'PETEY_GENERAL_MCP', 'PETEY_ADDONS']:
            self.addCleanup(app.config[key].close)
        client = app.test_client()
        self.assertFalse(client.get('/api/desktop/tools/browser').json['browser']['enabled'])
        self.assertEqual(client.post('/api/desktop/tools/browser/open').status_code, 400)
        self.assertEqual(client.put('/api/desktop/tools/browser', json={'enabled': 'bad'}).status_code, 400)
        client.put('/api/desktop/tools/browser', json={'enabled': True})
        self.assertEqual(client.put('/api/desktop/tools/browser', json={'search_engine': 'bad'}).status_code, 400)
        selected = client.put('/api/desktop/tools/browser', json={'search_engine': 'brave'}).json['browser']
        self.assertEqual(selected['search_engine'], 'brave')
        self.assertTrue(selected['enabled'])
        self.assertTrue(client.post('/api/desktop/tools/browser/open').json['browser']['open'])
        self.assertFalse(client.put('/api/desktop/tools/browser', json={'enabled': False}).json['browser']['open'])

    def test_native_restart_closes_browser_before_process_replacement(self):
        import run_desktop
        from unittest.mock import Mock
        browser = Mock()
        bridge = run_desktop.DesktopBridge(browser_manager=browser)
        bridge.window = Mock()
        with patch('run_desktop.os.chdir'), patch('run_desktop.terminate_qt_webengine_children'), \
                patch('run_desktop.os.execv', side_effect=lambda *_: browser.close.assert_called_once()):
            self.assertTrue(bridge.restart_petey()['ok'])


@unittest.skipUnless(os.environ.get('PETEY_BROWSER_INTEGRATION') == '1', 'Opt-in real Chromium check')
class BrowserIntegrationTests(unittest.TestCase):
    def test_visible_navigation_input_refs_popups_and_close(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'''<html><title>PETEY Browser Test</title><body>
                    <h1>Local browser fixture</h1><label>Name<input id="name"></label>
                    <input type="password" aria-label="Password"><input type="file">
                    <button onclick="document.querySelector('h1').textContent=document.querySelector('#name').value">Apply</button>
                    <a href="/next">Next page</a><a href="/popup" target="_blank">Popup</a>
                    </body></html>'''
                self.send_response(200); self.send_header('Content-Type', 'text/html')
                self.end_headers(); self.wfile.write(body)
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            manager = WebBrowserManager(state, lambda profile: VisibleBrowser(
                profile, headless=os.environ.get('PETEY_BROWSER_HEADLESS') == '1',
                executable_path=os.environ.get('PETEY_BROWSER_EXECUTABLE') or None))
            try:
                manager.set_enabled(True)
                url = f'http://127.0.0.1:{server.server_port}'
                result = manager.execute({'action': 'open', 'url': url})
                def command_line():
                    version_page = manager.driver.context.new_page()
                    try:
                        version_page.goto('chrome://version')
                        return version_page.locator('#command_line').inner_text()
                    finally:
                        version_page.close()
                self.assertNotIn('--no-sandbox', manager.worker.submit(command_line).result())
                self.assertIn('Local browser fixture', result['text'])
                self.assertTrue(result['page_content_is_untrusted'])
                self.assertFalse(any(e['type'] in {'password', 'file'} for e in result['elements']))
                target = next(e['ref'] for e in result['elements'] if e['label'] == 'Name')
                result = manager.execute({'action': 'type', 'ref': target, 'text': 'PETEY entered this'})
                button = next(e['ref'] for e in result['elements'] if e['label'] == 'Apply')
                result = manager.execute({'action': 'click', 'ref': button})
                self.assertIn('PETEY entered this', result['text'])
                stale_ref = next(e['ref'] for e in result['elements'] if e['label'] == 'Next page')
                manager.execute({'action': 'read'})
                with self.assertRaises(ToolError):
                    manager.execute({'action': 'click', 'ref': stale_ref})
                result = manager.execute({'action': 'read'})
                target = next(e['ref'] for e in result['elements'] if e['label'] == 'Popup')
                manager.execute({'action': 'click', 'ref': target})
                tabs = manager.execute({'action': 'tabs'})['tabs']
                self.assertEqual(len(tabs), 2)
                manager.execute({'action': 'switch', 'tab': 0})
                manager.execute({'action': 'scroll', 'direction': 'down'})
                manager.set_enabled(False)
                self.assertFalse(manager.public_status()['open'])
            finally:
                manager.close()
                server.shutdown(); server.server_close(); thread.join(timeout=2)
