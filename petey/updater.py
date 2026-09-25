"""Explicit, bounded updates for PETEY and repository-declared add-ons."""

from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import uuid
import zipfile

import requests

from petey.http_client import SESSION as HTTP_SESSION
from petey.version import PROJECT_URL, __version__


GITHUB_REPOSITORY = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)
MAX_ARCHIVE_BYTES = 30 * 1024 * 1024
MAX_ARCHIVE_FILES = 1000
MAX_EXTRACTED_BYTES = 80 * 1024 * 1024
OFFICIAL_ADDON_REPOSITORIES = {
    "home-assistant": "https://github.com/bizzomephisto/PETEY-HOME-ASSISTANT",
    "petey-conference": "https://github.com/bizzomephisto/PETEY-CONFERENCE",
    "petey-google-sheets": "https://github.com/bizzomephisto/PETEY-GOOGLE-SHEETS",
    "petey-life": "https://github.com/bizzomephisto/PETEY-LIFE",
    "petey-opencode": "https://github.com/bizzomephisto/PETEY-OPENCODE",
    "petey-webcam": "https://github.com/bizzomephisto/PETEY-WEBCAM",
    "quick-actions": "https://github.com/bizzomephisto/PETEY-QUICK-ACTIONS",
    "spotify": "https://github.com/bizzomephisto/PETEY-SPOTIFY",
}


class UpdateError(RuntimeError):
    pass


def version_key(value: object) -> tuple:
    text = str(value or "").strip().lower().lstrip("v")
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+](.*))?$", text)
    if not match:
        return (0, 0, 0, 0, text)
    major, minor, patch = (int(item or 0) for item in match.groups()[:3])
    suffix = match.group(4) or ""
    return (major, minor, patch, 1 if not suffix else 0, suffix)


def repository_slug(url: object) -> str:
    match = GITHUB_REPOSITORY.fullmatch(str(url or "").strip())
    if not match:
        raise UpdateError("Updates require an HTTPS github.com repository URL.")
    return f"{match.group(1)}/{match.group(2)}"


