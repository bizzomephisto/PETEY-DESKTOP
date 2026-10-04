"""Persistent, opt-in schedules for narrowly registered PETEY add-on actions."""

from __future__ import annotations

import calendar
import datetime as dt
import json
import os
import re
import threading
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


UTC = dt.timezone.utc
ACTION_ID = re.compile(r"[a-z][a-z0-9_-]{1,48}\.[a-z][a-z0-9_-]{1,48}")
RECURRENCES = {"once", "daily", "weekly", "selected_days", "monthly"}
MAX_TASKS = 100
MAX_STEPS = 12


class ScheduledTaskError(ValueError):
    """A task configuration error suitable for the PETEY UI."""


class ScheduledTaskService:
    """Run user-saved schedules through explicit add-on handlers, never model tools."""

    def __init__(self, path: str | Path, announce, *, clock=None, poll_seconds=15):
        self.path = Path(path)
        self._announce = announce
        self._clock = clock or (lambda: dt.datetime.now(UTC))
        self._poll_seconds = poll_seconds
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._worker = None
        self._actions = {}
        self._tasks = []
        self._show_upcoming = False
        self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            self._show_upcoming = data.get("show_upcoming_in_rail") is True
            for item in data.get("tasks", [])[:MAX_TASKS]:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    self._tasks.append(item)
        except (FileNotFoundError, ValueError, TypeError):
            pass

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "show_upcoming_in_rail": self._show_upcoming,
            "tasks": self._tasks,
        }, indent=2), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)

    def register_action(self, addon_id: str, action_name: str, label: str,
                        fields: list[dict], handler, *, prepare=None, addon_name=None):
        action_id = f"{addon_id}.{action_name}"
        if not ACTION_ID.fullmatch(action_id) or not callable(handler):
            raise ScheduledTaskError("A scheduled action needs a valid ID and handler.")
        if not isinstance(fields, list) or len(fields) > 8:
            raise ScheduledTaskError("A scheduled action may define at most eight fields.")
        safe_fields = []
        for field in fields:
            if not isinstance(field, dict) or not re.fullmatch(
                r"[a-z][a-z0-9_]{0,39}", str(field.get("name") or "")
            ):
                raise ScheduledTaskError("A scheduled action field has an invalid name.")
            kind = field.get("type", "text")
            if kind not in {"text", "textarea", "select"}:
                raise ScheduledTaskError("Unsupported scheduled action field type.")
            options = field.get("options", [])
            if kind == "select" and (not isinstance(options, list) or len(options) > 30):
                raise ScheduledTaskError("A select field needs a bounded option list.")
            safe_fields.append({
                "name": field["name"], "label": str(field.get("label") or field["name"])[:80],
                "type": kind, "required": field.get("required") is not False,
                "max_length": max(1, min(int(field.get("max_length", 500)), 1000)),
                "options": [str(option)[:100] for option in options] if kind == "select" else [],
            })
        with self._lock:
            if action_id in self._actions:
                raise ScheduledTaskError("That scheduled action is already registered.")
            self._actions[action_id] = {
                "id": action_id, "addon_id": addon_id, "label": str(label)[:80],
                "addon_name": str(addon_name or addon_id.replace("-", " ").title())[:80],
                "fields": safe_fields, "handler": handler, "prepare": prepare,
            }
        return lambda: self.unregister_action(action_id)

    def unregister_action(self, action_id: str):
        with self._lock:
            self._actions.pop(action_id, None)

    def public_state(self) -> dict:
        with self._lock:
            tasks = [dict(task) for task in self._tasks]
            actions = [
                {key: action[key] for key in ("id", "addon_id", "addon_name", "label", "fields")}
                for action in self._actions.values()
            ]
            return {
                "tasks": sorted(tasks, key=lambda task: task.get("next_run_at") or "~"),
                "actions": actions,
                "show_upcoming_in_rail": self._show_upcoming,
            }

    def set_show_upcoming(self, value: object) -> dict:
        if not isinstance(value, bool):
            raise ScheduledTaskError("Choose whether upcoming tasks appear in the rail.")
        with self._lock:
            self._show_upcoming = value
            self._save()
        return self.public_state()

    @staticmethod
    def _due_at(task: dict, after: dt.datetime) -> dt.datetime | None:
        zone = ZoneInfo(task["timezone"])
        anchor = dt.date.fromisoformat(task["start_date"])
        hour, minute = (int(part) for part in task["time"].split(":"))
        recurrence = task["recurrence"]
        local_after = after.astimezone(zone)
        if recurrence == "once":
            dates = [anchor]
        elif recurrence == "daily":
            dates = [max(anchor, local_after.date() - dt.timedelta(days=1)) + dt.timedelta(days=i)
                     for i in range(4)]
        elif recurrence == "weekly":
            elapsed = max(0, (local_after.date() - anchor).days // 7 - 1)
            dates = [anchor + dt.timedelta(weeks=elapsed + i) for i in range(4)]
        elif recurrence == "selected_days":
            start = max(anchor, local_after.date() - dt.timedelta(days=1))
            chosen = set(task.get("selected_days") or [])
            dates = [date for i in range(9) if (date := start + dt.timedelta(days=i)).isoweekday() % 7 in chosen]
        else:
            months = max(0, (local_after.year - anchor.year) * 12 + local_after.month - anchor.month - 1)
            dates = []
            for step in range(months, months + 4):
                year = anchor.year + (anchor.month - 1 + step) // 12
                month = (anchor.month - 1 + step) % 12 + 1
                dates.append(dt.date(year, month, min(anchor.day, calendar.monthrange(year, month)[1])))
        for date in dates:
            candidate = dt.datetime(date.year, date.month, date.day, hour, minute, tzinfo=zone)
            # A daylight-saving gap has no corresponding local wall time.
            if candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != candidate.replace(tzinfo=None):
                continue
            instant = candidate.astimezone(UTC)
            if instant > after:
                return instant
        return None

    def _validated(self, payload: object, previous: dict | None = None) -> dict:
        if not isinstance(payload, dict):
            raise ScheduledTaskError("Expected a task configuration.")
        title = str(payload.get("title") or "").strip()[:80]
        if not title:
            raise ScheduledTaskError("Give the task a title.")
        incoming_steps = payload.get("steps")
        if incoming_steps is None:
            incoming_steps = [{"action_id": payload.get("action_id"),
                               "arguments": payload.get("arguments"), "summary": title}]
        if not isinstance(incoming_steps, list) or not 1 <= len(incoming_steps) <= MAX_STEPS:
            raise ScheduledTaskError("Add between one and twelve task steps.")
        steps = [self._validated_step(item) for item in incoming_steps]
        date = str(payload.get("start_date") or "")
        time = str(payload.get("time") or "")
        timezone = str(payload.get("timezone") or "")
        recurrence = str(payload.get("recurrence") or "once")
        try:
            dt.date.fromisoformat(date)
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
                raise ValueError
            ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ScheduledTaskError("Choose a valid date, time, and time zone.") from exc
        if recurrence not in RECURRENCES:
            raise ScheduledTaskError("Choose a supported repeat setting.")
        selected_days = payload.get("selected_days", [])
        if recurrence == "selected_days":
            if (not isinstance(selected_days, list) or not selected_days
                    or any(type(day) is not int or not 0 <= day <= 6 for day in selected_days)):
                raise ScheduledTaskError("Choose at least one day of the week.")
            selected_days = sorted(set(selected_days))
        else:
            selected_days = []
        enabled = payload.get("enabled") is not False
        task = {
            "id": previous["id"] if previous else uuid.uuid4().hex,
            "title": title, "steps": steps,
            "start_date": date, "time": time, "timezone": timezone,
            "recurrence": recurrence, "selected_days": selected_days, "enabled": enabled,
            "last_run_at": previous.get("last_run_at") if previous else None,
            "last_status": previous.get("last_status", "") if previous else "",
            "last_due_at": previous.get("last_due_at") if previous else None,
        }
        old_schedule = (
            previous and all(previous.get(key) == task.get(key) for key in
                             ("start_date", "time", "timezone", "recurrence", "selected_days"))
        )
        if old_schedule:
            task["next_run_at"] = previous.get("next_run_at")
        else:
            now = self._clock()
            task["last_due_at"] = None
            task["next_run_at"] = (due.isoformat() if (due := self._due_at(
                task, now - dt.timedelta(seconds=1)
            )) else None)
            if task["next_run_at"] is None:
                raise ScheduledTaskError("Choose a future date and time.")
        return task

    def _validated_step(self, item: object) -> dict:
        if not isinstance(item, dict):
            raise ScheduledTaskError("Each task step needs an add-on action.")
        action_id = str(item.get("action_id") or "")
        action = self._actions.get(action_id)
        if action is None:
            raise ScheduledTaskError(f"The task action {action_id or '(missing)'} is unavailable.")
        arguments = item.get("arguments")
        if not isinstance(arguments, dict):
            raise ScheduledTaskError("Review each task step before saving.")
        safe_args = {}
        for field in action["fields"]:
            value = str(arguments.get(field["name"]) or "").strip()
            if field["required"] and not value:
                raise ScheduledTaskError(f"Set {field['label']}.")
            if len(value) > field["max_length"]:
                raise ScheduledTaskError(f"{field['label']} is too long.")
            if field["type"] == "select" and value and value not in field["options"]:
                raise ScheduledTaskError(f"Choose a valid {field['label']}.")
            safe_args[field["name"]] = value
        summary = str(item.get("summary") or action["label"]).strip()[:240]
        return {"action_id": action_id, "arguments": safe_args, "summary": summary,
                "instruction": str(item.get("instruction") or "").strip()[:500]}

    def preview_steps(self, requested: object) -> list[dict]:
        if not isinstance(requested, list) or not 1 <= len(requested) <= MAX_STEPS:
            raise ScheduledTaskError("Add between one and twelve task steps.")
        prepared = []
        for item in requested:
            if not isinstance(item, dict):
                raise ScheduledTaskError("Choose an add-on for each step.")
            action_id = str(item.get("action_id") or "")
            with self._lock:
                action = self._actions.get(action_id)
            if action is None:
                raise ScheduledTaskError("That add-on task action is unavailable.")
            instruction = str(item.get("instruction") or "").strip()
            if not instruction or len(instruction) > 500:
                raise ScheduledTaskError(f"Write a short instruction for {action['addon_name']}.")
            if action["prepare"] is None:
                fields = action["fields"]
                if len(fields) != 1:
                    raise ScheduledTaskError(f"{action['label']} needs a task editor update.")
                drafted = [{"arguments": {fields[0]["name"]: instruction}, "summary": instruction}]
            else:
                drafted = action["prepare"](instruction)
            if not isinstance(drafted, list) or not drafted:
                raise ScheduledTaskError(f"{action['addon_name']} could not prepare that instruction.")
            for draft in drafted:
                if not isinstance(draft, dict):
                    raise ScheduledTaskError(f"{action['addon_name']} returned an invalid action.")
                step = self._validated_step({"action_id": action_id,
                    "arguments": draft.get("arguments"), "summary": draft.get("summary"),
                    "instruction": instruction})
                if isinstance(draft.get("options"), list):
                    step["options"] = draft["options"][:10]
                prepared.append(step)
                if len(prepared) > MAX_STEPS:
                    raise ScheduledTaskError("A task may run at most twelve actions.")
        return prepared

    def preview_schedule(self, payload: dict) -> list[str]:
        with self._lock:
            task = self._validated(payload)
        upcoming = []
        after = self._clock() - dt.timedelta(seconds=1)
        for _ in range(3):
            due = self._due_at(task, after)
            if due is None:
                break
            upcoming.append(due.isoformat())
            after = due
        return upcoming

    def save_task(self, payload: object, task_id: str | None = None) -> dict:
        with self._lock:
            previous = next((task for task in self._tasks if task["id"] == task_id), None)
            if task_id and previous is None:
                raise ScheduledTaskError("Task not found.")
            if not previous and len(self._tasks) >= MAX_TASKS:
                raise ScheduledTaskError("The task list is full.")
            task = self._validated(payload, previous)
            if previous:
                self._tasks[self._tasks.index(previous)] = task
            else:
                self._tasks.append(task)
            self._save()
            if task["enabled"] and task["next_run_at"]:
                self._start()
            return dict(task)

    def delete_task(self, task_id: str) -> None:
        with self._lock:
            before = len(self._tasks)
            self._tasks = [task for task in self._tasks if task["id"] != task_id]
            if len(self._tasks) == before:
                raise ScheduledTaskError("Task not found.")
            self._save()

    def _start(self):
        if self._worker is None and not self._stop.is_set():
            self._worker = threading.Thread(target=self._run, name="petey-scheduled-tasks", daemon=True)
            self._worker.start()

    def start(self):
        with self._lock:
            if any(task.get("enabled") and task.get("next_run_at") for task in self._tasks):
                self._start()

    def _run(self):
        while not self._stop.wait(self._poll_seconds):
            self.run_due()

    def run_due(self):
        now = self._clock()
        due_tasks = []
        changed = False
        with self._lock:
            for task in self._tasks:
                if not task.get("enabled") or not task.get("next_run_at"):
                    continue
                due = dt.datetime.fromisoformat(task["next_run_at"])
                if due > now:
                    continue
                changed = True
                task["last_due_at"] = due.isoformat()
                following = self._due_at(task, now) if task["recurrence"] != "once" else None
                task["next_run_at"] = following.isoformat() if following else None
                if now - due > dt.timedelta(minutes=5):
                    task["last_status"] = "Missed while PETEY was unavailable"
                    continue
                task["last_status"] = "Running"
                due_tasks.append((task["id"], dict(task)))
            if changed:
                self._save()
        for task_id, snapshot in due_tasks:
            self._execute(task_id, snapshot)

    def run_now(self, task_id: str) -> dict:
        with self._lock:
            task = next((item for item in self._tasks if item["id"] == task_id), None)
            if task is None:
                raise ScheduledTaskError("Task not found.")
            snapshot = dict(task)
        return self._execute(task_id, snapshot)

    def _execute(self, task_id: str, task: dict) -> dict:
        steps = task.get("steps") or [{"action_id": task.get("action_id"),
                                        "arguments": task.get("arguments"),
                                        "summary": task.get("title", "Action")}]
        completed = []
        metadata = {"scheduled_task_id": task_id, "scheduled_task_title": task["title"]}
        try:
            for index, step in enumerate(steps, 1):
                action = self._actions.get(step["action_id"])
                if action is None:
                    raise ScheduledTaskError(f"Step {index}: add-on action is unavailable.")
                result = action["handler"](dict(step["arguments"]))
                if not isinstance(result, dict) or not str(result.get("message") or "").strip():
                    raise ScheduledTaskError(f"Step {index}: add-on returned no result.")
                completed.append(f"{index}. {str(result['message'])[:500]}")
                metadata.update({
                    key: value for key, value in (result.get("metadata") or {}).items()
                    if key in {"chat_image_url", "chat_image_alt", "chat_image_caption", "chat_image_link"}
                    and isinstance(value, str)
                })
        except Exception as exc:
            status = f"Failed after {len(completed)} of {len(steps)} steps: {str(exc)[:180]}"
            try:
                self._announce(
                    f"Scheduled task '{task['title']}' stopped after {len(completed)} of {len(steps)} steps. "
                    f"Completed: {'; '.join(completed) or 'none'}. Failure: {str(exc)[:180]}. "
                    "Report partial completion accurately.", metadata=metadata,
                )
            except Exception:
                pass
        else:
            try:
                self._announce(
                    f"Scheduled task '{task['title']}' completed: {'; '.join(completed)[:3000]}. "
                    "Report only this result; do not claim any other action was completed.",
                    metadata=metadata,
                )
                status = "Action ran; PETEY announcement queued"
            except Exception as exc:
                status = f"Action ran; PETEY announcement failed: {str(exc)[:150]}"
        with self._lock:
            current = next((item for item in self._tasks if item["id"] == task_id), None)
            if current:
                current["last_run_at"] = self._clock().isoformat()
                current["last_status"] = status
                self._save()
        return {"status": status}

    def close(self):
        self._stop.set()
        if self._worker and threading.current_thread() is not self._worker:
            self._worker.join(timeout=3)
