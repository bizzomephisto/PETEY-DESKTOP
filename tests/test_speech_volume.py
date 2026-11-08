"""Output volume is validated, persistent and independent of persona/mute."""
import tempfile
import unittest
from petey.desktop_state import DesktopState
from web.desktop_app import create_desktop_app


class SpeechVolumeTests(unittest.TestCase):
    def test_volume_persists_and_does_not_change_mute(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            self.assertEqual(state.speech['volume'], 1)
            state.update_speech({'auto_speak': True})
            state.update_speech({'volume': .35})
            loaded = DesktopState(directory)
            self.assertEqual(loaded.speech['volume'], .35)
            self.assertTrue(loaded.speech['auto_speak'])
            loaded.update_speech({'auto_speak': False})
            self.assertEqual(loaded.speech['volume'], .35)
            loaded.update_speech({'volume': 0})
            self.assertFalse(loaded.speech['auto_speak'])

    def test_profile_assignment_and_activation_keep_current_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_speech({'volume': .9})
            state.save_persona_slot(1, {'name': 'Saved', 'speech': state.speech})
            state.update_speech({'volume': .2})
            state.assign_conversation_persona(state.conversation_id, 1)
            self.assertEqual(state.conversation_speech['volume'], .2)
            state.activate_persona_slot(1)
            self.assertEqual(state.speech['volume'], .2)

    def test_api_rejects_invalid_volume_and_returns_saved_level(self):
        with tempfile.TemporaryDirectory() as directory:
            client = create_desktop_app(state=DesktopState(directory), runtime=object()).test_client()
            for bad in (-.01, 1.01, '50', True, None, float('nan'), float('inf')):
                self.assertEqual(client.put('/api/desktop/speech', json={'volume': bad}).status_code, 400)
            self.assertEqual(client.put('/api/desktop/speech', json={'volume': .5}).json['configuration']['volume'], .5)
            self.assertEqual(client.get('/api/desktop/bootstrap').json['speech']['volume'], .5)
