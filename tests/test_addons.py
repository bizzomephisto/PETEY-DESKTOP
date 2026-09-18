import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from petey.addons import AddonManager
from petey.desktop_state import DesktopState
from petey.tools.registry import ToolSpec
from web.desktop_app import create_desktop_app


def write_addon(root: Path, addon_id="sample-addon", entrypoint=None):
    directory = root / addon_id
    directory.mkdir(parents=True)
    (directory / "petey-addon.json").write_text(json.dumps({
        "api_version": 1,
        "id": addon_id,
        "name": "Sample add-on",
        "version": "0.2.0",
        "description": "Test extension",
        "entrypoint": "addon.py",
        "panel": "panel.html",
        "script": "panel.js",
        "navigation": {"label": "Sample", "icon": "S"},
    }), encoding="utf-8")
    (directory / "addon.py").write_text(entrypoint or """
from flask import jsonify
class Addon:
    def __init__(self, data_dir): self.data_dir = data_dir
    def close(self):
        (self.data_dir / 'closed').write_text('yes')
def setup(context):
    context.app.add_url_rule('/api/addons/sample-addon/ping', endpoint='sample_addon_ping', view_func=lambda: jsonify({'pong': True}))
    return Addon(context.data_dir)
""", encoding="utf-8")
    (directory / "panel.html").write_text(
        '<header class="tool-header"><h1>Sample panel</h1></header>', encoding="utf-8"
    )
    (directory / "panel.js").write_text("window.sampleAddonLoaded = true;", encoding="utf-8")
    return directory


class AddonManagerTests(unittest.TestCase):
    def test_disabled_addon_is_discovered_without_importing_python(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            addons = state.data_dir / "addons"
            write_addon(addons, entrypoint="raise RuntimeError('must not import')")
            manager = AddonManager(state)
            sample = next(item for item in manager.public_status()["addons"] if item["id"] == "sample-addon")
            self.assertFalse(sample["enabled"])
            self.assertFalse(sample["loaded"])
            self.assertEqual(sample["error"], "")

    def test_enabled_addon_registers_route_panel_asset_and_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            write_addon(state.data_dir / "addons")
            state.update_addon_enabled("sample-addon", True)
            manager = AddonManager(state)
            app = create_desktop_app(
                state=state, memory=MagicMock(), job_manager=MagicMock(),
                discord_bridge=MagicMock(), addon_manager=manager,
            )
            client = app.test_client()
            self.assertEqual(client.get("/api/addons/sample-addon/ping").json, {"pong": True})
            html = client.get("/").get_data(as_text=True)
            self.assertIn('data-view="addon-sample-addon"', html)
            self.assertIn("Sample panel", html)
            self.assertIn('id="restart-petey"', html)
            response = client.get("/api/desktop/addons/sample-addon/assets/panel.js")
            self.assertEqual(response.status_code, 200)
            response.close()
            manager.close()
            self.assertTrue((state.data_dir / "addon-data/sample-addon/closed").is_file())

    def test_disabling_builtin_discord_hides_it_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            state.update_addon_enabled("discord", False)
            app = create_desktop_app(
                state=state, memory=MagicMock(), job_manager=MagicMock()
            )
            client = app.test_client()
            html = client.get("/").get_data(as_text=True)
            self.assertNotIn('id="view-discord"', html)
            self.assertNotIn('/static/discord.js', html)
            self.assertEqual(client.get("/api/desktop/discord").status_code, 404)
            discord = next(
                item for item in client.get("/api/desktop/addons").json["addons"]
                if item["id"] == "discord"
            )
            self.assertFalse(discord["enabled"])
            self.assertFalse(discord["loaded"])

    def test_addon_api_saves_toggle_and_requires_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            write_addon(state.data_dir / "addons")
            manager = AddonManager(state)
            app = create_desktop_app(
                state=state, memory=MagicMock(), job_manager=MagicMock(),
                discord_bridge=MagicMock(), addon_manager=manager,
            )
            response = app.test_client().put(
                "/api/desktop/addons/sample-addon", json={"enabled": True}
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json["addon"]["enabled"])
            self.assertTrue(response.json["restart_required"])
            self.assertTrue(DesktopState(directory).addon_enabled("sample-addon"))

    def test_loaded_addon_tools_are_namespaced_and_callable(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            addon_dir = write_addon(state.data_dir / "addons", entrypoint="""
from petey.tools.registry import ToolSpec
class Addon:
    def tool_specs(self):
        return [ToolSpec(name='forecast', description='Get weather', parameters={'type': 'object', 'properties': {}}, handler=lambda arguments: {'weather': 'sunny'})]
def setup(context): return Addon()
""")
            state.update_addon_enabled("sample-addon", True)
            manager = AddonManager(state)
            app = create_desktop_app(
                state=state, memory=MagicMock(), job_manager=MagicMock(),
                discord_bridge=MagicMock(), addon_manager=manager,
            )
            specs = manager.tool_specs()
            self.assertEqual([spec.name for spec in specs], ["addon_sample_addon__forecast"])
            self.assertEqual(specs[0].handler({}), {"weather": "sunny"})


if __name__ == "__main__":
    unittest.main()
