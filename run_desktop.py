"""Launch Petey as a local desktop application."""

from __future__ import annotations

import argparse
import hmac
import importlib.util
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from flask import Flask, Response, redirect, request, send_file
from werkzeug.serving import make_server

from web.desktop_app import create_desktop_app
from petey.desktop_state import default_data_dir
from petey.version import MEDIA_PROVIDER_URL, PROJECT_URL, __version__


PROJECT_ROOT = Path(__file__).resolve().parent
ICON_DIRECTORY = PROJECT_ROOT / "assets" / "icons"
DESKTOP_APP_ID = "petey-desktop"
QUICK_WINDOW_WIDTH = 430
QUICK_WINDOW_HEIGHT = 390
LAN_TLS_DIRECTORY = "lan-tls"
REMOTE_ACCESS_FILE = "remote-access.json"
REMOTE_SESSION_SECONDS = 365 * 24 * 60 * 60


def persistent_remote_access_token(
    data_dir: str | Path | None = None, *, rotate: bool = False,
) -> str:
    """Load PETEY's durable remote pairing secret, creating or rotating it safely."""
    directory = Path(data_dir) if data_dir else default_data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    path = directory / REMOTE_ACCESS_FILE
    if not rotate:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            token = str(payload.get("access_token") or "")
            if re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
                return token
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            pass
    token = secrets.token_urlsafe(32)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"version": 1, "access_token": token}, indent=2),
        encoding="utf-8",
    )
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return token


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


def install_linux_desktop_shortcut(
    data_home: str | Path | None = None, *, cloudflare: bool = False,
    cloudflare_hostname: str = "", cloudflare_port: int | None = None,
) -> Path:
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
    launch_mode = " --cloudflare" if cloudflare else ""
    if cloudflare and cloudflare_hostname:
        launch_mode += f" --cloudflare-hostname {_desktop_exec_argument(cloudflare_hostname)}"
    if cloudflare and cloudflare_port is not None:
        launch_mode += f" --port {int(cloudflare_port)}"
    launcher.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Name=PETEY",
                f"Comment=Personal AI assistant · v{__version__}",
                f"Exec={_desktop_exec_argument(sys.executable)} {_desktop_exec_argument(Path(__file__).resolve())}{launch_mode}",
                f"Path={PROJECT_ROOT}",
                f"Icon={installed_icon}",
                "Terminal=false",
                "Categories=Utility;Development;",
                "StartupNotify=true",
                f"StartupWMClass={DESKTOP_APP_ID}",
                "Actions=QuickPetey;",
                "",
                "[Desktop Action QuickPetey]",
                "Name=Quick PETEY",
                f"Exec={_desktop_exec_argument(sys.executable)} {_desktop_exec_argument(Path(__file__).resolve())} --quick",
                "",
            ]
        ),
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    return launcher


def quick_launch_command() -> str:
    """Return the shell command used by desktop keyboard shortcut managers."""
    return f"{_desktop_exec_argument(sys.executable)} {_desktop_exec_argument(Path(__file__).resolve())} --quick"


def install_cosmic_quick_hotkey(config_home: str | Path | None = None) -> Path:
    """Bind Super+F1 to Quick PETEY without replacing an existing binding."""
    if sys.platform != "linux":
        raise RuntimeError("The COSMIC hotkey installer is available on Linux.")
    root = Path(config_home) if config_home else Path(
        os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
    )
    path = root / "cosmic" / "com.system76.CosmicSettings.Shortcuts" / "v1" / "custom"
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = path.read_text(encoding="utf-8") if path.exists() else "{}\n"
    compact = "".join(contents.split())
    if re.search(r'modifiers:\[Super,?\],key:"F1"', compact):
        if "--quick" in contents:
            return path
        raise RuntimeError("Super+F1 already has a COSMIC shortcut. PETEY left it unchanged.")
    closing = contents.rfind("}")
    if closing < 0:
        raise RuntimeError("The COSMIC custom shortcut file is not in the expected format.")
    command = quick_launch_command().replace("\\", "\\\\").replace('"', '\\"')
    entry = (
        "    (\n"
        "        modifiers: [\n"
        "            Super,\n"
        "        ],\n"
        '        key: "F1",\n'
        '        description: Some("Quick PETEY"),\n'
        f'    ): Spawn("{command}"),\n'
    )
    prefix = contents[:closing].rstrip()
    if prefix and not prefix.endswith("{"):
        prefix += "\n"
    updated = prefix + "\n" + entry + "}\n"
    temporary = path.with_name(path.name + ".petey-tmp")
    temporary.write_text(updated, encoding="utf-8")
    os.replace(temporary, path)
    return path