class PeteyUpdater:
    def __init__(self, addon_manager, project_root: str | Path | None = None, session=None):
        self.addons = addon_manager
        self.project_root = Path(project_root or Path(__file__).resolve().parents[1])
        self.session = session or HTTP_SESSION
        self._install_lock = threading.Lock()

    def _git(self, *arguments: str, timeout: int = 45, check: bool = True) -> str:
        try:
            result = subprocess.run(
                ["git", *arguments], cwd=self.project_root, capture_output=True,
                text=True, timeout=timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UpdateError(f"Git could not run: {exc}") from exc
        if check and result.returncode:
            detail = (result.stderr or result.stdout or "Git command failed.").strip()
            raise UpdateError(detail[:500])
        return result.stdout.strip()

    def check_petey(self) -> dict:
        result = {
            "id": "petey", "name": "PETEY Desktop", "current": __version__,
            "supported": False, "update_available": False,
        }
        if not (self.project_root / ".git").exists():
            result["message"] = "This PETEY copy is not a Git checkout. Update it manually."
            return result
        origin = self._git("remote", "get-url", "origin")
        accepted = {
            "https://github.com/bizzomephisto/PETEY-DESKTOP.git",
            "https://github.com/bizzomephisto/PETEY-DESKTOP",
            "git@github.com:bizzomephisto/PETEY-DESKTOP.git",
        }
        if origin not in accepted:
            result["message"] = "Automatic updates require the official PETEY GitHub origin."
            return result
        self._git("fetch", "--quiet", "origin", "main", timeout=90)
        current = self._git("rev-parse", "HEAD")
        latest = self._git("rev-parse", "origin/main")
        dirty = bool(self._git("status", "--porcelain", "--untracked-files=no"))
        behind = int(self._git("rev-list", "--count", "HEAD..origin/main") or "0")
        try:
            diverged = subprocess.run(
                ["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"],
                cwd=self.project_root, capture_output=True, timeout=15,
            ).returncode != 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UpdateError(f"Git could not compare revisions: {exc}") from exc
        result.update({
            "supported": True,
            "current_revision": current[:12],
            "latest_revision": latest[:12],
            "commits_behind": behind,
            "dirty": dirty,
            "diverged": diverged,
            "update_available": behind > 0 and not diverged,
            "repository": PROJECT_URL,
        })
        if diverged:
            result["message"] = "This checkout has commits that are not a fast-forward from official main."
        elif dirty:
            result["message"] = "Tracked PETEY files have local changes; automatic install is disabled."
        elif behind:
            result["message"] = f"{behind} update commit{'s' if behind != 1 else ''} available."
        else:
            result["message"] = "PETEY is current."
        result["installable"] = result["update_available"] and not dirty
        return result

    def install_petey(self) -> dict:
        if not self._install_lock.acquire(blocking=False):
            raise UpdateError("Another update is already being installed.")
        try:
            status = self.check_petey()
            if not status.get("installable"):
                raise UpdateError(status.get("message") or "No PETEY update is ready to install.")
            self._git("merge", "--ff-only", "origin/main", timeout=90)
            return {"installed": True, "restart_required": True,
                    "revision": self._git("rev-parse", "HEAD")[:12]}
        finally:
            self._install_lock.release()

    def _latest_release(self, repository: str) -> dict:
        slug = repository_slug(repository)
        try:
            response = self.session.get(
                f"https://api.github.com/repos/{slug}/releases/latest",
                headers={"Accept": "application/vnd.github+json"}, timeout=(10, 30),
            )
            if response.status_code == 404:
                raise UpdateError("No published GitHub release yet.")
            response.raise_for_status()
            payload = response.json()
        except UpdateError:
            raise
        except (requests.RequestException, ValueError) as exc:
            raise UpdateError(f"Could not check {slug}: {exc}") from exc
        if not isinstance(payload, dict) or not payload.get("tag_name"):
            raise UpdateError(f"{slug} did not return a published release.")
        return payload

    @staticmethod
    def _release_asset(release: dict, addon_id: str) -> dict | None:
        assets = [item for item in release.get("assets") or []
                  if isinstance(item, dict) and str(item.get("name") or "").lower().endswith(".zip")]
        matching = [item for item in assets if addon_id.replace("petey-", "") in
                    str(item.get("name") or "").lower()]
        return (matching or assets or [None])[0]

    def check_addon(self, addon_id: str) -> dict:
        record = self.addons._records.get(str(addon_id))
        if not record or record.get("source") != "user":
            raise UpdateError("Only installed external add-ons can be updated here.")
        repository = str(record.get("repository") or OFFICIAL_ADDON_REPOSITORIES.get(
            str(record.get("id") or ""), ""
        ))
        base = {
            "id": record["id"], "name": record["name"], "current": record["version"],
            "repository": repository, "supported": bool(repository),
            "update_available": False, "installable": False,
        }
        if not repository:
            base["message"] = "No automatic update source is declared."
            return base
        release = self._latest_release(repository)
        latest = str(release.get("tag_name") or "").lstrip("v")
        asset = self._release_asset(release, record["id"])
        available = version_key(latest) > version_key(record["version"])
        base.update({
            "latest": latest,
            "release_url": str(release.get("html_url") or repository),
            "update_available": available,
            "installable": available and asset is not None,
            "message": (
                "Update available." if available and asset else
                "A newer release exists, but it has no ZIP package." if available else
                "Current."
            ),
        })
        return base

    def check_all(self) -> dict:
        try:
            petey = self.check_petey()
        except UpdateError as exc:
            petey = {
                "id": "petey", "name": "PETEY Desktop", "current": __version__,
                "supported": True, "update_available": False,
                "installable": False, "error": str(exc),
            }
        addons = []
        for record in self.addons._records.values():
            if record.get("source") != "user":
                continue
            try:
                addons.append(self.check_addon(record["id"]))
            except UpdateError as exc:
                addons.append({
                    "id": record["id"], "name": record["name"],
                    "current": record["version"], "supported": bool(
                        record.get("repository") or OFFICIAL_ADDON_REPOSITORIES.get(record["id"])
                    ),
                    "update_available": False, "installable": False, "error": str(exc),
                })
        return {"petey": petey, "addons": addons}

    def _download(self, url: str) -> bytes:
        try:
            with self.session.get(url, stream=True, timeout=(10, 90)) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_content(128 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise UpdateError("The add-on package exceeds 30 MiB.")
                    chunks.append(chunk)
                return b"".join(chunks)
        except requests.RequestException as exc:
            raise UpdateError(f"Could not download the add-on package: {exc}") from exc

    def _extract_package(self, data: bytes, root: Path, addon_id: str,
                         repository: str, latest: str) -> Path:
        try:
            archive = zipfile.ZipFile(BytesIO(data))
        except (OSError, zipfile.BadZipFile) as exc:
            raise UpdateError("The downloaded add-on package is not a valid ZIP file.") from exc
        infos = [item for item in archive.infolist() if not item.is_dir()]
        if len(infos) > MAX_ARCHIVE_FILES or sum(item.file_size for item in infos) > MAX_EXTRACTED_BYTES:
            raise UpdateError("The add-on package is too large after extraction.")
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (path.is_absolute() or ".." in path.parts or "\\" in item.filename
                    or stat.S_ISLNK(mode)):
                raise UpdateError("The add-on package contains an unsafe path.")
        archive.extractall(root)
        manifests = list(root.rglob("petey-addon.json"))
        if len(manifests) != 1:
            raise UpdateError("The add-on package must contain exactly one manifest.")
        manifest_path = manifests[0]
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UpdateError("The add-on package manifest is invalid.") from exc
        if str(manifest.get("id") or "") != addon_id:
            raise UpdateError("The downloaded package has the wrong add-on ID.")
        if version_key(manifest.get("version")) != version_key(latest):
            raise UpdateError("The package version does not match its GitHub release.")
        manifest["repository"] = repository
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        try:
            self.addons._validate_manifest(manifest, manifest_path.parent)
        except ValueError as exc:
            raise UpdateError(f"The add-on package failed validation: {exc}") from exc
        return manifest_path.parent

    def install_addon(self, addon_id: str) -> dict:
        if not self._install_lock.acquire(blocking=False):
            raise UpdateError("Another update is already being installed.")
        try:
            return self._install_addon(addon_id)
        finally:
            self._install_lock.release()

    def _install_addon(self, addon_id: str) -> dict:
        status = self.check_addon(addon_id)
        if not status.get("installable"):
            raise UpdateError(status.get("message") or "No add-on update is ready to install.")
        record = self.addons._records[addon_id]
        repository = str(record.get("repository") or OFFICIAL_ADDON_REPOSITORIES.get(addon_id) or "")
        release = self._latest_release(repository)
        asset = self._release_asset(release, addon_id)
        if not asset:
            raise UpdateError("The latest release has no ZIP package.")
        try:
            asset_size = int(asset.get("size") or 0)
        except (TypeError, ValueError):
            asset_size = 0
        if asset_size > MAX_ARCHIVE_BYTES:
            raise UpdateError("The add-on package exceeds 30 MiB.")
        url = str(asset.get("browser_download_url") or "")
        if not url.startswith("https://github.com/"):
            raise UpdateError("The release package URL is invalid.")
        data = self._download(url)
        target = Path(record["path"])
        work_root = target.parent.parent / "update-staging"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"{addon_id}-", dir=work_root) as temporary:
            package = self._extract_package(
                data, Path(temporary), addon_id, repository, status["latest"],
            )
            incoming = work_root / f".{addon_id}-{uuid.uuid4().hex}.incoming"
            backup = work_root / f".{addon_id}-{uuid.uuid4().hex}.backup"
            shutil.copytree(package, incoming)
            try:
                os.replace(target, backup)
                os.replace(incoming, target)
            except OSError as exc:
                if backup.exists() and not target.exists():
                    os.replace(backup, target)
                shutil.rmtree(incoming, ignore_errors=True)
                raise UpdateError(f"Could not install the add-on update: {exc}") from exc
            shutil.rmtree(backup, ignore_errors=True)
        record["update_installed"] = status["latest"]
        return {"installed": True, "version": status["latest"], "restart_required": True}
