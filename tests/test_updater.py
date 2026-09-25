import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import zipfile

from petey.addons import AddonManager
from petey.desktop_state import DesktopState
from petey.updater import PeteyUpdater, UpdateError, repository_slug, version_key
from web.desktop_app import create_desktop_app


REPOSITORY = "https://github.com/example/petey-sample"


def write_addon(root: Path, version="1.0.0") -> Path:
    directory = root / "sample-addon"
    directory.mkdir(parents=True)
    (directory / "petey-addon.json").write_text(json.dumps({
        "api_version": 1,
        "id": "sample-addon",
        "name": "Sample",
        "version": version,
        "description": "Updater fixture",
        "entrypoint": "addon.py",
        "repository": REPOSITORY,
    }), encoding="utf-8")
    (directory / "addon.py").write_text("def setup(context): return None\n", encoding="utf-8")
    (directory / "old.txt").write_text("old", encoding="utf-8")
    return directory


def package(version="1.1.0", addon_id="sample-addon", unsafe_name=None) -> bytes:
    manifest = {
        "api_version": 1,
        "id": addon_id,
        "name": "Sample",
        "version": version,
        "description": "Updater fixture",
        "entrypoint": "addon.py",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("release/petey-addon.json", json.dumps(manifest))
        archive.writestr("release/addon.py", "def setup(context): return None\n")
        archive.writestr(unsafe_name or "release/new.txt", "new")
    return output.getvalue()


class FakeResponse:
    def __init__(self, *, payload=None, content=b""):
        self.payload = payload
        self.content = content
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload

    def iter_content(self, _size):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeSession:
    def __init__(self, archive):
        self.archive = archive

    def get(self, url, **_kwargs):
        if url.startswith("https://api.github.com/"):
            return FakeResponse(payload={
                "tag_name": "v1.1.0",
                "html_url": f"{REPOSITORY}/releases/tag/v1.1.0",
                "assets": [{
                    "name": "sample-addon-v1.1.0.zip",
                    "size": len(self.archive),
                    "browser_download_url": f"{REPOSITORY}/releases/download/v1.1.0/sample-addon.zip",
                }],
            })
        return FakeResponse(content=self.archive)


class UpdaterTests(unittest.TestCase):
    def test_missing_release_has_a_clear_status(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            write_addon(state.data_dir / "addons")
            manager = AddonManager(state)
            session = MagicMock()
            response = MagicMock(status_code=404)
            session.get.return_value = response
            updater = PeteyUpdater(manager, session=session)
            result = updater.check_all()["addons"][0]
            self.assertEqual(result["error"], "No published GitHub release yet.")

    def test_version_and_repository_normalization(self):
        self.assertGreater(version_key("1.2.0"), version_key("1.2.0-beta"))
        self.assertEqual(repository_slug(REPOSITORY + ".git"), "example/petey-sample")
        with self.assertRaises(UpdateError):
            repository_slug("https://example.com/project")

    def test_addon_update_replaces_code_and_preserves_data(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            addon = write_addon(state.data_dir / "addons")
            saved = state.data_dir / "addon-data/sample-addon/saved.json"
            saved.parent.mkdir(parents=True)
            saved.write_text("saved", encoding="utf-8")
            manager = AddonManager(state)
            updater = PeteyUpdater(manager, session=FakeSession(package()))

            checked = updater.check_addon("sample-addon")
            self.assertTrue(checked["installable"])
            installed = updater.install_addon("sample-addon")

            self.assertTrue(installed["restart_required"])
            self.assertFalse((addon / "old.txt").exists())
            self.assertTrue((addon / "new.txt").is_file())
            self.assertEqual(saved.read_text(encoding="utf-8"), "saved")
            manifest = json.loads((addon / "petey-addon.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["repository"], REPOSITORY)

    def test_addon_update_rejects_unsafe_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            addon = write_addon(state.data_dir / "addons")
            manager = AddonManager(state)
            updater = PeteyUpdater(manager, session=FakeSession(package(unsafe_name="../escape")))
            with self.assertRaisesRegex(UpdateError, "unsafe path"):
                updater.install_addon("sample-addon")
            self.assertTrue((addon / "old.txt").is_file())

    @patch("petey.updater.subprocess.run")
    def test_petey_update_requires_clean_fast_forward(self, run):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            manager = MagicMock()
            manager._records = {}
            outputs = {
                ("remote", "get-url", "origin"): "https://github.com/bizzomephisto/PETEY-DESKTOP.git\n",
                ("fetch", "--quiet", "origin", "main"): "",
                ("rev-parse", "HEAD"): "a" * 40 + "\n",
                ("rev-parse", "origin/main"): "b" * 40 + "\n",
                ("status", "--porcelain", "--untracked-files=no"): "",
                ("rev-list", "--count", "HEAD..origin/main"): "2\n",
            }

            def result(command, **_kwargs):
                value = MagicMock(returncode=0, stdout="", stderr="")
                if command[1] == "merge-base":
                    return value
                value.stdout = outputs[tuple(command[1:])]
                return value

            run.side_effect = result
            status = PeteyUpdater(manager, project_root=root).check_petey()
            self.assertTrue(status["installable"])
            self.assertEqual(status["commits_behind"], 2)

    def test_update_routes_use_injected_updater(self):
        with tempfile.TemporaryDirectory() as directory:
            updater = MagicMock()
            updater.check_all.return_value = {"petey": {"id": "petey"}, "addons": []}
            updater.install_petey.return_value = {"installed": True}
            state = DesktopState(directory)
            app = create_desktop_app(
                state=state, memory=MagicMock(), job_manager=MagicMock(), updater=updater,
            )
            client = app.test_client()
            self.assertEqual(client.get("/api/desktop/updates").status_code, 200)
            self.assertTrue(client.post("/api/desktop/updates/petey/install").json["installed"])
            updater.install_petey.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
