import tempfile
import unittest
from pathlib import Path

from petey.desktop_state import DesktopState
from petey.workspace import WorkspaceError, WorkspaceService
from web.desktop_app import create_desktop_app


class WorkspaceServiceTests(unittest.TestCase):
    def make_service(self, directory):
        state = DesktopState(Path(directory) / "state")
        root = Path(directory) / "project"
        root.mkdir()
        workspace = state.add_workspace(str(root))
        return state, root, workspace, WorkspaceService(state)

    def test_approved_folders_persist_without_touching_files(self):
        with tempfile.TemporaryDirectory() as directory:
            state, root, workspace, _ = self.make_service(directory)
            self.assertEqual(state.active_workspace_id, workspace["id"])
            self.assertEqual(DesktopState(Path(directory) / "state").workspaces[0]["path"], str(root))
            removed = state.remove_workspace(workspace["id"])
            self.assertEqual(removed["path"], str(root))
            self.assertTrue(root.exists())

    def test_traversal_and_escaping_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _, root, workspace, service = self.make_service(directory)
            outside = Path(directory) / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            (root / "escape").symlink_to(outside)
            for path in ("../outside.txt", "escape"):
                with self.subTest(path=path), self.assertRaises(WorkspaceError):
                    service.read_file(workspace["id"], path)

    def test_stale_edit_is_rejected_and_proposal_is_one_shot(self):
        with tempfile.TemporaryDirectory() as directory:
            _, root, workspace, service = self.make_service(directory)
            target = root / "hello.py"
            target.write_text("print('old')\n", encoding="utf-8")
            opened = service.read_file(workspace["id"], "hello.py")
            target.write_text("print('someone else')\n", encoding="utf-8")
            with self.assertRaises(WorkspaceError):
                service.write_file(workspace["id"], "hello.py", "print('new')\n", opened["sha256"])

            proposal = service.propose_write(workspace["id"], "hello.py", "print('approved')\n")
            service.approve(proposal["id"])
            self.assertEqual(target.read_text(encoding="utf-8"), "print('approved')\n")
            with self.assertRaises(WorkspaceError):
                service.approve(proposal["id"])

    def test_command_does_not_run_until_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            _, root, workspace, service = self.make_service(directory)
            proposal = service.propose_command(workspace["id"], "printf approved > result.txt")
            self.assertFalse((root / "result.txt").exists())
            result = service.approve(proposal["id"])
            self.assertEqual(result["run"]["exit_code"], 0)
            self.assertEqual((root / "result.txt").read_text(encoding="utf-8"), "approved")

    def test_workspace_routes_save_and_gate_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            state, root, workspace, service = self.make_service(directory)
            app = create_desktop_app(state=state, runtime=object(), workspace_service=service)
            client = app.test_client()
            saved = client.put("/api/desktop/workspace/file", json={
                "workspace_id": workspace["id"], "path": "note.txt", "content": "hello",
            })
            self.assertEqual(saved.status_code, 200)
            preview = client.post("/api/desktop/workspace/command", json={
                "workspace_id": workspace["id"], "command": "printf api > api.txt",
            })
            self.assertEqual(preview.status_code, 201)
            self.assertFalse((root / "api.txt").exists())
            proposal_id = preview.get_json()["proposal"]["id"]
            approved = client.post(f"/api/desktop/workspace/proposals/{proposal_id}/approve")
            self.assertEqual(approved.status_code, 200)
            self.assertTrue((root / "api.txt").exists())


if __name__ == "__main__":
    unittest.main()
