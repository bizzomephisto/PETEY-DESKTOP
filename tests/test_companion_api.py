import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask, jsonify, request
from web.companion_api import CompanionTokens, PREFIX, register_companion_api
from run_desktop import protect_lan_app


class CompanionApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = Flask(__name__)
        self.app.config['PETEY_STATE'] = SimpleNamespace(data_dir=Path(self.directory.name))
        register_companion_api(self.app)
        self.app.add_url_rule('/private', 'private', lambda: jsonify(secret='private'))
        self.app.view_functions['desktop_voice_input_transcribe'] = lambda: jsonify(transcript='Hello')
        self.app.view_functions['desktop_chat'] = lambda: jsonify(text=request.form['message'], surface=request.form['surface'])
        self.app.view_functions['desktop_chat_speech'] = lambda: (jsonify(job={'id': 'job1'}), 202)
        self.app.view_functions['desktop_media_job'] = lambda job_id: jsonify(job={'id': job_id})
        protect_lan_app(self.app, 'root-secret', secure_cookie=True)
        self.client = self.app.test_client()

    def headers(self, token):
        return {'Authorization': 'Bearer ' + token}

    def pair(self):
        result = self.client.post(PREFIX + '/pair', headers=self.headers('root-secret'))
        self.assertEqual(result.status_code, 200)
        return result.json['token']

    def test_auth_scope_revocation_rotation_and_no_cache(self):
        self.assertEqual(self.client.get(PREFIX + '/device').status_code, 401)
        self.assertEqual(self.client.post(PREFIX + '/pair', headers=self.headers('wrong')).status_code, 401)
        first, second = self.pair(), self.pair()
        result = self.client.get(PREFIX + '/device', headers=self.headers(first))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.get('/private', headers=self.headers(first)).status_code, 401)
        self.assertEqual(self.client.get(PREFIX + '/device', headers=self.headers('root-secret')).status_code, 401)
        self.client.delete(PREFIX + '/device', headers=self.headers(first))
        self.assertEqual(self.client.get(PREFIX + '/device', headers=self.headers(first)).status_code, 401)
        self.assertEqual(self.client.get(PREFIX + '/device', headers=self.headers(second)).status_code, 200)
        self.app.config['PETEY_COMPANION_PAIRING_SECRET'] = 'rotated'
        self.assertEqual(self.client.get(PREFIX + '/device', headers=self.headers(second)).status_code, 401)

    def test_full_interface_session_requires_grant_and_revokes_with_device(self):
        token = self.pair()
        self.client.set_cookie('petey_device_session', token)
        self.assertEqual(self.client.get('/private').status_code, 401)
        result = self.client.post(PREFIX + '/interface-session', headers=self.headers(token))
        self.assertEqual(result.status_code, 200)
        cookie = result.headers['Set-Cookie']
        for attribute in ['Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/']:
            self.assertIn(attribute, cookie)
        self.assertNotIn('root-secret', cookie)
        self.assertEqual(self.client.get('/private', base_url='https://localhost').status_code, 200)
        self.client.delete(PREFIX + '/device', headers=self.headers(token))
        self.assertEqual(self.client.get('/private', base_url='https://localhost').status_code, 401)

    def test_full_interface_session_invalidated_by_rotation_or_expiry(self):
        token = self.pair()
        self.client.post(PREFIX + '/interface-session', headers=self.headers(token))
        with patch('web.companion_api.time.time', return_value=10**12):
            self.assertEqual(self.client.get('/private', base_url='https://localhost').status_code, 401)
        self.app.config['PETEY_COMPANION_PAIRING_SECRET'] = 'rotated'
        self.assertEqual(self.client.get('/private', base_url='https://localhost').status_code, 401)
        self.assertEqual(self.client.post(PREFIX + '/interface-session', headers=self.headers(token)).status_code, 401)

    def test_interface_grant_rechecks_pairing_after_request_authentication(self):
        token = self.pair()
        original = CompanionTokens.enable_interface

        def revoke_before_grant(store, token, root):
            store.revoke(token)
            return original(store, token, root)

        with patch.object(CompanionTokens, 'enable_interface', revoke_before_grant):
            result = self.client.post(PREFIX + '/interface-session', headers=self.headers(token))
        self.assertEqual(result.status_code, 401)
        self.assertNotIn('Set-Cookie', result.headers)

    def test_mobile_surface_and_validation(self):
        headers = self.headers(self.pair())
        result = self.client.post(PREFIX + '/chat', headers=headers, json={'message': 'Hello', 'surface': 'petey_desktop'})
        self.assertEqual(result.json, {'text': 'Hello', 'surface': 'mobile_petey'})
        for value in ['', 'x' * 16001, [], None]:
            self.assertEqual(self.client.post(PREFIX + '/chat', headers=headers, json={'message': value}).status_code, 400)
        self.assertEqual(self.client.post(PREFIX + '/transcribe', headers=headers, data=b'x' * (1024 * 1024 + 1)).status_code, 413)

    def test_speech_job_is_bound_to_issuing_device(self):
        first, second = self.headers(self.pair()), self.headers(self.pair())
        self.assertEqual(self.client.post(PREFIX + '/speech', headers=first, json={'text': 'Hi'}).status_code, 202)
        self.assertEqual(self.client.get(PREFIX + '/speech/job1', headers=first).status_code, 200)
        self.assertEqual(self.client.get(PREFIX + '/speech/job1', headers=second).status_code, 404)

    def test_tokens_persist_hashed_and_expire(self):
        token = self.pair()
        path = Path(self.directory.name) / 'companion-devices.json'
        self.assertNotIn(token, path.read_text())
        self.assertNotIn('root-secret', path.read_text())
        store = CompanionTokens(path)
        self.assertTrue(store.valid(token, 'root-secret'))
        with patch('web.companion_api.time.time', return_value=10**12):
            self.assertFalse(store.valid(token, 'root-secret'))

    def test_disabled_without_remote_access(self):
        self.app.config.pop('PETEY_COMPANION_PAIRING_SECRET')
        self.assertEqual(self.client.post(PREFIX + '/pair', headers=self.headers('root-secret')).status_code, 503)

    def test_wav_validation_and_transcription(self):
        import io
        import wave
        headers = self.headers(self.pair())
        bad = self.client.post(PREFIX + '/transcribe', headers=headers, data={'audio': (io.BytesIO(b'bad'), 'bad.wav')})
        self.assertEqual(bad.status_code, 400)
        for rate, expected in [(16000, 200), (48000, 400)]:
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(rate)
                wav.writeframes(b'\0\0' * 1600)
            result = self.client.post(PREFIX + '/transcribe', headers=headers, data={'audio': (io.BytesIO(output.getvalue()), 'request.wav')})
            self.assertEqual(result.status_code, expected)

    def test_car_local_transcription_rejects_hosted_providers_and_never_falls_back(self):
        import io
        import wave
        from unittest.mock import MagicMock
        from petey.desktop_state import DesktopState
        from petey.local_whisper import LocalWhisperError
        from web.desktop_app import create_desktop_app
        state = DesktopState(self.directory.name)
        state.update_voice_input({'mode': 'push_to_talk', 'provider': 'local_whisper'})
        app = create_desktop_app(state=state, memory=MagicMock(), job_manager=MagicMock())
        protect_lan_app(app, 'local-secret', secure_cookie=True)
        client = app.test_client()
        token = client.post(PREFIX + '/pair', headers=self.headers('local-secret')).json['token']
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(b'\0\0' * 1600)
        def transcribe():
            return client.post(PREFIX + '/transcribe-local', headers=self.headers(token), data={'audio': (io.BytesIO(output.getvalue()), 'request.wav')})
        with patch('web.desktop_app.LocalWhisper') as local, patch('web.desktop_app.DeapiSTT') as deapi, patch('web.desktop_app.GeminiSTT') as gemini:
            for provider in ('automatic', 'deapi', 'gemini'):
                with self.subTest(provider=provider):
                    state.update_voice_input({'provider': provider})
                    self.assertEqual(transcribe().status_code, 409)
                    local.assert_not_called(); deapi.assert_not_called(); gemini.assert_not_called()
            state.update_voice_input({'provider': 'local_whisper'})
            local.return_value.transcribe.return_value = 'Car request'
            result = transcribe()
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json, {'transcript': 'Car request', 'provider': 'local_whisper'})
            local.return_value.transcribe.side_effect = LocalWhisperError('Model unavailable')
            self.assertEqual(transcribe().status_code, 502)
            deapi.assert_not_called(); gemini.assert_not_called()

    def test_real_desktop_handlers_with_mocked_providers(self):
        import io
        import wave
        from unittest.mock import MagicMock, AsyncMock
        from petey.desktop_state import DesktopState
        from petey.assistant import AssistantReply
        from web.desktop_app import create_desktop_app
        state = DesktopState(self.directory.name)
        state.update_voice_input({'mode': 'push_to_talk', 'provider': 'local_whisper'})
        app = create_desktop_app(state=state, memory=MagicMock(), job_manager=MagicMock())
        protect_lan_app(app, 'integration-secret', secure_cookie=True)
        client = app.test_client()
        token = client.post(PREFIX + '/pair', headers=self.headers('integration-secret')).json['token']
        headers = self.headers(token)
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(b'\0\0' * 1600)
        with patch('web.desktop_app.LocalWhisper') as whisper:
            whisper.return_value.transcribe.return_value = 'Hello Petey'
            result = client.post(PREFIX + '/transcribe', headers=headers, data={'audio': (io.BytesIO(output.getvalue()), 'request.wav')})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['transcript'], 'Hello Petey')
        with patch('web.desktop_app.AssistantService') as assistant:
            assistant.return_value.respond = AsyncMock(return_value=AssistantReply(text='Hello phone', tool_events=()))
            result = client.post(PREFIX + '/chat', headers=headers, json={'message': 'Hello Petey'})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json['text'], 'Hello phone')
            self.assertEqual(assistant.return_value.respond.call_args.args[1].surface, 'mobile_petey')