def quick_window_position(cursor_x, cursor_y, screen_x, screen_y, screen_width, screen_height,
                          width=QUICK_WINDOW_WIDTH, height=QUICK_WINDOW_HEIGHT, gap=10):
    """Anchor the nearest popup corner to the cursor and keep it on-screen."""
    right = screen_x + screen_width
    bottom = screen_y + screen_height
    x = cursor_x + gap if cursor_x < screen_x + screen_width / 2 else cursor_x - width - gap
    y = cursor_y + gap if cursor_y < screen_y + screen_height / 2 else cursor_y - height - gap
    return (
        max(screen_x, min(x, right - width)),
        max(screen_y, min(y, bottom - height)),
    )


class DesktopBridge:
    """Small native-window API exposed to the local web interface."""

    def __init__(
        self, gallery=None, addons_dir=None, voice_cues_dir=None, restart_args=(), data_dir=None,
    ):
        self.window = None
        self.gallery = gallery
        self.addons_dir = Path(addons_dir) if addons_dir else None
        self.voice_cues_dir = Path(voice_cues_dir) if voice_cues_dir else None
        self.data_dir = Path(data_dir) if data_dir else None
        self.restart_args = tuple(restart_args)
        self.fullscreen = False
        self._restart_started = False

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

    def open_addons_folder(self):
        if self.addons_dir is None:
            return {"ok": False, "error": "The add-ons folder is unavailable."}
        self.addons_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(self.addons_dir))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.addons_dir)])
            else:
                subprocess.Popen(["xdg-open", str(self.addons_dir)])
            return {"ok": True, "path": str(self.addons_dir)}
        except OSError as exc:
            return {"ok": False, "error": f"Could not open the add-ons folder: {exc}"}

    def open_voice_cues_folder(self):
        if self.voice_cues_dir is None:
            return {"ok": False, "error": "The voice acknowledgement folder is unavailable."}
        self.voice_cues_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(self.voice_cues_dir))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.voice_cues_dir)])
            else:
                subprocess.Popen(["xdg-open", str(self.voice_cues_dir)])
            return {"ok": True, "path": str(self.voice_cues_dir)}
        except OSError as exc:
            return {"ok": False, "error": f"Could not open the voice acknowledgement folder: {exc}"}

    def restart_petey(self):
        """Replace this desktop process so restart cannot leave stale copies."""
        if self.window is None:
            return {"ok": False, "error": "Restart is available in the PETEY desktop window."}
        if self._restart_started:
            return {"ok": True, "restarting": True}
        self._restart_started = True
        try:
            os.chdir(PROJECT_ROOT)
            os.execv(
                sys.executable,
                [sys.executable, str(Path(__file__).resolve()), *self.restart_args],
            )
            return {"ok": True, "restarting": True}
        except OSError as exc:
            self._restart_started = False
            return {"ok": False, "error": f"Could not restart PETEY: {exc}"}

    def open_external_url(self, url):
        """Open feed links in the OS default browser, outside the app window."""
        try:
            parsed = urlsplit(str(url or ""))
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username or parsed.password):
                return False
            parsed.port  # Reject malformed ports before handing off to the browser.
        except ValueError:
            return False
        return bool(webbrowser.open(parsed.geturl(), new=1))

    def open_discord_url(self, url):
        parsed = urlsplit(str(url or ""))
        if (parsed.scheme != "https" or parsed.hostname != "discord.com"
                or parsed.username or parsed.password or parsed.port not in {None, 443}
                or parsed.path not in {"/developers/applications", "/oauth2/authorize"}):
            return False
        return bool(webbrowser.open(parsed.geturl()))

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
        return self._save_local_file(source)

    def download_addon_file(self, addon_id, relative_path):
        """Save a file from one add-on's private data directory through a native dialog."""
        if self.data_dir is None:
            return {"ok": False, "error": "The add-on data folder is unavailable."}
        addon_id = str(addon_id or "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", addon_id):
            return {"ok": False, "error": "Invalid add-on identifier."}
        candidate = Path(str(relative_path or ""))
        if not str(candidate) or candidate.is_absolute():
            return {"ok": False, "error": "Invalid add-on file path."}
        root = (self.data_dir / "addon-data" / addon_id).resolve()
        source = (root / candidate).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            return {"ok": False, "error": "The add-on file could not be found."}
        return self._save_local_file(source)

    def _save_local_file(self, source):
        if self.window is None:
            return {"ok": False, "error": "The native save dialog is unavailable."}
        source = Path(source)
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


