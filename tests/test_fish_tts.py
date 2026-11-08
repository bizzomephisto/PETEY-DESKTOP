import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

from petey.desktop_state import DesktopState
from petey.fish_tts import FishTTS, FishTTSError
from petey.media_jobs import MediaGallery, MediaJobManager
from web.desktop_app import create_desktop_app


class FishTTSTests(unittest.TestCase):
    def test_request_uses_model_header_voice_reference_and_mp3(self):
        response = MagicMock(content=b'ID3-test', headers={'Content-Type': 'audio/mpeg'})
        with patch('petey.fish_tts.HTTP_SESSION.post', return_value=response) as post:
            result = FishTTS({'fish': {'api_key': 'test-secret'}}).generate('Hello', 's2.1-pro-free', 'voice-id', 'low')
        self.assertEqual(result['data'], b'ID3-test')
        request = post.call_args.kwargs
        self.assertEqual(request['headers']['model'], 's2.1-pro-free')
        self.assertEqual(request['headers']['Authorization'], 'Bearer test-secret')
        self.assertEqual(request['json'], {'text': 'Hello', 'reference_id': 'voice-id', 'format': 'mp3', 'latency': 'low'})

    def test_invalid_settings_do_not_contact_provider(self):
        with patch.dict(os.environ, {}, clear=True), patch('petey.fish_tts.HTTP_SESSION.post') as post:
            with self.assertRaises(FishTTSError):
                FishTTS({}).generate('Hello', voice='voice-id')
            client = FishTTS({'fish': {'api_key': 'test-secret'}})
            for text, model, voice, latency in [('', 's1', 'id', 'low'), ('Hello', 'unknown', 'id', 'low'), ('Hello', 's1', '', 'low'), ('Hello', 's1', 'https://fish.audio/voice', 'low'), ('Hello', 's1', 'id', 'bad')]:
                with self.assertRaises(FishTTSError):
                    client.generate(text, model, voice, latency)
            post.assert_not_called()

    def test_environment_key_and_errors_do_not_expose_credentials(self):
        with patch.dict(os.environ, {'FISH_API_KEY': 'env-secret'}):
            client = FishTTS({})
        self.assertEqual(client.api_key, 'env-secret')
        response = requests.Response(); response.status_code = 401
        for error in (requests.HTTPError('env-secret', response=response), requests.ConnectionError('env-secret')):
            with patch('petey.fish_tts.HTTP_SESSION.post', side_effect=error):
                with self.assertRaises(FishTTSError) as caught:
                    client.generate('Hello', voice='id')
            self.assertNotIn('env-secret', str(caught.exception))

    def test_empty_or_non_audio_response_is_rejected(self):
        for content, kind in ((b'', 'audio/mpeg'), (b'{"error": "bad"}', 'application/json')):
            response = MagicMock(content=content, headers={'Content-Type': kind})
            with patch('petey.fish_tts.HTTP_SESSION.post', return_value=response):
                with self.assertRaises(FishTTSError):
                    FishTTS({'fish': {'api_key': 'test'}}).generate('Hello', voice='id')

    def test_settings_and_profile_survive_reload_with_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_provider_key('fish', 'test-secret')
            speech = state.update_speech({'provider': 'fish', 'fish_model': 's2.1-pro-free', 'fish_voice': 'voice-id', 'fish_latency': 'low'})
            state.save_persona_slot(1, {'name': 'Fish Petey', 'speech': speech})
            loaded = DesktopState(directory)
            self.assertEqual(loaded.speech['fish_voice'], 'voice-id')
            self.assertEqual(loaded.ai_provider['fish']['api_key'], 'test-secret')
            _, selected = loaded.activate_persona_slot(1)
            self.assertEqual(selected['provider'], 'fish')
            for changes in ({'fish_model': 'invalid'}, {'fish_voice': '../private'}, {'fish_latency': 'invalid'}):
                with self.assertRaises(ValueError):
                    loaded.update_speech(changes)

    def test_api_redacts_keys_and_queues_selected_fish_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            jobs = MagicMock(); jobs.submit.return_value = {'id': 'fish-job', 'status': 'queued'}
            client = create_desktop_app(state=state, runtime=object(), job_manager=jobs).test_client()
            key = client.put('/api/desktop/provider-keys', json={'provider': 'fish', 'api_key': 'test-secret'})
            self.assertTrue(key.get_json()['providers']['fish']['has_saved_key'])
            self.assertNotIn('test-secret', key.get_data(as_text=True))
            speech = client.put('/api/desktop/speech', json={'provider': 'fish', 'fish_voice': 'voice-id'})
            self.assertEqual(speech.status_code, 200)
            self.assertTrue(speech.get_json()['fish_has_api_key'])
            self.assertNotIn('test-secret', speech.get_data(as_text=True))
            queued = client.post('/api/desktop/chat/speech', json={'text': 'Hello'})
            self.assertEqual(queued.status_code, 202)
            arguments = jobs.submit.call_args.kwargs
            self.assertEqual(arguments['model_slug'], 's2.1-pro-free')
            self.assertEqual(arguments['parameters']['voice'], 'voice-id')
            self.assertEqual(arguments['ai_config']['fish']['api_key'], 'test-secret')
            self.assertFalse(arguments['save_to_gallery'])

    def test_queue_returns_audio_without_using_fallback_providers(self):
        import asyncio
        with tempfile.TemporaryDirectory() as directory:
            manager = MediaJobManager(MediaGallery(directory))
            try:
                job = {'id': 'test', 'prompt': 'Hello', '_parameters': {}, '_ai_config': {'fish': {'api_key': 'test'}}, '_save_to_gallery': False}
                with patch('petey.media_jobs.FishTTS.generate', return_value={'data': b'ID3-audio', 'content_type': 'audio/mpeg'}) as fish, patch('petey.media_jobs.GeminiTTS.generate') as gemini, patch('petey.media_jobs.OpenAITTS.generate') as openai:
                    result, gallery = asyncio.run(manager._execute_speech(job, {'provider': 'fish', 'fish_voice': 'voice-id', 'fish_latency': 'low'}))
                self.assertEqual(result['tts_provider'], 'fish')
                self.assertEqual(result['data'], b'ID3-audio')
                self.assertIsNone(gallery)
                fish.assert_called_once_with('Hello', 's2.1-pro-free', 'voice-id', 'low')
                gemini.assert_not_called(); openai.assert_not_called()
            finally:
                manager.close()


