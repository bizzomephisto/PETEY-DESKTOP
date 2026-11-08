"""Behavior regressions for the seven 2026-10-16 interface audit fixes.

Run with the project Python: python tests/browser/audit_regressions.py
Requires Playwright and Chrome (or PLAYWRIGHT_CHROMIUM_EXECUTABLE).
Uses a temporary PETEY state and mocked API responses; no account or audio actions.
"""
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


class AuditRegressions(unittest.TestCase):
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

    def test_modal_focus_escape_and_return_for_all_shared_flows(self):
        for width in (1440, 390):
            self.viewport(width)
            self.view('personality')
            for dialog_id, invoke in [
                ('profile-slot-dialog', 'openProfileSlotDialog()'),
                ('personality-wizard-dialog', 'openPersonalityWizard()'),
                ('new-chat-dialog', 'openNewChatDialog()'),
                ('delete-chat-dialog', "deleteConversation({id:'audit-only',title:'Audit'})"),
            ]:
                with self.subTest(dialog=dialog_id, width=width):
                    self.page.locator('#save-personality').focus()
                    self.page.evaluate('async()=>{await ' + invoke + '}')
                    self.page.wait_for_function("id=>document.getElementById(id).open", arg=dialog_id)
                    controls = self.page.locator(f'#{dialog_id}').locator('button:visible:not([disabled]),input:visible,select:visible,textarea:visible')
                    controls.last.focus()
                    self.page.keyboard.press('Tab')
                    self.assertTrue(self.page.evaluate("id=>document.getElementById(id).contains(document.activeElement)", dialog_id))
                    controls.first.focus()
                    self.page.keyboard.press('Shift+Tab')
                    self.assertTrue(self.page.evaluate("id=>document.getElementById(id).contains(document.activeElement)", dialog_id))
                    self.page.keyboard.press('Escape')
                    self.page.wait_for_function("id=>!document.getElementById(id).open&&document.getElementById(id).hidden", arg=dialog_id)
                    self.assertEqual(self.page.evaluate('document.activeElement.id'), 'save-personality')

    def test_panel_reorder_keyboard_persistence_edges_and_failed_save(self):
        self.page.wait_for_function("document.querySelectorAll('.command-card-move').length>0")
        order = lambda: self.page.evaluate('currentCommandPanelOrder()')
        before = order()
        first = self.page.locator(f'[data-command-panel="{before[0]}"]')
        move = first.locator('.command-card-move[data-direction="1"]')
        move.focus()
        self.page.keyboard.press('Enter')
        self.page.wait_for_function('id=>currentCommandPanelOrder()[1]===id&&!commandRailSaving', arg=before[0])
        self.assertEqual(order()[:2], [before[1], before[0]])
        self.assertTrue(move.evaluate('(el)=>document.activeElement===el'))
        self.assertTrue(any('command_rail_order' in x for x in self.saved_changes))
        self.page.reload()
        self.page.wait_for_function('id=>currentCommandPanelOrder()[1]===id', arg=before[0])
        self.assertEqual(order()[:2], [before[1], before[0]])
        top = self.page.locator(f'[data-command-panel="{before[1]}"] .command-card-move[data-direction="-1"]')
        self.assertEqual(top.get_attribute('aria-disabled'), 'true')
        top.focus()
        self.page.keyboard.press('Enter')
        self.assertEqual(order()[:2], [before[1], before[0]])
        self.fail_preferences = True
        self.page.locator(f'[data-command-panel="{before[0]}"] .command-card-move[data-direction="-1"]').click()
        self.page.wait_for_function("document.getElementById('command-rail-status').textContent.includes('Could not save rail')")
        self.assertEqual(order()[:2], [before[1], before[0]])

    def test_wizard_action_is_independent_and_meter_has_live_value(self):
        self.view('personality')
        button = self.page.locator('#open-personality-wizard')
        self.assertFalse(button.evaluate("el=>!!el.closest('summary')"))
        button.click()
        self.assertTrue(self.page.locator('#personality-wizard-dialog').evaluate('(el)=>el.open'))
        self.page.keyboard.press('Escape')
        self.view('microphone')
        meter = self.page.get_by_role('meter', name='Microphone input level')
        self.page.evaluate('()=>setMicrophoneMeter(73,true)')
        self.assertEqual(meter.get_attribute('aria-valuenow'), '73')
        self.page.evaluate('()=>setMicrophoneMeter(150,true)')
        self.assertEqual(meter.get_attribute('aria-valuenow'), '100')
        self.page.evaluate('()=>setMicrophoneMeter(0,true)')
        self.assertEqual(meter.get_attribute('aria-valuenow'), '0')

    def test_phone_touch_targets_copy_and_scroll(self):
        for width in (320, 390):
            self.viewport(width)
            self.view('chat')
            for selector in ('.copy-message', '.speak-message', '#mobile-chat-dock-toggle'):
                for item in self.page.locator(selector).all():
                    size = item.bounding_box()
                    if size:
                        self.assertGreaterEqual(size['width'], 44)
                        self.assertGreaterEqual(size['height'], 44)
            self.page.locator('.copy-message').first.tap()
            self.page.wait_for_function("window.auditCopied==='Plan a creative project.'")
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)
        self.view('providers')
        content = self.page.locator('#view-providers .tool-content')
        bounds = content.bounding_box()
        x = bounds['x'] + bounds['width']/2
        y = min(700, bounds['y'] + bounds['height'] - 30)
        cdp = self.context.new_cdp_session(self.page)
        cdp.send('Input.dispatchTouchEvent', {'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
        for i in range(1,9):
            cdp.send('Input.dispatchTouchEvent', {'type':'touchMove','touchPoints':[{'x':x,'y':y-i*30}]})
        cdp.send('Input.dispatchTouchEvent', {'type':'touchEnd','touchPoints':[]})
        self.page.wait_for_function("document.querySelector('#view-providers .tool-content').scrollTop>0")

    def test_reduced_motion_preserves_static_progress_and_real_state(self):
        self.page.emulate_media(reduced_motion='reduce')
        state = self.page.evaluate("""()=>{const el=document.createElement('div');el.className='media-job-progress indeterminate';el.innerHTML='<span></span>';document.body.append(el);const s=getComputedStyle(el.firstChild);const result={name:s.animationName,opacity:s.opacity,transform:s.transform};el.remove();return result}""")
        self.assertEqual(state['name'], 'none')
        self.assertGreater(float(state['opacity']), 0)
        self.assertEqual(state['transform'], 'none')

    def test_focus_glow_follows_all_five_theme_accents(self):
        self.view('providers')
        field = self.page.locator('#ai-base-url')
        self.page.evaluate("()=>document.getElementById('ai-base-url-field').hidden=false")
        shadows = []
        for theme in ('nebula', 'cognitive', 'signal', 'terminal', 'ember'):
            self.page.evaluate("theme=>{document.documentElement.dataset.theme=theme;document.documentElement.style.removeProperty('--theme-accent')}", theme)
            self.page.add_style_tag(content='*,*::before,*::after{transition:none!important}')
            field.focus()
            shadow = field.evaluate('(el)=>getComputedStyle(el).boxShadow')
            self.assertNotEqual(shadow, 'none')
            shadows.append(shadow)
        self.assertEqual(len(set(shadows)), 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
