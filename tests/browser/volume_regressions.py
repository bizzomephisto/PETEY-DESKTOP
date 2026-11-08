"""Volume UI and gain routing with temporary state; no provider/audio calls."""
import unittest
from browser_fixture import DesktopBrowserFixture


class VolumeRegressions(DesktopBrowserFixture):
    def test_volume_popover_save_reload_keyboard_and_phone_layout(self):
        changes = []
        def speech(route):
            payload = route.request.post_data_json if route.request.method == 'PUT' else {}
            changes.append(payload)
            self.responses['bootstrap']['speech'].update(payload)
            self.responses['speech']['configuration'].update(payload)
            route.fulfill(json=self.responses['speech'])
        self.context.route('**/api/desktop/speech', speech)
        self.view('chat')
        self.page.locator('.composer .speech-volume-button').click()
        self.assertTrue(self.page.locator('#petey-output-volume').is_visible())
        slider = self.page.locator('#petey-output-volume')
        slider.evaluate("el=>{el.value=35;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}")
        self.page.wait_for_function("!document.getElementById('petey-output-volume').disabled")
        self.assertEqual(changes[-1], {'volume': .35})
        self.assertEqual(self.page.locator('#settings-output-volume').input_value(), '35')
        self.page.keyboard.press('Escape')
        self.assertFalse(self.page.locator('#petey-output-volume').is_visible())
        self.page.reload()
        self.page.wait_for_function('speechConfiguration?.volume===.35')
        self.assertEqual(self.page.locator('#petey-output-volume').input_value(), '35')
        for width in (1440, 390, 320):
            self.viewport(width)
            self.view('chat')
            self.page.locator('.composer .speech-volume-button').click()
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth>innerWidth'))
            self.page.screenshot(path=f'/tmp/petey-volume-{width}.png')
            self.page.keyboard.press('Escape')
        self.page.evaluate("document.getElementById('visual-chat').hidden=false")
        self.page.locator('.visual-voice-buttons .speech-volume-button').evaluate('el=>el.click()')
        self.assertTrue(self.page.locator('#petey-output-volume').is_visible())

    def test_volume_changes_live_gain_without_toggling_mute_and_rolls_back_on_failure(self):
        self.context.route('**/api/desktop/speech', lambda route:route.fulfill(status=503,json={'error':'Save failed'}))
        result = self.page.evaluate("""()=>{
            const nodes={};
            const context={currentTime:0,state:'running',destination:{name:'speaker'},
                createGain:()=>nodes.gain={gain:{setValueAtTime:v=>nodes.initial=v,setTargetAtTime:v=>nodes.target=v},connect:dest=>nodes.destination=dest},
                createAnalyser:()=>nodes.analyser={context,connect:dest=>nodes.next=dest}};
            speechConfiguration={...speechConfiguration,volume:.8};
            const before=voiceResponseEnabled;
            speechVisualizationOutput(context);
            const slider=document.getElementById('petey-output-volume');
            slider.value=0;slider.dispatchEvent(new Event('input',{bubbles:true}));
            return {initial:nodes.initial,target:nodes.target,routed:nodes.next===nodes.gain&&nodes.destination===context.destination,muteSame:before===voiceResponseEnabled};
        }""")
        self.assertEqual(result, {'initial': .8, 'target': 0, 'routed': True, 'muteSame': True})
        self.page.locator('#petey-output-volume').dispatch_event('change')
        self.page.wait_for_function("!document.getElementById('petey-output-volume').disabled")
        self.assertEqual(self.page.locator('#petey-output-volume').input_value(), '80')
        self.assertIn('Save failed', self.page.locator('#speech-volume-popover [role=status]').text_content())


if __name__ == '__main__':
    names=[n for n in unittest.defaultTestLoader.getTestCaseNames(VolumeRegressions) if n.startswith('test_volume_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(VolumeRegressions(n) for n in names))
    raise SystemExit(not result.wasSuccessful())
