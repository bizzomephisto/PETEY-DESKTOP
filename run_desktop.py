"""Launch Petey as a local desktop application."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from werkzeug.serving import make_server

from web.desktop_app import create_desktop_app
from petey.version import MEDIA_PROVIDER_URL, PROJECT_URL, __version__


PROJECT_ROOT = Path(__file__).resolve().parent
ICON_DIRECTORY = PROJECT_ROOT / "assets" / "icons"


def application_icon_path(platform: str | None = None) -> Path:
    platform = platform or sys.platform
    if platform == "win32":
        return ICON_DIRECTORY / "petey.ico"
    if platform == "darwin":
        return ICON_DIRECTORY / "petey.icns"
    return ICON_DIRECTORY / "petey-icon-256.png"


def _desktop_exec_argument(value: str | Path) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def install_linux_desktop_shortcut(data_home: str | Path | None = None) -> Path:
    """Install a per-user Linux launcher and stable icon copy."""
    if sys.platform != "linux":
        raise RuntimeError("Desktop shortcut installation is currently available on Linux.")
    root = Path(data_home) if data_home else Path(
        os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")
    )
    icon_directory = root / "icons" / "hicolor" / "256x256" / "apps"
    application_directory = root / "applications"
    icon_directory.mkdir(parents=True, exist_ok=True)
    application_directory.mkdir(parents=True, exist_ok=True)
    installed_icon = icon_directory / "petey-desktop.png"
    shutil.copy2(application_icon_path("linux"), installed_icon)
    launcher = application_directory / "petey-desktop.desktop"
    launcher.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Name=PETEY Desktop",
                f"Comment=Personal AI assistant · v{__version__}",
                f"Exec={_desktop_exec_argument(sys.executable)} {_desktop_exec_argument(Path(__file__).resolve())}",
                f"Path={PROJECT_ROOT}",
                f"Icon={installed_icon}",
                "Terminal=false",
                "Categories=Utility;Development;",
                "StartupNotify=true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    return launcher


class DesktopBridge:
    """Small native-window API exposed to the local web interface."""

    def __init__(self, gallery=None):
        self.window = None
        self.gallery = gallery
        self.fullscreen = False

    def set_always_on_top(self, enabled):
        if self.window is None:
            return False
        self.window.on_top = bool(enabled)
        return True

    def toggle_fullscreen(self):
        if self.window is None:
            return {"ok": False, "fullscreen": False}
        self.window.toggle_fullscreen()
        self.fullscreen = not self.fullscreen
        return {"ok": True, "fullscreen": self.fullscreen}

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

    def open_project_repository(self):
        return bool(webbrowser.open(PROJECT_URL))

    def open_media_provider(self):
        return bool(webbrowser.open(MEDIA_PROVIDER_URL))

    def open_gallery_item(self, item_id):
        """Open a generated file in the operating system's default media viewer."""
        if self.gallery is None:
            return {"ok": False, "error": "The desktop gallery is unavailable."}
        path = self.gallery.file_path(str(item_id or ""))
        if path is None:
            return {"ok": False, "error": "The local gallery file could not be found."}
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return {"ok": True}
        except OSError as exc:
            return {"ok": False, "error": f"Could not open the generated file: {exc}"}

    def download_gallery_item(self, item_id):
        """Copy a generated file to a location selected with a native Save As dialog."""
        if self.window is None or self.gallery is None:
            return {"ok": False, "error": "The native save dialog is unavailable."}
        source = self.gallery.file_path(str(item_id or ""))
        if source is None:
            return {"ok": False, "error": "The local gallery file could not be found."}
        import webview

        dialog_type = getattr(getattr(webview, "FileDialog", None), "SAVE", None)
        if dialog_type is None:
            dialog_type = getattr(webview, "SAVE_DIALOG", None)
        if dialog_type is None:
            return {"ok": False, "error": "This desktop backend has no Save As dialog."}
        result = self.window.create_file_dialog(
            dialog_type,
            allow_multiple=False,
            save_filename=source.name,
        )
        if isinstance(result, (list, tuple)):
            destination = str(result[0]) if result else ""
        else:
            destination = str(result or "")
        if not destination:
            return {"ok": False, "cancelled": True}
        try:
            destination_path = os.path.abspath(destination)
            if destination_path != os.path.abspath(source):
                shutil.copy2(source, destination_path)
            return {"ok": True, "path": destination_path}
        except OSError as exc:
            return {"ok": False, "error": f"Could not save the generated file: {exc}"}


def preferred_linux_webview_backend():
    """Select an installed backend without making pywebview probe noisy failures."""
    if sys.platform != "linux":
        return None
    if any(
        importlib.util.find_spec(module) is not None
        for module in ("PySide6", "PyQt6", "PySide2", "PyQt5")
    ):
        return "qt"
    if importlib.util.find_spec("gi") is not None:
        return "gtk"
    return ""


def linux_webview_backend_available():
    """Return whether this interpreter can supply GTK or Qt to pywebview."""
    return sys.platform != "linux" or bool(preferred_linux_webview_backend())


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
    parser.add_argument(
        "--install-shortcut",
        action="store_true",
        help="Install PETEY Desktop in the current Linux user's application menu",
    )
    args = parser.parse_args()

    if args.install_shortcut:
        try:
            launcher = install_linux_desktop_shortcut()
        except RuntimeError as exc:
            parser.error(str(exc))
        print(f"[DESKTOP] Installed launcher: {launcher}")
        return

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
        bridge = DesktopBridge(local.app.config["PETEY_GALLERY"])
        bridge.window = webview.create_window(
            f"Petey v{__version__}",
            local.url,
            width=1180,
            height=780,
            min_size=(760, 560),
            on_top=bool(state.preferences.get("always_on_top", False)),
            text_select=True,
            js_api=bridge,
        )
        try:
            backend = preferred_linux_webview_backend()
            if backend:
                webview.start(gui=backend, icon=str(application_icon_path()))
            else:
                webview.start(icon=str(application_icon_path()))
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
