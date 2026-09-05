import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from petey.image_browser import ImageBrowser, ImageBrowserError
from petey.desktop_state import DesktopState
from web.desktop_app import create_desktop_app


class ImageBrowserTests(unittest.TestCase):
    def test_lists_dimensions_and_creates_small_thumbnail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "images"
            root.mkdir()
            Image.new("RGB", (640, 480), "purple").save(root / "sample.png")
            browser = ImageBrowser()
            opened = browser.open(str(root))
            listing = browser.list_directory(opened["token"])
            self.assertEqual(listing["images"][0]["width"], 640)
            self.assertEqual(listing["images"][0]["height"], 480)
            thumbnail = browser.thumbnail(opened["token"], "sample.png")
            with Image.open(thumbnail) as preview:
                self.assertLessEqual(preview.width, 360)
                self.assertLessEqual(preview.height, 260)

    def test_token_cannot_escape_selected_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "images"
            root.mkdir()
            outside = Path(directory) / "outside.png"
            Image.new("RGB", (20, 20), "red").save(outside)
            (root / "escape.png").symlink_to(outside)
            browser = ImageBrowser()
            token = browser.open(str(root))["token"]
            for path in ("../outside.png", "escape.png"):
                with self.subTest(path=path), self.assertRaises(ImageBrowserError):
                    browser.image_file(token, path)

    def test_repeated_listing_and_thumbnail_reuse_cached_image_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "images"
            root.mkdir()
            Image.new("RGB", (640, 480), "purple").save(root / "sample.png")
            browser = ImageBrowser()
            token = browser.open(str(root))["token"]

            with patch("petey.image_browser.Image.open", wraps=Image.open) as image_open:
                browser.list_directory(token)
                browser.thumbnail(token, "sample.png")
                first_count = image_open.call_count
                browser.list_directory(token)
                browser.thumbnail(token, "sample.png")

            self.assertEqual(first_count, 2)
            self.assertEqual(image_open.call_count, first_count)

    def test_desktop_routes_serve_thumbnail_and_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "images"
            root.mkdir()
            Image.new("RGB", (80, 60), "blue").save(root / "photo.jpg")
            app = create_desktop_app(state=DesktopState(Path(directory) / "state"), runtime=object())
            client = app.test_client()
            opened = client.post("/api/desktop/image-browser/open", json={"path": str(root)})
            self.assertEqual(opened.status_code, 201)
            token = opened.get_json()["token"]
            listing = client.get("/api/desktop/image-browser/list", query_string={"token": token})
            self.assertEqual(listing.get_json()["images"][0]["name"], "photo.jpg")
            thumbnail = client.get("/api/desktop/image-browser/thumbnail", query_string={"token": token, "path": "photo.jpg"})
            self.assertEqual(thumbnail.status_code, 200)
            self.assertEqual(thumbnail.mimetype, "image/jpeg")
            thumbnail.close()
            original = client.get("/api/desktop/image-browser/file", query_string={"token": token, "path": "photo.jpg"})
            self.assertEqual(original.status_code, 200)
            original.close()


if __name__ == "__main__":
    unittest.main()
