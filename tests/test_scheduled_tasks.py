import datetime as dt
import tempfile
import unittest
from pathlib import Path

from petey.scheduled_tasks import ScheduledTaskError, ScheduledTaskService, UTC


class ScheduledTaskTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.now = [dt.datetime(2026, 9, 27, 20, 0, tzinfo=UTC)]
        self.announcements = []
        self.executions = []
        self.path = Path(self.directory.name) / "scheduled-tasks.json"
        self.service = ScheduledTaskService(
            self.path,
            lambda message, **kwargs: self.announcements.append((message, kwargs)),
            clock=lambda: self.now[0],
            poll_seconds=3600,
        )
        self.addCleanup(self.service.close)
        self.service.register_action(
            "example", "capture", "Capture camera",
            [{"name": "camera_name", "label": "Camera name", "type": "text"}],
            lambda args: self.executions.append(args) or {
                "message": "Captured a frame.",
                "metadata": {"chat_image_url": "/api/addons/example/snapshots/test"},
            },
        )

    def payload(self, **changes):
        value = {
            "title": "Shedfeed", "action_id": "example.capture",
            "arguments": {"camera_name": "Shedfeed"},
            "start_date": "2026-09-27", "time": "15:30",
            "timezone": "America/Chicago", "recurrence": "once",
            "enabled": True,
        }
        value.update(changes)
        return value

    def test_one_time_action_runs_once_and_survives_reload(self):
        task = self.service.save_task(self.payload())
        self.assertEqual(task["next_run_at"], "2026-09-27T20:30:00+00:00")
        self.now[0] = dt.datetime(2026, 9, 27, 20, 30, tzinfo=UTC)
        self.service.run_due()
        self.service.run_due()
        self.assertEqual(self.executions, [{"camera_name": "Shedfeed"}])
        self.assertEqual(len(self.announcements), 1)
        self.assertEqual(
            self.announcements[0][1]["metadata"]["chat_image_url"],
            "/api/addons/example/snapshots/test",
        )
        reloaded = ScheduledTaskService(self.path, lambda *_args, **_kwargs: None,
                                        clock=lambda: self.now[0])
        self.addCleanup(reloaded.close)
        self.assertIsNone(reloaded.public_state()["tasks"][0]["next_run_at"])

    def test_daily_recurrence_uses_local_wall_time_across_dst(self):
        self.now[0] = dt.datetime(2026, 10, 31, 19, 0, tzinfo=UTC)
        task = self.service.save_task(self.payload(
            start_date="2026-10-31", time="15:30", recurrence="daily",
        ))
        self.assertEqual(task["next_run_at"], "2026-10-31T20:30:00+00:00")
        self.now[0] = dt.datetime(2026, 10, 31, 20, 30, tzinfo=UTC)
        self.service.run_due()
        self.assertEqual(
            self.service.public_state()["tasks"][0]["next_run_at"],
            "2026-11-01T21:30:00+00:00",
        )

    def test_monthly_recurring_day_clamps_to_short_month(self):
        self.now[0] = dt.datetime(2027, 1, 31, 19, 0, tzinfo=UTC)
        self.service.save_task(self.payload(
            start_date="2027-01-31", time="14:30", recurrence="monthly",
        ))
        self.now[0] = dt.datetime(2027, 1, 31, 20, 30, tzinfo=UTC)
        self.service.run_due()
        self.assertEqual(
            self.service.public_state()["tasks"][0]["next_run_at"],
            "2027-02-28T20:30:00+00:00",
        )

    def test_missed_task_does_not_execute_late(self):
        self.service.save_task(self.payload())
        self.now[0] = dt.datetime(2026, 9, 27, 21, 0, tzinfo=UTC)
        self.service.run_due()
        self.assertEqual(self.executions, [])
        self.assertIn("Missed", self.service.public_state()["tasks"][0]["last_status"])

    def test_action_arguments_are_validated_and_unavailable_action_fails_closed(self):
        with self.assertRaises(ScheduledTaskError):
            self.service.save_task(self.payload(arguments={"camera_name": ""}))
        task = self.service.save_task(self.payload())
        self.service.unregister_action("example.capture")
        self.assertIn("Failed", self.service.run_now(task["id"])["status"])
        self.assertEqual(self.executions, [])

    def test_announcement_failure_does_not_mark_completed_action_as_failed(self):
        task = self.service.save_task(self.payload())
        self.service._announce = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("queue full"))
        status = self.service.run_now(task["id"])["status"]
        self.assertEqual(self.executions, [{"camera_name": "Shedfeed"}])
        self.assertIn("Action ran; PETEY announcement failed", status)

    def test_selected_sunday_and_thursday_run_at_local_wall_time(self):
        task = self.service.save_task(self.payload(
            start_date="2026-09-27", time="15:30", recurrence="selected_days",
            selected_days=[0, 4],
        ))
        self.assertEqual(task["next_run_at"], "2026-09-27T20:30:00+00:00")
        self.now[0] = dt.datetime(2026, 9, 27, 20, 30, tzinfo=UTC)
        self.service.run_due()
        self.assertEqual(self.service.public_state()["tasks"][0]["next_run_at"],
                         "2026-10-01T20:30:00+00:00")

    def test_multiple_steps_run_in_order_and_stop_after_failure(self):
        self.service.register_action("example", "fail", "Fail deliberately", [],
                                     lambda _args: (_ for _ in ()).throw(ValueError("offline")))
        self.service.register_action("example", "later", "Later", [],
                                     lambda _args: self.executions.append("later") or {"message": "Later"})
        task = self.service.save_task(self.payload(steps=[
            {"action_id": "example.capture", "arguments": {"camera_name": "Shedfeed"}},
            {"action_id": "example.fail", "arguments": {}},
            {"action_id": "example.later", "arguments": {}},
        ]))
        result = self.service.run_now(task["id"])
        self.assertIn("Failed after 1 of 3 steps", result["status"])
        self.assertEqual(self.executions, [{"camera_name": "Shedfeed"}])
        self.assertIn("Completed: 1. Captured a frame.", self.announcements[0][0])

    def test_preview_can_expand_one_typed_instruction_into_two_steps(self):
        self.service.register_action("example", "lights", "Control lights",
            [{"name": "name", "label": "Light"}], lambda args: {"message": args["name"]},
            prepare=lambda _instruction: [
                {"arguments": {"name": "Outside"}, "summary": "Turn on Outside"},
                {"arguments": {"name": "Living room"}, "summary": "Dim Living room"},
            ])
        steps = self.service.preview_steps([{
            "action_id": "example.lights", "instruction": "turn on outside and dim living room",
        }])
        self.assertEqual([step["summary"] for step in steps],
                         ["Turn on Outside", "Dim Living room"])


if __name__ == "__main__":
    unittest.main()
