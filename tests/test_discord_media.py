import unittest

from petey.discord_media import MEDIA_COMMANDS, command_schemas, parse_media_interaction


class DiscordMediaTests(unittest.TestCase):
    def test_command_catalog_covers_desktop_media_operations(self):
        self.assertEqual(
            {item["name"] for item in command_schemas()},
            {"genimg", "img2img", "genvid", "img2vid", "vid2vid", "genmusic", "tts", "rmbg", "upscale"},
        )
        self.assertEqual(MEDIA_COMMANDS["genimg"]["operation"], "txt2img")
        self.assertEqual(MEDIA_COMMANDS["img2img"]["operation"], "img2img")

    def test_interaction_options_and_resolved_attachment_are_parsed(self):
        attachment = {
            "id": "44", "filename": "cat.png", "content_type": "image/png",
            "url": "https://cdn.discordapp.com/attachments/1/2/cat.png",
        }
        parsed = parse_media_interaction({"data": {
            "name": "img2img",
            "options": [
                {"name": "prompt", "value": "make it neon"},
                {"name": "image", "value": "44"},
                {"name": "width", "value": 768},
            ],
            "resolved": {"attachments": {"44": attachment}},
        }})
        self.assertEqual(parsed["operation"], "img2img")
        self.assertEqual(parsed["prompt"], "make it neon")
        self.assertEqual(parsed["parameters"], {"width": 768})
        self.assertEqual(parsed["attachment"], attachment)
        self.assertEqual(parsed["source_kind"], "image")

    def test_unrelated_command_is_ignored(self):
        self.assertIsNone(parse_media_interaction({"data": {"name": "weather"}}))


if __name__ == "__main__":
    unittest.main()
