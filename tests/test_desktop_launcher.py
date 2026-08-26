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

    def test_platform_icon_formats_are_selected(self):
        self.assertEqual(run_desktop.application_icon_path("linux").name, "petey-icon-256.png")
        self.assertEqual(run_desktop.application_icon_path("win32").name, "petey.ico")
        self.assertEqual(run_desktop.application_icon_path("darwin").name, "petey.icns")
        for platform in ("linux", "win32", "darwin"):
            self.assertTrue(run_desktop.application_icon_path(platform).is_file())

    def test_linux_shortcut_installer_copies_icon_and_writes_launcher(self):
        with TemporaryDirectory() as directory, patch("run_desktop.sys.platform", "linux"):
            launcher = run_desktop.install_linux_desktop_shortcut(directory)
            installed_icon = (
                Path(directory) / "icons" / "hicolor" / "256x256" / "apps"
                / "petey-desktop.png"
            )
            contents = launcher.read_text(encoding="utf-8")

            self.assertTrue(installed_icon.is_file())
            self.assertIn("Name=PETEY Desktop", contents)
            self.assertIn(f"Icon={installed_icon}", contents)
            self.assertIn("run_desktop.py", contents)
            self.assertTrue(launcher.stat().st_mode & 0o100)

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
            self.assertEqual(run_desktop.preferred_linux_webview_backend(), "qt")

    def test_linux_backend_prefers_qt_without_probing_gtk(self):
        def find_spec(name):
            return object() if name in {"gi", "PySide6"} else None

        with (
            patch("run_desktop.sys.platform", "linux"),
            patch("run_desktop.importlib.util.find_spec", side_effect=find_spec),
        ):
            self.assertEqual(run_desktop.preferred_linux_webview_backend(), "qt")

    def test_linux_backend_uses_gtk_when_it_is_the_only_backend(self):
        def find_spec(name):
            return object() if name == "gi" else None

        with (
            patch("run_desktop.sys.platform", "linux"),
            patch("run_desktop.importlib.util.find_spec", side_effect=find_spec),
        ):
            self.assertEqual(run_desktop.preferred_linux_webview_backend(), "gtk")

    def test_linux_backend_detection_rejects_missing_bindings(self):
        with (
            patch("run_desktop.sys.platform", "linux"),
            patch("run_desktop.importlib.util.find_spec", return_value=None),
        ):
            self.assertFalse(run_desktop.linux_webview_backend_available())


if __name__ == "__main__":
    unittest.main()
