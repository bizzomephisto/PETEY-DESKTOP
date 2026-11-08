"""Temporary Flask and Chrome fixture for PETEY browser tests."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server, WSGIRequestHandler

APP_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_ROOT))
from petey.desktop_state import DesktopState
from web.desktop_app import create_desktop_app


class QuietHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs):
        pass


class DesktopBrowserFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='petey-audit-regressions-')
        memory = MagicMock()
        memory.get_conversation_messages.return_value = []
        cls.app = create_desktop_app(state=DesktopState(cls.directory.name), memory=memory,
                                     runtime=MagicMock(), job_manager=MagicMock())
        client = cls.app.test_client()
        cls.payloads = {}
        for name in ['bootstrap', 'preferences', 'personality', 'speech', 'voice-input',
                     'provider-keys', 'ai-provider', 'addons', 'conversations']:
            result = client.get('/api/desktop/' + name)
            if result.status_code == 200 and result.is_json:
                cls.payloads[name] = result.json
        cls.payloads['bootstrap']['changelog_unread'] = False
        cls.payloads['bootstrap']['messages'] = [
            {'role': 'user', 'message': 'Plan a creative project.', 'timestamp': '2026-10-16T12:00:00Z'},
            {'role': 'assistant', 'message': 'Choose a small first step.', 'timestamp': '2026-10-16T12:00:01Z'},
        ]
        cls.payloads.update({'addon-events': {'events': [], 'cursor': 0}, 'media/jobs': {'jobs': []},
                             'ai-provider/models': {'models': []}, 'gallery': {'items': []},
                             'mcp/servers': {'servers': []}})
        cls.server = make_server('127.0.0.1', 0, cls.app, threaded=True, request_handler=QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True,
            executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE', '/opt/google/chrome/chrome'),
            args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        service = cls.app.config.get('PETEY_TASKS')
        if service:
            service.close()
        cls.directory.cleanup()

    def setUp(self):
        self.responses = deepcopy(self.payloads)
        self.fail_preferences = False
        self.saved_changes = []
        self.errors = []
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1000}, has_touch=True)
        self.context.route('**/*', self.route)
        self.page = self.context.new_page()
        self.page.set_default_timeout(5000)
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.add_init_script("Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.auditCopied=text}}})")
        self.page.goto(self.origin)
        self.page.wait_for_function("document.querySelectorAll('.message').length===2")

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def route(self, route):
        request = route.request
        if not request.url.startswith(self.origin):
            route.abort()
            return
        path = urlsplit(request.url).path
        if path.startswith('/api/'):
            name = path.removeprefix('/api/desktop/')
            if name == 'preferences' and request.method == 'PUT':
                if self.fail_preferences:
                    route.fulfill(status=503, json={'error': 'Audit fixture save failure'})
                    return
                changes = request.post_data_json
                self.saved_changes.append(changes)
                preferences = {**self.responses['bootstrap']['preferences'], **changes}
                self.responses['bootstrap']['preferences'] = preferences
                route.fulfill(json={'preferences': preferences})
            else:
                route.fulfill(json=self.responses.get(name, {}))
            return
        route.continue_()

    def view(self, view):
        self.page.evaluate("view=>{if(innerWidth<=760&&view!=='chat')document.body.classList.add('mobile-full-settings');showView(view)}", view)
        self.page.wait_for_function("view=>document.getElementById(`view-${view}`).classList.contains('active-view')", arg=view)

    def viewport(self, width):
        self.page.set_viewport_size({'width': width, 'height': 1000})
        self.page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
