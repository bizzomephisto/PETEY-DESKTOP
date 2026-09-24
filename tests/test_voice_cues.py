import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from petey.gemini_tts import GEMINI_TTS_VOICES
from petey.voice_cues import VoiceCueLibrary


class VoiceCueLibraryTests(unittest.TestCase):
    def test_library_creates_a_folder_for_every_gemini_voice(self):
        with TemporaryDirectory() as directory:
            library = VoiceCueLibrary(directory)

            self.assertEqual(
                {path.name for path in library.root.iterdir() if path.is_dir()},
                {"default", *GEMINI_TTS_VOICES},
            )
            self.assertTrue((library.root / "default" / "interrupts").is_dir())

    def test_current_voice_clips_override_default_and_fallback(self):
        with TemporaryDirectory() as directory:
            library = VoiceCueLibrary(directory)
            catalog = library.catalog({"provider": "gemini", "gemini_voice": "Kore"})
            self.assertEqual(catalog["voice"], "Kore")
            self.assertEqual(catalog["source_voice"], "default")
            self.assertTrue(Path(catalog["directory"]).is_dir())
            self.assertTrue(catalog["fallback_phrases"])

            default_clip = library.root / "default" / "yeah.wav"
            default_clip.write_bytes(b"RIFF")
            self.assertEqual(library.catalog({"gemini_voice": "Kore"})["clips"], [default_clip])

            voice_clip = library.root / "Kore" / "whats-up.mp3"
            voice_clip.write_bytes(b"ID3")
            selected = library.catalog({"gemini_voice": "Kore"})
            self.assertEqual(selected["source_voice"], "Kore")
            self.assertEqual(selected["clips"], [voice_clip])

            default_interrupt = library.root / "default" / "interrupts" / "sorry.wav"
            default_interrupt.write_bytes(b"RIFF")
            selected = library.catalog({"gemini_voice": "Kore"})
            self.assertEqual(selected["interrupt_source_voice"], "default")
            self.assertEqual(selected["interrupt_clips"], [default_interrupt])
            voice_interrupt = library.root / "Kore" / "interrupts" / "go-ahead.mp3"
            voice_interrupt.write_bytes(b"ID3")
            selected = library.catalog({"gemini_voice": "Kore"})
            self.assertEqual(selected["interrupt_source_voice"], "Kore")
            self.assertEqual(selected["interrupt_clips"], [voice_interrupt])

    def test_resolve_stays_inside_the_cue_library(self):
        with TemporaryDirectory() as directory:
            library = VoiceCueLibrary(directory)
            clip = library.root / "Kore" / "yeah.ogg"
            clip.parent.mkdir(exist_ok=True)
            clip.write_bytes(b"OggS")
            self.assertEqual(library.resolve("Kore", "yeah.ogg"), clip.resolve())
            interrupt = library.root / "Kore" / "interrupts" / "sorry.ogg"
            interrupt.write_bytes(b"OggS")
            self.assertEqual(
                library.resolve("Kore", "interrupts/sorry.ogg"), interrupt.resolve()
            )
            with self.assertRaises(ValueError):
                library.resolve("Kore", "../secret.wav")
            with self.assertRaises(ValueError):
                library.resolve("Kore", "notes.txt")


if __name__ == "__main__":
    unittest.main()
