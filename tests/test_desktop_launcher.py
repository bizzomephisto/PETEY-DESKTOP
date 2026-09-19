import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from flask import Flask

import run_desktop
from petey.quick_window import move_x11_window_frame, screenshot_path


class DesktopLauncherTests(unittest.TestCase):
    def test_lan_access_requires_private_link_then_uses_strict_cookie(self):
        app = Flask(__name__)
        app.add_url_rule("/", "home", lambda: "PETEY")
        run_desktop.protect_lan_app(app, "private-token")
        client = app.test_client()

        denied = client.get("/")
        self.assertEqual(denied.status_code, 401)
        self.assertNotIn("private-token", denied.get_data(as_text=True))

        accepted = client.get("/?access_token=private-token")
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(accepted.headers["Location"], "/")
        self.assertIn("HttpOnly", accepted.headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", accepted.headers["Set-Cookie"])
        self.assertEqual(client.get("/").get_data(as_text=True), "PETEY")

    def test_network_server_requires_access_token(self):
        with self.assertRaisesRegex(ValueError, "access token"):
            run_desktop.LocalServer(host="0.0.0.0", port=8765)

    def test_lan_ip_address_prefers_routed_non_loopback_address(self):
        probe = MagicMock()
        probe.getsockname.return_value = ("192.168.1.42", 43210)
        with patch("run_desktop.socket.socket", return_value=probe):
            self.assertEqual(run_desktop.lan_ip_address(), "192.168.1.42")
        probe.close.assert_called_once()

    def test_desktop_bridge_opens_only_expected_discord_pages(self):
        bridge = run_desktop.DesktopBridge()
        with patch("run_desktop.webbrowser.open", return_value=True) as opened:
            self.assertTrue(bridge.open_discord_url(
                "https://discord.com/oauth2/authorize?client_id=123&scope=bot&permissions=68608"
            ))
            opened.assert_called_once()
            opened.reset_mock()
            self.assertTrue(bridge.open_discord_url("https://discord.com/developers/applications"))
            opened.assert_called_once()
            for url in (
                "https://discord.com.evil.example/oauth2/authorize",
                "https://user:secret@discord.com/oauth2/authorize",
                "http://discord.com/oauth2/authorize",
                "https://discord.com/channels/@me",
            ):
                self.assertFalse(bridge.open_discord_url(url))
            self.assertEqual(opened.call_count, 1)

    def test_desktop_bridge_updates_native_window(self):
        bridge = run_desktop.DesktopBridge()
        window = type("Window", (), {"on_top": False, "toggle_fullscreen": lambda self: None})()
        bridge.window = window

        self.assertTrue(bridge.set_always_on_top(True))
        self.assertTrue(window.on_top)
        self.assertEqual(bridge.toggle_fullscreen(), {"ok": True, "fullscreen": True})

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
            self.assertIn("Name=PETEY", contents.splitlines())
            self.assertIn(f"Icon={installed_icon}", contents)
            self.assertIn("run_desktop.py", contents)
            self.assertIn("StartupWMClass=petey-desktop", contents)
            self.assertIn("[Desktop Action QuickPetey]", contents)
            self.assertIn("--quick", contents)
            self.assertTrue(launcher.stat().st_mode & 0o100)

    def test_cosmic_hotkey_installer_preserves_custom_shortcuts(self):
        with TemporaryDirectory() as directory, patch("run_desktop.sys.platform", "linux"):
            config = Path(directory) / "cosmic/com.system76.CosmicSettings.Shortcuts/v1/custom"
            config.parent.mkdir(parents=True)
            config.write_text("{\n    (modifiers: [Super],): System(AppLibrary),\n}\n", encoding="utf-8")

            result = run_desktop.install_cosmic_quick_hotkey(directory)
            contents = result.read_text(encoding="utf-8")

            self.assertIn("System(AppLibrary)", contents)
            self.assertIn('key: "F1"', contents)
            self.assertIn('Spawn(', contents)
            self.assertIn("--quick", contents)
            self.assertEqual(run_desktop.install_cosmic_quick_hotkey(directory), result)
            self.assertEqual(result.read_text(encoding="utf-8").count('key: "F1"'), 1)

    def test_cosmic_hotkey_installer_does_not_replace_super_f1(self):
        with TemporaryDirectory() as directory, patch("run_desktop.sys.platform", "linux"):
            config = Path(directory) / "cosmic/com.system76.CosmicSettings.Shortcuts/v1/custom"
            config.parent.mkdir(parents=True)
            config.write_text(
                '{\n    (modifiers: [Super], key: "F1",): Spawn("something-else"),\n}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "already has"):
                run_desktop.install_cosmic_quick_hotkey(directory)

    def test_quick_window_anchors_nearest_corner_and_clamps(self):
        self.assertEqual(
            run_desktop.quick_window_position(200, 150, 0, 0, 1920, 1080, width=400, height=300),
            (210, 160),
        )
        self.assertEqual(
            run_desktop.quick_window_position(1800, 1000, 0, 0, 1920, 1080, width=400, height=300),
            (1390, 690),
        )
        self.assertEqual(
            run_desktop.quick_window_position(149, 2628, 149, 2628, 1755, 987, width=430, height=390),
            (159, 2638),
        )

    def test_native_frame_move_is_skipped_outside_x11(self):
        with patch("petey.quick_window.sys.platform", "darwin"):
            self.assertFalse(move_x11_window_frame(123, 10, 20))

    def test_cosmic_screenshot_output_returns_existing_file(self):
        with TemporaryDirectory() as directory:
            screenshot = Path(directory) / "Screenshot.png"
            screenshot.write_bytes(b"image")

            self.assertEqual(screenshot_path(f"portal notice\n{screenshot}\n"), screenshot)
            self.assertIsNone(screenshot_path("cancelled"))

    def test_desktop_bridge_opens_project_repository(self):
        bridge = run_desktop.DesktopBridge()
        with patch("run_desktop.webbrowser.open", return_value=True) as opened:
            self.assertTrue(bridge.open_project_repository())
        opened.assert_called_once_with(run_desktop.PROJECT_URL)

    def test_desktop_bridge_opens_media_provider(self):
        bridge = run_desktop.DesktopBridge()
        with patch("run_desktop.webbrowser.open", return_value=True) as opened:
            self.assertTrue(bridge.open_media_provider())
        opened.assert_called_once_with(run_desktop.MEDIA_PROVIDER_URL)

    def test_desktop_bridge_opens_addons_folder(self):
        with TemporaryDirectory() as directory, patch(
            "run_desktop.subprocess.Popen"
        ) as opened, patch("run_desktop.sys.platform", "linux"):
            path = Path(directory) / "addons"
            result = run_desktop.DesktopBridge(addons_dir=path).open_addons_folder()
            self.assertTrue(result["ok"])
            self.assertTrue(path.is_dir())
            opened.assert_called_once_with(["xdg-open", str(path)])

    def test_desktop_bridge_replaces_current_process_once(self):
        bridge = run_desktop.DesktopBridge()
        bridge.window = MagicMock()
        with (
            patch("run_desktop.os.chdir") as changed,
            patch("run_desktop.os.execv") as replaced,
        ):
            first = bridge.restart_petey()
            second = bridge.restart_petey()
        self.assertEqual(first, {"ok": True, "restarting": True})
        self.assertEqual(second, {"ok": True, "restarting": True})
        changed.assert_called_once_with(run_desktop.PROJECT_ROOT)
        replaced.assert_called_once_with(
            run_desktop.sys.executable,
            [run_desktop.sys.executable, str(Path(run_desktop.__file__).resolve())],
        )
        bridge.window.destroy.assert_not_called()

    def test_restart_requires_native_window_and_recovers_from_launch_error(self):
        bridge = run_desktop.DesktopBridge()
        self.assertFalse(bridge.restart_petey()["ok"])
        bridge.window = MagicMock()
        with patch("run_desktop.os.chdir"), patch(
            "run_desktop.os.execv", side_effect=OSError("launch failed")
        ):
            result = bridge.restart_petey()
        self.assertFalse(result["ok"])
        self.assertFalse(bridge._restart_started)
        bridge.window.destroy.assert_not_called()

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
