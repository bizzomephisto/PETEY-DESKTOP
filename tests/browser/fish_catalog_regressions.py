"""Voice picker checks with temporary PETEY state and a mocked Fish catalog."""
import unittest
from urllib.parse import parse_qs,urlsplit
from browser_fixture import DesktopBrowserFixture


class FishCatalogRegressions(DesktopBrowserFixture):
    def test_voice_search_selection_pagination_profile_restore_and_mobile(self):
        requests=[]
        def catalog(route):
            params=parse_qs(urlsplit(route.request.url).query);requests.append(params)
            page=int(params.get('page',['1'])[0]);scope=params.get('scope',['public'])[0]
            title='My cloned voice' if scope=='mine' else 'Warm narrator <safe text>'
            route.fulfill(json={'voices':[{'id':f'voice-{scope}-{page}','name':title,'author':'Creator','languages':['en']}],
                               'page':page,'has_more':page==1,'total':60,'scope':scope})
        self.context.route('**/api/desktop/speech/fish/voices?*',catalog)
        self.view('personality')
        self.page.evaluate("""()=>{document.getElementById('speech-settings-card').open=true;
            fillSpeechForm({...speechConfiguration,provider:'fish',fish_voice:'saved-manual-voice'});} """)
        picker=self.page.locator('#speech-fish-voice-picker')
        self.page.wait_for_function("document.getElementById('speech-fish-voice-picker').options.length===3")
        self.assertEqual(picker.input_value(),'saved-manual-voice')
        picker.select_option('voice-public-1')
        self.assertEqual(self.page.evaluate('readSpeechForm().fish_voice'),'voice-public-1')
        self.assertEqual(self.page.locator('#speech-fish-voice-picker safe').count(),0)
        self.page.locator('#speech-fish-voice-next').click()
        self.page.wait_for_function("document.querySelector('#speech-fish-voice-picker option[value=\"voice-public-2\"]')")
        self.assertEqual(picker.input_value(),'voice-public-1')
        self.page.locator('#speech-fish-voice-query').fill('Warm')
        self.page.locator('#speech-fish-voice-query').press('Enter')
        self.page.wait_for_function("document.querySelector('#speech-fish-voice-picker option[value=\"voice-public-1\"]')")
        self.assertEqual(requests[-1]['q'],['Warm'])
        self.page.locator('#speech-fish-voice-scope').select_option('mine')
        self.page.wait_for_function("document.querySelector('#speech-fish-voice-picker option[value=\"voice-mine-1\"]')")
        picker.select_option('voice-mine-1')
        self.assertEqual(self.page.evaluate('readSpeechForm().fish_voice'),'voice-mine-1')
        self.page.evaluate("fillSpeechForm({...speechConfiguration,provider:'fish',fish_voice:'another-profile-voice'})")
        self.assertEqual(picker.input_value(),'another-profile-voice')
        self.responses['speech']['configuration'].update({'provider':'fish','fish_voice':'another-profile-voice'})
        self.viewport(390)
        self.view('personality')
        self.page.locator('#speech-fish-voice-field').scroll_into_view_if_needed()
        self.assertTrue(picker.is_visible())
        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth>innerWidth'))
        self.page.screenshot(path='/tmp/petey-fish-catalog-mobile.png',full_page=True)

    def test_catalog_error_keeps_manual_id(self):
        self.context.route('**/api/desktop/speech/fish/voices?*',lambda route:route.fulfill(status=401,json={'error':'Add a Fish Audio key.'}))
        self.view('personality')
        self.page.evaluate("fillSpeechForm({...speechConfiguration,provider:'fish',fish_voice:'keep-me'})")
        self.page.wait_for_function("document.getElementById('speech-fish-voice-status').textContent.includes('Add a Fish')")
        self.assertEqual(self.page.evaluate('readSpeechForm().fish_voice'),'keep-me')


if __name__=='__main__':
    names=[name for name in FishCatalogRegressions.__dict__ if name.startswith('test_')]
    suite=unittest.TestSuite(FishCatalogRegressions(name) for name in names)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
