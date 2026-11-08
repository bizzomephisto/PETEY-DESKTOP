import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

from petey.fish_tts import FishTTSError
from petey.fish_voices import list_fish_voices
from petey.desktop_state import DesktopState
from web.desktop_app import create_desktop_app


class FishVoiceCatalogTests(unittest.TestCase):
    def response(self, payload, status=200):
        result=MagicMock(status_code=status)
        result.iter_content.return_value=[json.dumps(payload).encode()]
        return result

    def test_pagination_scope_search_and_safe_projection(self):
        payload={'total':70,'has_more':True,'items':[
            {'_id':'voice-1','title':'Warm narrator','author':{'nickname':'Creator'},'languages':['en'],'api_key':'not-public'},
            {'_id':'voice-1','title':'Duplicate'}, {'_id':'../unsafe','title':'Bad'},
            {'_id':'removed','dmca_taken_down':True}]}
        response=self.response(payload)
        with patch('petey.fish_voices.HTTP_SESSION.get',return_value=response) as get:
            value=list_fish_voices({'fish':{'api_key':'private-test-key'}},query='warm',scope='mine',page=2)
        self.assertEqual(value['voices'],[{'id':'voice-1','name':'Warm narrator','author':'Creator','languages':['en']}])
        self.assertTrue(value['has_more'])
        kwargs=get.call_args.kwargs
        self.assertEqual(kwargs['params'],{'page_size':50,'page_number':2,'self':'true','sort_by':'score','title':'warm'})
        self.assertEqual(kwargs['headers']['Authorization'],'Bearer private-test-key')
        self.assertFalse(kwargs['allow_redirects'])
        self.assertNotIn('private-test-key',json.dumps(value));self.assertNotIn('not-public',json.dumps(value))
        response.close.assert_called_once()

    def test_missing_key_and_invalid_inputs_make_no_request(self):
        with patch.dict('os.environ',{'FISH_API_KEY':''}),patch('petey.fish_voices.HTTP_SESSION.get') as get:
            with self.assertRaises(FishTTSError):list_fish_voices({})
            for values in ({'scope':'elsewhere'},{'page':0},{'query':'x'*101}):
                with self.assertRaises(ValueError):list_fish_voices({'fish':{'api_key':'key'}},**values)
            get.assert_not_called()

    def test_errors_are_redacted_and_responses_close(self):
        response=self.response({},401)
        with patch('petey.fish_voices.HTTP_SESSION.get',return_value=response):
            with self.assertRaisesRegex(FishTTSError,'HTTP 401'):list_fish_voices({'fish':{'api_key':'secret'}})
        response.close.assert_called_once()
        with patch('petey.fish_voices.HTTP_SESSION.get',side_effect=requests.ConnectionError('secret')):
            with self.assertRaises(FishTTSError) as caught:list_fish_voices({'fish':{'api_key':'secret'}})
            self.assertNotIn('secret',str(caught.exception))
        for payload in ({},[],{'items':'invalid'}):
            response=self.response(payload)
            with patch('petey.fish_voices.HTTP_SESSION.get',return_value=response):
                with self.assertRaises(FishTTSError):list_fish_voices({'fish':{'api_key':'secret'}})
            response.close.assert_called_once()

    def test_response_size_is_bounded(self):
        response=self.response({'items':[]})
        with patch('petey.fish_voices.MAX_RESPONSE',4),patch('petey.fish_voices.HTTP_SESSION.get',return_value=response):
            with self.assertRaisesRegex(FishTTSError,'too large'):list_fish_voices({'fish':{'api_key':'key'}})
        response.close.assert_called_once()

    def test_route_uses_saved_key_and_never_changes_selected_voice(self):
        with tempfile.TemporaryDirectory() as root:
            state=DesktopState(root);state.update_provider_key('fish','private-test-key')
            state.update_speech({'fish_voice':'original'})
            app=create_desktop_app(state=state,runtime=object())
            with patch('petey.fish_voices.list_fish_voices',return_value={'voices':[],'page':1,'has_more':False}) as catalog:
                result=app.test_client().get('/api/desktop/speech/fish/voices?q=warm&scope=mine&page=1')
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.headers['Cache-Control'],'no-store')
            self.assertEqual(catalog.call_args.args[0]['fish']['api_key'],'private-test-key')
            self.assertEqual(catalog.call_args.kwargs,{'query':'warm','scope':'mine','page':1})
            self.assertNotIn('private-test-key',result.get_data(as_text=True))
            self.assertEqual(state.speech['fish_voice'],'original')