def configure_linux_window_identity(backend):
    """Match the Qt window to its desktop entry on Wayland and X11."""
    if sys.platform != "linux" or backend != "qt":
        return
    from qtpy.QtCore import QCoreApplication
    from qtpy.QtGui import QGuiApplication

    QCoreApplication.setApplicationName(DESKTOP_APP_ID)
    QGuiApplication.setDesktopFileName(DESKTOP_APP_ID)


def run_in_browser(url, reason=None):
    if reason:
        print(f"[DESKTOP] {reason}")
    print("[DESKTOP] Opening Petey in your browser instead.")
    webbrowser.open(url)
    input("Press Enter to stop Petey.\n")


def lan_ip_address() -> str:
    """Return the most useful IPv4 address for another device on this LAN."""
    candidates = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # UDP connect selects a route without sending application data.
            probe.connect(("192.0.2.1", 9))
            candidates.append(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        candidates.extend(
            address[4][0]
            for address in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        )
    except OSError:
        pass
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.version == 4 and not address.is_loopback and not address.is_unspecified:
            return candidate
    return "127.0.0.1"


@dataclass(frozen=True)
class LanCertificates:
    ca_certificate: Path
    server_certificate: Path
    server_key: Path
    ca_created: bool


def _run_openssl(*arguments: str) -> None:
    executable = shutil.which("openssl")
    if not executable:
        raise RuntimeError(
            "Trusted phone access needs OpenSSL. Install the openssl package and try again."
        )
    try:
        subprocess.run(
            [executable, *arguments], check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = str(exc.stderr or exc.stdout or exc).strip().splitlines()[-1]
        raise RuntimeError(f"Could not create PETEY's LAN certificate: {detail}") from exc


def ensure_lan_certificates(address: str, data_directory: str | Path | None = None) -> LanCertificates:
    """Create a private local CA once and a fresh server certificate for this LAN IP."""
    try:
        parsed_address = ipaddress.ip_address(address)
    except ValueError as exc:
        raise RuntimeError("PETEY could not determine a valid LAN IP address.") from exc
    if parsed_address.is_loopback or parsed_address.is_unspecified:
        raise RuntimeError("PETEY could not find a LAN address for trusted phone access.")

    directory = Path(data_directory or default_data_dir()) / LAN_TLS_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    ca_key = directory / "petey-local-ca.key"
    ca_certificate = directory / "petey-local-ca.crt"
    server_key = directory / "petey-lan.key"
    server_request = directory / "petey-lan.csr"
    server_certificate = directory / "petey-lan.crt"
    extensions = directory / "petey-lan.ext"
    serial = directory / "petey-local-ca.srl"

    ca_created = not (ca_key.is_file() and ca_certificate.is_file())
    if ca_created:
        for path in (ca_key, ca_certificate, serial):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        _run_openssl(
            "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:3072",
            "-out", str(ca_key),
        )
        _run_openssl(
            "req", "-x509", "-new", "-key", str(ca_key), "-sha256", "-days", "3650",
            "-subj", "/CN=PETEY Local CA",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign",
            "-out", str(ca_certificate),
        )

    extensions.write_text(
        "\n".join([
            "basicConstraints=critical,CA:FALSE",
            "keyUsage=critical,digitalSignature,keyEncipherment",
            "extendedKeyUsage=serverAuth",
            f"subjectAltName=IP:{address},DNS:localhost",
            "",
        ]),
        encoding="utf-8",
    )
    _run_openssl(
        "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
        "-out", str(server_key),
    )
    _run_openssl(
        "req", "-new", "-key", str(server_key), "-subj", "/CN=PETEY LAN",
        "-out", str(server_request),
    )
    _run_openssl(
        "x509", "-req", "-in", str(server_request), "-CA", str(ca_certificate),
        "-CAkey", str(ca_key), "-CAcreateserial", "-out", str(server_certificate),
        "-days", "365", "-sha256", "-extfile", str(extensions),
    )
    for path in (ca_key, server_key):
        try:
            path.chmod(0o600)
        except OSError:
            pass
    for path in (server_request, extensions):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return LanCertificates(ca_certificate, server_certificate, server_key, ca_created)


def certificate_setup_app(ca_certificate: Path, access_token: str) -> Flask:
    """Serve only the public CA certificate and phone installation instructions."""
    app = Flask("petey-lan-certificate-setup")

    def authorized() -> bool:
        supplied = request.args.get("access_token", "")
        return bool(supplied and hmac.compare_digest(supplied, access_token))

    @app.get("/")
    def instructions():
        if not authorized():
            return Response("Use the private setup link printed by PETEY.", status=401)
        download = "/petey-local-ca.crt?" + urlencode({"access_token": access_token})
        return Response(
            f"""<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'>
<title>PETEY trusted microphone setup</title><style>
body{{margin:0;background:#09070e;color:#f4f0ff;font:16px system-ui,sans-serif}}
main{{max-width:680px;margin:auto;padding:32px 22px 60px}}h1{{font-size:28px}}h2{{margin-top:30px;font-size:18px}}
p,li{{color:#c8bed8;line-height:1.55}}a{{display:inline-block;margin:10px 0;padding:13px 17px;border-radius:10px;background:#7650dc;color:white;text-decoration:none;font-weight:700}}
.note{{padding:14px;border:1px solid #3b3150;border-radius:10px;background:#15101f}}
</style></head><body><main><h1>Trust PETEY on this phone</h1>
<p>Install PETEY's public local certificate once. Its private key never leaves your computer.</p>
<a href='{download}' download='petey-local-ca.crt'>Download PETEY certificate</a>
<h2>iPhone or iPad</h2><ol><li>Download and allow the configuration profile.</li><li>Open Settings → Profile Downloaded and install it.</li><li>Open Settings → General → About → Certificate Trust Settings and enable full trust for PETEY Local CA.</li></ol>
<h2>Android</h2><ol><li>Download the certificate.</li><li>Open Settings → Security &amp; privacy → More security settings → Install a certificate → CA certificate.</li><li>Select the downloaded PETEY certificate. Menu names vary by phone.</li></ol>
<p class=note>When installation is complete, return to the computer and press Enter. PETEY will switch this port to HTTPS.</p>
</main></body></html>""",
            content_type="text/html; charset=utf-8",
        )

    @app.get("/petey-local-ca.crt")
    def download_certificate():
        if not authorized():
            return Response("Use the private setup link printed by PETEY.", status=401)
        return send_file(
            ca_certificate,
            mimetype="application/x-x509-ca-cert",
            as_attachment=True,
            download_name="petey-local-ca.crt",
            max_age=0,
        )

    return app


class CertificateSetupServer:
    def __init__(self, host: str, port: int, ca_certificate: Path, access_token: str):
        self.app = certificate_setup_app(ca_certificate, access_token)
        self.server = make_server(host, port, self.app, threaded=True)
        self.thread = threading.Thread(
            target=self.server.serve_forever, name="petey-certificate-setup", daemon=True,
        )

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.thread.join(timeout=5)


def protect_lan_app(
    app, access_token: str, secure_cookie: bool | None = False,
    cookie_max_age: int = 12 * 60 * 60,
):
    """Require a secret URL once, then retain access in a strict browser cookie."""
    cookie_name = "petey_lan_session"

    @app.before_request
    def require_lan_session():
        supplied = request.args.get("access_token", "")
        if supplied and hmac.compare_digest(supplied, access_token):
            response = redirect(request.path or "/")
            request_is_secure = (
                bool(secure_cookie)
                if secure_cookie is not None
                else request.is_secure
                or request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip() == "https"
            )
            response.set_cookie(
                cookie_name,
                access_token,
                max_age=cookie_max_age,
                httponly=True,
                # A phone commonly opens this link from a messaging app or QR
                # scanner. SameSite=Strict can suppress the new cookie for the
                # redirect that immediately follows that cross-site navigation.
                samesite="Lax",
                path="/",
                secure=request_is_secure,
            )
            return response
        saved = request.cookies.get(cookie_name, "")
        if saved and hmac.compare_digest(saved, access_token):
            return None
        return Response(
            "PETEY phone access requires the private link printed on the computer.",
            status=401,
            content_type="text/plain; charset=utf-8",
        )


class LocalServer:
    def __init__(
        self, host="127.0.0.1", port=0, access_token=None, ssl_context=None,
        advertised_host=None, mirror_hosts=(), cookie_max_age=12 * 60 * 60,
    ):
        if host not in {"127.0.0.1", "localhost", "::1"} and not access_token:
            raise ValueError("Network access requires an access token.")
        if any(item not in {"127.0.0.1", "::1"} for item in mirror_hosts):
            raise ValueError("Mirror servers must use a loopback address.")
        self.host = host
        self.access_token = access_token
        self.scheme = "https" if ssl_context else "http"
        self.advertised_host = advertised_host
        self.app = create_desktop_app()
        if access_token:
            protect_lan_app(
                self.app, access_token,
                secure_cookie=True if ssl_context else None,
                cookie_max_age=cookie_max_age,
            )
        self.server = make_server(host, port, self.app, threaded=True, ssl_context=ssl_context)
        self.servers = [self.server]
        for mirror_host in mirror_hosts:
            try:
                self.servers.append(make_server(
                    mirror_host, self.server.server_port, self.app,
                    threaded=True, ssl_context=ssl_context,
                ))
            except OSError:
                # IPv6 is optional on supported systems. Keep the primary
                # loopback listener when this address family is unavailable.
                continue
        self.threads = [
            threading.Thread(
                target=server.serve_forever,
                name=f"petey-local-web-{index}", daemon=True,
            )
            for index, server in enumerate(self.servers)
        ]
        self.thread = self.threads[0]

    @property
    def url(self):
        return f"{self.scheme}://127.0.0.1:{self.server.server_port}"

    @property
    def phone_url(self):
        if not self.access_token:
            return ""
        query = urlencode({"access_token": self.access_token})
        host = self.advertised_host or lan_ip_address()
        return f"{self.scheme}://{host}:{self.server.server_port}/?{query}"

    @property
    def private_url(self):
        if not self.access_token:
            return self.url
        query = urlencode({"access_token": self.access_token})
        return f"{self.url}/?{query}"

    def start(self):
        for thread in self.threads:
            thread.start()

    def close(self):
        discord = self.app.config.get("PETEY_DISCORD")
        if discord is not None:
            discord.close()
        for server in self.servers:
            server.shutdown()
        for thread in self.threads:
            thread.join(timeout=5)
        self.app.config["PETEY_ADDONS"].close()
        jobs = self.app.config.get("PETEY_MEDIA_JOBS")
        if jobs is not None:
            jobs.close()
        self.app.config["PETEY_MCP"].close()
        self.app.config["PETEY_RUNTIME"].close()


def main():
    parser = argparse.ArgumentParser(description="Run the Petey desktop assistant")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open the local interface in a browser for development",
    )
    parser.add_argument(
        "--lan",
        action="store_true",
        help="Share PETEY with a phone on this local network using a private link",
    )
    parser.add_argument(
        "--lan-https",
        action="store_true",
        help="Share PETEY over trusted HTTPS so a phone can use live microphone capture",
    )
    parser.add_argument(
        "--cloudflare",
        action="store_true",
        help="Serve PETEY through an existing named Cloudflare Tunnel",
    )
    parser.add_argument(
        "--cloudflare-hostname",
        default=os.getenv("PETEY_CLOUDFLARE_HOSTNAME", ""),
        help="Public hostname routed by the named tunnel (or PETEY_CLOUDFLARE_HOSTNAME)",
    )
    parser.add_argument(
        "--rotate-mobile-access",
        action="store_true",
        help="Replace the saved Cloudflare mobile pairing link and revoke paired browsers",
    )
    parser.add_argument(
        "--install-lan-certificate",
        action="store_true",
        help="Show the phone certificate installation page again (requires --lan-https)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="TCP port used with --lan, --lan-https, or --cloudflare (default: 8765)",
    )
    parser.add_argument(
        "--install-shortcut",
        action="store_true",
        help="Install PETEY in the current Linux user's application menu",
    )
    parser.add_argument(
        "--install-quick-hotkey",
        action="store_true",
        help="Bind Super+F1 to Quick PETEY in the COSMIC desktop",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Open the compact PETEY window at the mouse cursor",
    )
    args = parser.parse_args()

    cloudflare_port = os.getenv("PETEY_CLOUDFLARE_PORT", "8765") if args.cloudflare else "8765"
    try:
        port = args.port if args.port is not None else int(cloudflare_port)
    except ValueError:
        parser.error("PETEY_CLOUDFLARE_PORT must be a TCP port number")
    if not 1 <= port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if sum(bool(mode) for mode in (args.lan, args.lan_https, args.cloudflare)) > 1:
        parser.error("Choose only one of --lan, --lan-https, or --cloudflare.")
    if (args.lan or args.lan_https or args.cloudflare) and args.quick:
        parser.error("Network access and --quick cannot be used together")
    if args.install_lan_certificate and not args.lan_https:
        parser.error("--install-lan-certificate requires --lan-https")
    if args.rotate_mobile_access and not args.cloudflare:
        parser.error("--rotate-mobile-access requires --cloudflare")
    cloudflare_hostname = str(args.cloudflare_hostname or "").strip().lower()
    if args.cloudflare and not re.fullmatch(
        r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
        cloudflare_hostname,
    ):
        parser.error(
            "--cloudflare needs a valid --cloudflare-hostname or "
            "PETEY_CLOUDFLARE_HOSTNAME"
        )

    if args.install_shortcut:
        try:
            launcher = install_linux_desktop_shortcut(
                cloudflare=args.cloudflare,
                cloudflare_hostname=cloudflare_hostname,
                cloudflare_port=port if args.cloudflare else None,
            )
        except RuntimeError as exc:
            parser.error(str(exc))
        print(f"[DESKTOP] Installed launcher: {launcher}")
        return

    if args.install_quick_hotkey:
        try:
            path = install_cosmic_quick_hotkey()
        except RuntimeError as exc:
            parser.error(str(exc))
        print(f"[DESKTOP] Installed Super+F1 shortcut: {path}")
        return

    if args.quick and sys.platform == "linux":
        # Qt chooses its platform plugin at import time. XWayland is intentional:
        # Wayland clients cannot place a popup at an exact global cursor position.
        os.environ["QT_QPA_PLATFORM"] = "xcb"

    network_enabled = args.lan or args.lan_https or args.cloudflare
    lan_enabled = args.lan or args.lan_https
    if args.cloudflare:
        access_token = persistent_remote_access_token(rotate=args.rotate_mobile_access)
    else:
        access_token = secrets.token_urlsafe(24) if network_enabled else None
    advertised_host = lan_ip_address() if lan_enabled else None
    ssl_context = None
    certificates = None
    if args.lan_https:
        try:
            certificates = ensure_lan_certificates(advertised_host)
        except RuntimeError as exc:
            parser.error(str(exc))
        if args.lan_https and (certificates.ca_created or args.install_lan_certificate):
            setup = CertificateSetupServer(
                "0.0.0.0", port, certificates.ca_certificate, access_token,
            )
            setup.start()
            setup_query = urlencode({"access_token": access_token})
            setup_url = f"http://{advertised_host}:{port}/?{setup_query}"
            print("[DESKTOP] First, install PETEY's public certificate on your phone:")
            print(setup_url)
            print(f"[DESKTOP] Certificate file: {certificates.ca_certificate}")
            try:
                input("After the phone trusts PETEY Local CA, press Enter to start HTTPS.\n")
            except KeyboardInterrupt:
                print("\n[DESKTOP] Certificate setup stopped.")
                return
            finally:
                setup.close()
        ssl_context = (
            str(certificates.server_certificate), str(certificates.server_key),
        )
    local = LocalServer(
        host="0.0.0.0" if lan_enabled else "127.0.0.1",
        port=port if network_enabled else 0,
        access_token=access_token,
        ssl_context=ssl_context,
        advertised_host=advertised_host,
        mirror_hosts=("::1",) if args.cloudflare else (),
        cookie_max_age=REMOTE_SESSION_SECONDS if args.cloudflare else 12 * 60 * 60,
    )
    local.start()
    print(f"[DESKTOP] Petey is running locally at {local.url}")
    desktop_url = local.private_url if args.cloudflare else local.url
    try:
        if args.cloudflare:
            public_query = urlencode({"access_token": access_token})
            print(f"[DESKTOP] Named tunnel origin: http://localhost:{port}")
            print(f"[DESKTOP] Open this private PETEY link from anywhere:\nhttps://{cloudflare_hostname}/?{public_query}")
            print("[DESKTOP] The bare hostname is blocked even if Cloudflare Access is misconfigured.")
            print("[DESKTOP] Paired browsers stay authorized for one year. Use --rotate-mobile-access to revoke them.")

        if lan_enabled:
            print(f"[DESKTOP] Open this private link on your phone:\n{local.phone_url}")
            print("[DESKTOP] Keep the link private. It grants access to this PETEY session.")
            input("Press Enter to stop phone access.\n")
            return

        if args.quick:
            from petey.quick_window import run_quick_window

            run_quick_window(
                local.url, application_icon_path(), PROJECT_ROOT, quick_window_position
            )
            return

        if args.browser:
            run_in_browser(desktop_url)
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
        bridge = DesktopBridge(
            local.app.config["PETEY_GALLERY"],
            local.app.config["PETEY_ADDONS"].user_dir,
            local.app.config["PETEY_VOICE_CUES"].root,
            restart_args=(
                "--cloudflare", "--cloudflare-hostname", cloudflare_hostname,
                "--port", str(port),
            ) if args.cloudflare else (),
            data_dir=state.data_dir,
        )
        bridge.window = webview.create_window(
            "PETEY",
            desktop_url,
            width=1180,
            height=780,
            min_size=(760, 560),
            on_top=bool(state.preferences.get("always_on_top", False)),
            text_select=True,
            js_api=bridge,
        )
        try:
            backend = preferred_linux_webview_backend()
            configure_linux_window_identity(backend)
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
