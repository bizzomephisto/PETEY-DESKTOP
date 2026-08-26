"""Launch Petey as a local desktop application."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import threading
import webbrowser

from werkzeug.serving import make_server

from web.desktop_app import create_desktop_app


class DesktopBridge:
    """Small native-window API exposed to the local web interface."""

    def __init__(self):
        self.window = None

    def set_always_on_top(self, enabled):
        if self.window is None:
            return False
        self.window.on_top = bool(enabled)
        return True

    def choose_workspace_folder(self):
        """Open the native folder picker; the Flask API performs final validation."""
        if self.window is None:
            return ""
        import webview

        dialog_type = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
        if dialog_type is None:
            dialog_type = getattr(webview, "FOLDER_DIALOG", None)
        if dialog_type is None:
            return ""
        result = self.window.create_file_dialog(dialog_type, allow_multiple=False)
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else ""
        return str(result or "")

    def choose_image_folder(self):
        return self.choose_workspace_folder()


def linux_webview_backend_available():
    """Return whether this interpreter can supply GTK or Qt to pywebview."""
    if sys.platform != "linux":
        return True
    return any(
        importlib.util.find_spec(module) is not None
        for module in ("gi", "PySide6", "PyQt6", "PySide2", "PyQt5")
    )


def run_in_browser(url, reason=None):
    if reason:
        print(f"[DESKTOP] {reason}")
    print("[DESKTOP] Opening Petey in your browser instead.")
    webbrowser.open(url)
    input("Press Enter to stop Petey.\n")


class LocalServer:
    def __init__(self):
        self.app = create_desktop_app()
        self.server = make_server("127.0.0.1", 0, self.app, threaded=True)
        self.thread = threading.Thread(
            target=self.server.serve_forever, name="petey-local-web", daemon=True
        )

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        jobs = self.app.config.get("PETEY_MEDIA_JOBS")
        if jobs is not None:
            jobs.close()
        self.app.config["PETEY_RUNTIME"].close()


def main():
    parser = argparse.ArgumentParser(description="Run the Petey desktop assistant")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open the local interface in a browser for development",
    )
    args = parser.parse_args()

    local = LocalServer()
    local.start()
    print(f"[DESKTOP] Petey is running locally at {local.url}")
    try:
        if args.browser:
            run_in_browser(local.url)
            return

        try:
            import webview
        except ImportError as exc:
            raise SystemExit(
                "pywebview is not installed. Run 'pip install -r requirements.txt' "
                "or use 'python run_desktop.py --browser' for development."
            ) from exc

        if not linux_webview_backend_available():
            run_in_browser(
                local.url,
                "No GTK or Qt Python backend is installed. For a native Linux "
                "window, run: pip install 'pywebview[pyside6]'",
            )
            return

        state = local.app.config["PETEY_STATE"]
        bridge = DesktopBridge()
        bridge.window = webview.create_window(
            "Petey",
            local.url,
            width=1180,
            height=780,
            min_size=(760, 560),
            on_top=bool(state.preferences.get("always_on_top", False)),
            js_api=bridge,
        )
        try:
            webview.start()
        except Exception as exc:
            # A partially installed GTK backend may import successfully but still
            # lack WebKit. Keep Petey usable and show the exact native-window fix.
            run_in_browser(
                local.url,
                f"The native window backend could not start ({exc}). For a "
                "self-contained Qt backend, run: pip install 'pywebview[pyside6]'",
            )
    finally:
        local.close()


if __name__ == "__main__":
    main()
