import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import run_desktop


class DesktopLauncherTests(unittest.TestCase):
    def test_desktop_bridge_updates_native_window(self):
        bridge = run_desktop.DesktopBridge()
        window = type("Window", (), {"on_top": False})()
        bridge.window = window

        self.assertTrue(bridge.set_always_on_top(True))
        self.assertTrue(window.on_top)

    def test_desktop_bridge_opens_project_repository(self):
        bridge = run_desktop.DesktopBridge()
        with patch("run_desktop.webbrowser.open", return_value=True) as opened:
            self.assertTrue(bridge.open_project_repository())
        opened.assert_called_once_with(run_desktop.PROJECT_URL)

    def test_desktop_bridge_opens_gallery_file_with_system_viewer(self):
        gallery = MagicMock()
        gallery.file_path.return_value = Path("/tmp/generated.png")
        bridge = run_desktop.DesktopBridge(gallery)

        with (
            patch("run_desktop.sys.platform", "linux"),
            patch("run_desktop.subprocess.Popen") as launch,
        ):
            result = bridge.open_gallery_item("item-1")

        self.assertTrue(result["ok"])
        launch.assert_called_once_with(["xdg-open", "/tmp/generated.png"])
        gallery.file_path.assert_called_once_with("item-1")

    def test_desktop_bridge_download_uses_native_save_dialog(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "generated.png"
            destination = Path(directory) / "saved.png"
            source.write_bytes(b"image-data")
            gallery = MagicMock()
            gallery.file_path.return_value = source
            bridge = run_desktop.DesktopBridge(gallery)
            bridge.window = MagicMock()
            bridge.window.create_file_dialog.return_value = (str(destination),)

            result = bridge.download_gallery_item("item-1")

            self.assertTrue(result["ok"])
            self.assertEqual(destination.read_bytes(), b"image-data")
            self.assertEqual(
                bridge.window.create_file_dialog.call_args.kwargs["save_filename"],
                "generated.png",
            )

    def test_linux_backend_detection_accepts_qt(self):
        def find_spec(name):
            return object() if name == "PySide6" else None

        with (
            patch("run_desktop.sys.platform", "linux"),
            patch("run_desktop.importlib.util.find_spec", side_effect=find_spec),
        ):
            self.assertTrue(run_desktop.linux_webview_backend_available())

    def test_linux_backend_detection_rejects_missing_bindings(self):
        with (
            patch("run_desktop.sys.platform", "linux"),
            patch("run_desktop.importlib.util.find_spec", return_value=None),
        ):
            self.assertFalse(run_desktop.linux_webview_backend_available())


if __name__ == "__main__":
    unittest.main()
