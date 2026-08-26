import unittest
from unittest.mock import patch

import run_desktop


class DesktopLauncherTests(unittest.TestCase):
    def test_desktop_bridge_updates_native_window(self):
        bridge = run_desktop.DesktopBridge()
        window = type("Window", (), {"on_top": False})()
        bridge.window = window

        self.assertTrue(bridge.set_always_on_top(True))
        self.assertTrue(window.on_top)

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
