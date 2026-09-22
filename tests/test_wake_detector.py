import unittest

from petey.wake_detector import LocalWakeDetector


class _Processor:
    def encode(self, phrase, out_type=str):
        return phrase.split()


class LocalWakeDetectorTests(unittest.TestCase):
    def test_petey_keyword_accepts_common_acoustic_spellings(self):
        detector = LocalWakeDetector.__new__(LocalWakeDetector)
        detector._processor = _Processor()

        keywords = detector._keywords("Petey")

        self.assertIn("PETEY @PETEY", keywords)
        self.assertIn("HEY PETEY @HEY_PETEY", keywords)
        self.assertIn("PETTY @PETTY", keywords)
        self.assertIn("P T @P_T", keywords)
        self.assertIn("P T Y @P_T_Y", keywords)
        self.assertIn("PEE TEE @PEE_TEE", keywords)
        self.assertNotIn("PETE @PETE", keywords)

    def test_custom_wake_name_does_not_gain_petey_aliases(self):
        detector = LocalWakeDetector.__new__(LocalWakeDetector)
        detector._processor = _Processor()

        keywords = detector._keywords("Jarvis")

        self.assertEqual(keywords, "JARVIS @JARVIS/HEY JARVIS @HEY_JARVIS")


if __name__ == "__main__":
    unittest.main()