class FishExpressionAndStreamingTests(unittest.TestCase):
    def test_expression_prompt_is_scoped_and_preserves_profile(self):
        from petey.fish_tts import fish_expression_prompt, fish_speech_text
        profile = 'You are a reserved, dryly humorous Petey.'
        enabled = fish_expression_prompt(profile, {'provider': 'fish'})
        self.assertIn(profile, enabled)
        self.assertIn('FISH AUDIO EXPRESSION', enabled)
        self.assertIn('[[fish:cue words]]', enabled)
        for speech in ({'provider': 'gemini'}, {'provider': 'fish', 'fish_emotions': False},
                       {'provider': 'fish', 'fish_model': 's1'}):
            self.assertNotIn('FISH AUDIO EXPRESSION', fish_expression_prompt(profile, speech))
        text = '[[fish:dryly sarcastic]] Sure. [1, 2, 3] [Docs](https://example.com)'
        self.assertEqual(fish_speech_text(text), '[dryly sarcastic] Sure. [1, 2, 3] [Docs](https://example.com)')
        self.assertEqual(fish_speech_text(text, False), ' Sure. [1, 2, 3] [Docs](https://example.com)')

    def test_switches_persist_and_chat_visibility_is_global(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            speech = state.update_speech({'provider': 'fish', 'fish_voice': 'voice',
                                         'fish_emotions': False, 'fish_streaming': False,
                                         'fish_show_cues': False})
            state.save_persona_slot(1, {'name': 'Fish', 'speech': speech})
            state.assign_conversation_persona(state.conversation_id, 1)
            state.update_speech({'fish_show_cues': True})
            loaded = DesktopState(directory)
            self.assertFalse(loaded.conversation_speech['fish_emotions'])
            self.assertFalse(loaded.conversation_speech['fish_streaming'])
            self.assertTrue(loaded.conversation_speech['fish_show_cues'])
            for key in ('fish_emotions', 'fish_streaming', 'fish_show_cues'):
                with self.assertRaises(ValueError):
                    loaded.update_speech({key: 'false'})

    def test_pcm_stream_yields_before_completion_and_closes_on_cancel(self):
        response = MagicMock(headers={'Content-Type': 'audio/pcm'})
        response.iter_content.return_value = iter([b'\x01', b'\x02\x03', b'\x04'])
        with patch('petey.fish_tts.HTTP_SESSION.post', return_value=response) as post:
            stream = FishTTS({'fish': {'api_key': 'test'}}).stream_pcm('Hello', voice='voice')
            self.assertEqual(next(stream), b'\x01\x02')
            response.close.assert_not_called()
            self.assertTrue(post.call_args.kwargs['stream'])
            self.assertEqual(post.call_args.kwargs['headers']['model'], 's2.1-pro-free')
            self.assertEqual(post.call_args.kwargs['json']['format'], 'pcm')
            self.assertEqual(post.call_args.kwargs['json']['sample_rate'], 24000)
            stream.close()
            response.close.assert_called_once()

    def test_pcm_stream_preserves_samples_and_rejects_invalid_audio(self):
        for chunks, content_type, expected_error in [
            ([b'\x01', b'\x02\x03', b'\x04'], 'audio/pcm', False),
            ([], 'audio/pcm', True), ([b'\x01'], 'audio/pcm', True),
            ([b'error'], 'application/json', True),
        ]:
            response = MagicMock(headers={'Content-Type': content_type})
            response.iter_content.return_value = iter(chunks)
            with patch('petey.fish_tts.HTTP_SESSION.post', return_value=response):
                stream = FishTTS({'fish': {'api_key': 'test'}}).stream_pcm('Hello', voice='voice')
                if expected_error:
                    with self.assertRaises(FishTTSError):
                        list(stream)
                else:
                    self.assertEqual(b''.join(stream), b'\x01\x02\x03\x04')
            response.close.assert_called_once()

    def test_stream_errors_are_redacted_and_closed(self):
        response = MagicMock(headers={'Content-Type': 'audio/pcm'})
        response.iter_content.side_effect = requests.ConnectionError('test-secret')
        with patch('petey.fish_tts.HTTP_SESSION.post', return_value=response):
            with self.assertRaises(FishTTSError) as caught:
                list(FishTTS({'fish': {'api_key': 'test-secret'}}).stream_pcm('Hi', voice='voice'))
            self.assertNotIn('test-secret', str(caught.exception))
            response.close.assert_called_once()

    def test_stream_route_uses_profile_cues_and_stops_upstream_on_disconnect(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_speech({'provider': 'fish', 'fish_voice': 'profile-voice'})
            client = create_desktop_app(state=state, runtime=object()).test_client()
            closed = []
            def audio(*args):
                try:
                    yield b'\x01\x02'
                    yield b'\x03\x04'
                finally:
                    closed.append(True)
            with patch('web.desktop_app.FishTTS.stream_pcm', side_effect=audio) as stream:
                response = client.post('/api/desktop/chat/speech/stream',
                                       json={'text': '[[fish:curious]] Hello'}, buffered=False)
                events = iter(response.response)
                self.assertEqual(json.loads(next(events))['provider'], 'fish')
                self.assertIn('audio', json.loads(next(events)))
                self.assertEqual(stream.call_args.args[:3], ('[curious] Hello', 's2.1-pro-free', 'profile-voice'))
                response.close()
                self.assertEqual(closed, [True])
            state.update_speech({'fish_streaming': False})
            self.assertEqual(client.post('/api/desktop/chat/speech/stream', json={'text': 'Hello'}).status_code, 400)

    def test_chat_uses_effective_profile_for_cue_generation(self):
        from types import SimpleNamespace
        import asyncio
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            speech = {**state.speech, 'provider': 'fish', 'fish_voice': 'voice'}
            state.save_persona_slot(1, {'name': 'Fish', 'speech': speech})
            state.assign_conversation_persona(state.conversation_id, 1)
            runtime = SimpleNamespace(call=asyncio.run)
            client = create_desktop_app(state=state, runtime=runtime, memory=MagicMock()).test_client()
            with patch('web.desktop_app.AssistantService') as service:
                from unittest.mock import AsyncMock
                service.return_value.respond = AsyncMock(return_value=SimpleNamespace(text='[[fish:calm]] Hi.', tool_events=[]))
                result = client.post('/api/desktop/chat', data={'message': 'Hello', 'temporary': 'true'})
                self.assertEqual(result.status_code, 200)
                self.assertIn('FISH AUDIO EXPRESSION', service.call_args.args[0])
                self.assertEqual(result.json['text'], '[[fish:calm]] Hi.')
                state.update_speech({'provider': 'gemini'})
                state.assign_conversation_persona(state.conversation_id, None)
                client.post('/api/desktop/chat', data={'message': 'Hello', 'temporary': 'true'})
                self.assertNotIn('FISH AUDIO EXPRESSION', service.call_args.args[0])


class FishContextualDirectionTests(unittest.TestCase):
    def test_prompt_offers_inline_layering_and_context_without_tag_quota(self):
        from petey.fish_tts import fish_expression_prompt
        s2 = fish_expression_prompt('Keep the current persona.', {'provider': 'fish'})
        self.assertIn('no one-cue-per-sentence limit', s2)
        self.assertIn('actual meaning of the current words', s2)
        self.assertIn('Do not laugh at distress', s2)
        self.assertIn('[[fish:emphasis]]', s2)
        self.assertIn('long-break', s2)
        self.assertIn('sarcastic', s2)
        self.assertIn('[[fish:curious]][[fish:whispering]]', s2)
        self.assertNotIn('Prefer one cue before a spoken sentence', s2)
        self.assertIn('do not generate paired <emphasis>', s2)
        drama = fish_expression_prompt('Keep the current persona.', {'provider': 'fish', 'fish_model': 'drama-3'})
        self.assertIn('[[fish:<emphasis>]]those words[[fish:</emphasis>]]', drama)
        self.assertIn('Do not copy this reaction into unrelated replies', drama)
        self.assertNotIn('do not generate paired <emphasis>', drama)

    def test_multiple_inline_cues_and_model_specific_word_spans(self):
        from petey.fish_tts import fish_speech_text
        text = ('[[fish:surprised]][[fish:gasping]] Wait, '
                '[[fish:<emphasis>]]HOLY SHIT![[fish:</emphasis>]] '
                '[[fish:soft tone]]It worked. [[fish:long-break]] Now [check] [Docs](https://example.com).')
        expected = ('[surprised][gasping] Wait, <emphasis>HOLY SHIT!</emphasis> '
                    '[soft tone]It worked. [long-break] Now [check] [Docs](https://example.com).')
        self.assertEqual(fish_speech_text(text, model='drama-3'), expected)
        self.assertEqual(fish_speech_text(text, model='drama-3-preview'), expected)
        s2 = fish_speech_text(text)
        self.assertIn('[emphasis]HOLY SHIT!', s2)
        self.assertNotIn('<emphasis>', s2)
        plain = fish_speech_text(text, False)
        self.assertIn('HOLY SHIT!', plain)
        self.assertNotIn('fish:', plain)
        self.assertNotIn('<emphasis>', plain)
        self.assertIn('[check] [Docs](https://example.com)', plain)
        self.assertEqual(fish_speech_text('Example: <emphasis>literal code</emphasis>'), 'Example: <emphasis>literal code</emphasis>')

    def test_unbalanced_internal_spans_do_not_reach_provider_as_controls(self):
        from petey.fish_tts import fish_speech_text
        for text in ('[[fish:<emphasis>]]words', 'words[[fish:</emphasis>]]',
                     '[[fish:<soft>]]words[[fish:</emphasis>]]'):
            self.assertEqual(fish_speech_text(text, model='drama-3'), 'words')

    def test_drama_preview_selections_migrate_without_changing_s21_default(self):
        import json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            self.assertEqual(state.speech['fish_model'], 's2.1-pro-free')
            state.update_speech({'fish_model': 'drama-3-preview'})
            self.assertEqual(state.speech['fish_model'], 'drama-3')
            state.save_persona_slot(1, {'name': 'Legacy drama', 'speech': state.speech})
            data = json.loads(state.settings_path.read_text())
            data['speech']['fish_model'] = 'drama-3-preview'
            data['saved_personas'][0]['speech']['fish_model'] = 'drama-3-preview'
            state.settings_path.write_text(json.dumps(data))
            restored = DesktopState(directory)
            self.assertEqual(restored.speech['fish_model'], 'drama-3')
            self.assertEqual(restored.saved_personas[0]['speech']['fish_model'], 'drama-3')

    def test_queued_and_streamed_drama_preserve_the_same_emphasis(self):
        import asyncio
        text = 'Wait, [[fish:<emphasis>]]HOLY SHIT![[fish:</emphasis>]] It worked.'
        expected = 'Wait, <emphasis>HOLY SHIT!</emphasis> It worked.'
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            speech = state.update_speech({'provider': 'fish', 'fish_model': 'drama-3', 'fish_voice': 'voice'})
            manager = MediaJobManager(MediaGallery(directory))
            try:
                job = {'id': 'test', 'prompt': text, '_parameters': {}, '_ai_config': {}, '_save_to_gallery': False}
                with patch('petey.media_jobs.FishTTS.generate', return_value={'data': b'ID3-audio', 'content_type': 'audio/mpeg'}) as fish:
                    asyncio.run(manager._execute_speech(job, speech))
                    self.assertEqual(fish.call_args.args[:2], (expected, 'drama-3'))
                client = create_desktop_app(state=state, runtime=object(), job_manager=manager).test_client()
                with patch('web.desktop_app.FishTTS.stream_pcm', return_value=iter([b'\x00\x00'])) as stream:
                    result = client.post('/api/desktop/chat/speech/stream', json={'text': text})
                    self.assertIn('"status": "done"', result.get_data(as_text=True))
                    self.assertEqual(stream.call_args.args[:2], (expected, 'drama-3'))
            finally:
                manager.close()
