import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

import run_desktop
from petey.quick_window import move_x11_window_frame, screenshot_path


class DesktopLauncherTests(unittest.TestCase):
    def test_cloudflare_mobile_pairing_token_persists_and_rotates(self):
        with TemporaryDirectory() as directory:
            first = run_desktop.persistent_remote_access_token(directory)
            second = run_desktop.persistent_remote_access_token(directory)
            rotated = run_desktop.persistent_remote_access_token(directory, rotate=True)

            self.assertEqual(first, second)
            self.assertNotEqual(first, rotated)
            token_file = Path(directory) / run_desktop.REMOTE_ACCESS_FILE
            self.assertEqual(token_file.stat().st_mode & 0o777, 0o600)

    def test_cloudflare_mode_continues_into_the_local_desktop_flow(self):
        server = MagicMock()
        server.url = "http://127.0.0.1:43909"
        server.private_url = "http://127.0.0.1:43909/?access_token=private-token"
        with (
            patch("run_desktop.sys.argv", [
                "run_desktop.py", "--cloudflare", "--browser",
                "--cloudflare-hostname", "meetpetey.com", "--port", "43909",
            ]),
            patch("run_desktop.LocalServer", return_value=server) as local_server,
            patch("run_desktop.persistent_remote_access_token", return_value="private-token"),
            patch("run_desktop.run_in_browser") as open_local,
            patch("builtins.input") as terminal_pause,
        ):
            run_desktop.main()

        open_local.assert_called_once_with(server.private_url)
        terminal_pause.assert_not_called()
        server.close.assert_called_once_with()
        self.assertEqual(
            local_server.call_args.kwargs["mirror_hosts"], ("::1",)
        )

    def test_cloudflare_native_window_keeps_restart_settings(self):
        server = MagicMock()
        server.url = "http://127.0.0.1:43909"
        server.private_url = "http://127.0.0.1:43909/?access_token=private-token"
        webview = MagicMock()
        with (
            patch("run_desktop.sys.argv", [
                "run_desktop.py", "--cloudflare", "--cloudflare-hostname",
                "meetpetey.com", "--port", "43909",
            ]),
            patch("run_desktop.LocalServer", return_value=server),
            patch("run_desktop.persistent_remote_access_token", return_value="private-token"),
            patch("run_desktop.linux_webview_backend_available", return_value=True),
            patch("run_desktop.preferred_linux_webview_backend", return_value=None),
            patch.dict("sys.modules", {"webview": webview}),
        ):
            run_desktop.main()

        bridge = webview.create_window.call_args.kwargs["js_api"]
        self.assertEqual(bridge.restart_args, (
            "--cloudflare", "--cloudflare-hostname", "meetpetey.com",
            "--port", "43909",
        ))
        server.close.assert_called_once_with()

    def test_lan_access_requires_private_link_then_uses_mobile_safe_cookie(self):
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
        self.assertIn("SameSite=Lax", accepted.headers["Set-Cookie"])
        self.assertIn("Path=/", accepted.headers["Set-Cookie"])
        self.assertEqual(client.get("/").get_data(as_text=True), "PETEY")

    def test_network_server_requires_access_token(self):
        with self.assertRaisesRegex(ValueError, "access token"):
            run_desktop.LocalServer(host="0.0.0.0", port=8765)

    def test_https_lan_cookie_and_private_url_use_secure_transport(self):
        app = Flask(__name__)
        app.add_url_rule("/", "home", lambda: "PETEY")
        run_desktop.protect_lan_app(app, "private-token", secure_cookie=True)
        response = app.test_client().get("/?access_token=private-token")
        self.assertIn("Secure", response.headers["Set-Cookie"])

        server = run_desktop.LocalServer.__new__(run_desktop.LocalServer)
        server.scheme = "https"
        server.access_token = "private-token"
        server.advertised_host = "192.168.1.42"
        server.server = SimpleNamespace(server_port=8765)
        self.assertEqual(
            server.phone_url,
            "https://192.168.1.42:8765/?access_token=private-token",
        )

    def test_cloudflare_forwarded_https_sets_secure_session_cookie(self):
        app = Flask(__name__)
        app.add_url_rule("/", "home", lambda: "PETEY")
        run_desktop.protect_lan_app(app, "private-token", secure_cookie=None)

        response = app.test_client().get(
            "/?access_token=private-token",
            headers={"X-Forwarded-Proto": "https"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("Secure", response.headers["Set-Cookie"])

    def test_cloudflare_session_can_remember_a_paired_phone_for_one_year(self):
        app = Flask(__name__)
        app.add_url_rule("/", "home", lambda: "PETEY")
        run_desktop.protect_lan_app(
            app, "private-token", secure_cookie=None,
            cookie_max_age=run_desktop.REMOTE_SESSION_SECONDS,
        )

        response = app.test_client().get(
            "/?access_token=private-token",
            headers={"X-Forwarded-Proto": "https"},
        )

        self.assertIn(f"Max-Age={run_desktop.REMOTE_SESSION_SECONDS}", response.headers["Set-Cookie"])

    def test_certificate_setup_serves_only_public_certificate_with_token(self):
        with TemporaryDirectory() as directory:
            certificate = Path(directory) / "petey-local-ca.crt"
            certificate.write_bytes(b"PUBLIC CERTIFICATE")
            app = run_desktop.certificate_setup_app(certificate, "private-token")
            client = app.test_client()

            self.assertEqual(client.get("/").status_code, 401)
            page = client.get("/?access_token=private-token")
            self.assertIn("Trust PETEY", page.get_data(as_text=True))
            downloaded = client.get(
                "/petey-local-ca.crt?access_token=private-token"
            )
            self.assertEqual(downloaded.status_code, 200)
            self.assertEqual(downloaded.data, b"PUBLIC CERTIFICATE")
            self.assertIn("attachment", downloaded.headers["Content-Disposition"])
            downloaded.close()

    @unittest.skipUnless(run_desktop.shutil.which("openssl"), "OpenSSL is unavailable")
    def test_lan_certificates_reuse_ca_and_cover_current_ip(self):
        with TemporaryDirectory() as directory:
            first = run_desktop.ensure_lan_certificates("192.168.1.42", directory)
            second = run_desktop.ensure_lan_certificates("192.168.1.43", directory)

            self.assertTrue(first.ca_created)
            self.assertFalse(second.ca_created)
            self.assertEqual(first.ca_certificate.read_bytes(), second.ca_certificate.read_bytes())
            self.assertEqual(second.server_key.stat().st_mode & 0o777, 0o600)
            details = run_desktop.subprocess.run(
                [run_desktop.shutil.which("openssl"), "x509", "-in",
                 str(second.server_certificate), "-noout", "-text"],
                check=True, capture_output=True, text=True,
            ).stdout
            self.assertIn("IP Address:192.168.1.43", details)

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

    def test_linux_shortcut_can_launch_cloudflare_mode(self):
        with TemporaryDirectory() as directory, patch(
            "run_desktop.sys.platform", "linux"
        ):
            launcher = run_desktop.install_linux_desktop_shortcut(
                directory, cloudflare=True
            )
            main_exec = next(
                line for line in launcher.read_text(encoding="utf-8").splitlines()
                if line.startswith("Exec=")
            )
            self.assertTrue(main_exec.endswith(" --cloudflare"))
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

    def test_desktop_bridge_opens_feed_links_in_new_browser_window(self):
        bridge = run_desktop.DesktopBridge()
        for url in ("https://example.com/report", "http://127.0.0.1:8765/api/addons/petey-opencode/artifacts/1/0"):
            with self.subTest(url=url), patch("run_desktop.webbrowser.open", return_value=True) as opened:
                self.assertTrue(bridge.open_external_url(url))
                opened.assert_called_once_with(url, new=1)
        with patch("run_desktop.webbrowser.open") as opened:
            for url in ("javascript:alert(1)", "file:///tmp/report.html", "/relative", "https://[", "http://localhost:bad", "https://user:pass@example.com"):
                with self.subTest(url=url):
                    self.assertFalse(bridge.open_external_url(url))
            opened.assert_not_called()

    def test_desktop_bridge_opens_addons_folder(self):
        with TemporaryDirectory() as directory, patch(
            "run_desktop.subprocess.Popen"
        ) as opened, patch("run_desktop.sys.platform", "linux"):
            path = Path(directory) / "addons"
            result = run_desktop.DesktopBridge(addons_dir=path).open_addons_folder()
            self.assertTrue(result["ok"])
            self.assertTrue(path.is_dir())
            opened.assert_called_once_with(["xdg-open", str(path)])

    def test_desktop_bridge_opens_voice_cues_folder(self):
        with TemporaryDirectory() as directory, patch(
            "run_desktop.subprocess.Popen"
        ) as opened, patch("run_desktop.sys.platform", "linux"):
            path = Path(directory) / "voice-cues"
            result = run_desktop.DesktopBridge(voice_cues_dir=path).open_voice_cues_folder()
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

    def test_desktop_bridge_restart_preserves_cloudflare_launch_settings(self):
        bridge = run_desktop.DesktopBridge(restart_args=(
            "--cloudflare", "--cloudflare-hostname", "meetpetey.com",
            "--port", "8765",
        ))
        bridge.window = MagicMock()
        with patch("run_desktop.os.chdir"), patch("run_desktop.os.execv") as replaced:
            self.assertEqual(bridge.restart_petey(), {"ok": True, "restarting": True})
        replaced.assert_called_once_with(
            run_desktop.sys.executable,
            [run_desktop.sys.executable, str(Path(run_desktop.__file__).resolve()),
             "--cloudflare", "--cloudflare-hostname", "meetpetey.com", "--port", "8765"],
        )

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

    def test_desktop_bridge_downloads_only_files_inside_requested_addon_data(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            source = data_dir / "addon-data" / "petey-conference" / "sessions" / "one" / "transcript.md"
            source.parent.mkdir(parents=True)
            source.write_text("meeting notes", encoding="utf-8")
            destination = data_dir / "saved.md"
            bridge = run_desktop.DesktopBridge(data_dir=data_dir)
            bridge.window = MagicMock()
            bridge.window.create_file_dialog.return_value = (str(destination),)

            result = bridge.download_addon_file(
                "petey-conference", "sessions/one/transcript.md"
            )

            self.assertTrue(result["ok"])
            self.assertEqual(destination.read_text(encoding="utf-8"), "meeting notes")
            self.assertFalse(
                bridge.download_addon_file("petey-conference", "../../settings.json")["ok"]
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
