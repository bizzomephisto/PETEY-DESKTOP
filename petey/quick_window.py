"""Native compact PETEY window used by the desktop hotkey."""

from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import requests


def screenshot_path(output: str) -> Path | None:
    """Extract the file emitted by cosmic-screenshot."""
    for line in reversed(str(output or "").splitlines()):
        candidate = Path(line.strip())
        if candidate.is_file():
            return candidate
    return None


def run_quick_window(server_url: str, icon_path: Path, project_root: Path, position):
    """Run the XWayland Qt popup and block until the user closes it."""
    from PySide6.QtCore import QObject, Qt, Signal, QTimer
    from PySide6.QtGui import QCursor, QIcon, QKeyEvent
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QPushButton,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )

    class Events(QObject):
        chat = Signal(str, object)
        transcript = Signal(bool, str)

    class Composer(QPlainTextEdit):
        send_requested = Signal()
        talk_started = Signal()
        talk_stopped = Signal()
        close_requested = Signal()

        def __init__(self):
            super().__init__()
            self.space_talking = False

        def keyPressEvent(self, event: QKeyEvent):
            if event.key() == Qt.Key_Escape:
                self.close_requested.emit()
                return
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
                self.send_requested.emit()
                return
            if (
                event.key() == Qt.Key_Space
                and not event.isAutoRepeat()
                and not self.toPlainText()
                and event.modifiers() == Qt.NoModifier
            ):
                self.space_talking = True
                self.talk_started.emit()
                return
            super().keyPressEvent(event)

        def keyReleaseEvent(self, event: QKeyEvent):
            if event.key() == Qt.Key_Space and self.space_talking and not event.isAutoRepeat():
                self.space_talking = False
                self.talk_stopped.emit()
                return
            super().keyReleaseEvent(event)

    class QuickWindow(QDialog):
        def __init__(self):
            super().__init__()
            self.events = Events()
            self.events.chat.connect(self.on_chat_event)
            self.events.transcript.connect(self.on_transcript)
            self.attachment: Path | None = None
            self.chat_items = []
            self.reply_index = None
            self.reply_text = ""
            self.busy = False
            self.recorder = None
            self.recording_path: Path | None = None
            self.drag_offset = None
            self.setWindowTitle("Quick PETEY")
            self.setWindowIcon(QIcon(str(icon_path)))
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setFixedSize(430, 390)
            self.build_ui()

        def build_ui(self):
            shell = QWidget(self)
            shell.setObjectName("shell")
            shell.setGeometry(self.rect())
            root = QVBoxLayout(shell)
            root.setContentsMargins(11, 9, 11, 10)
            root.setSpacing(8)

            header = QHBoxLayout()
            avatar = QLabel()
            avatar.setPixmap(QIcon(str(icon_path)).pixmap(32, 32))
            title = QLabel("<b>PETEY</b><br><span style='color:#9aa5b9;font-size:10px'>Quick companion</span>")
            self.status = QLabel("Ready")
            self.status.setObjectName("status")
            full = self.button("↗", "Open full PETEY", self.open_full_petey)
            close = self.button("×", "Close (Esc)", self.close)
            header.addWidget(avatar)
            header.addWidget(title)
            header.addStretch()
            header.addWidget(self.status)
            header.addWidget(full)
            header.addWidget(close)
            root.addLayout(header)

            self.messages = QTextBrowser()
            self.messages.setObjectName("messages")
            self.messages.setOpenExternalLinks(True)
            self.messages.setHtml("<p class='hint'>Ask anything, attach a screenshot, or hold Space to talk.</p>")
            root.addWidget(self.messages, 1)

            self.attachment_label = QLabel()
            self.attachment_label.setObjectName("attachment")
            self.attachment_label.hide()
            root.addWidget(self.attachment_label)

            tools = QHBoxLayout()
            tools.setSpacing(5)
            tools.addWidget(self.button("▣  Screen", "Attach all screens", lambda: self.capture("screen")))
            tools.addWidget(self.button("▢  Window", "Choose a window to attach", lambda: self.capture("window")))
            tools.addWidget(self.button("＋  File", "Attach a file", self.choose_file))
            tools.addStretch()
            self.mic = self.button("●  Talk", "Hold to talk")
            self.mic.pressed.connect(self.start_recording)
            self.mic.released.connect(self.stop_recording)
            tools.addWidget(self.mic)
            root.addLayout(tools)

            row = QHBoxLayout()
            self.composer = Composer()
            self.composer.setPlaceholderText("Message PETEY…")
            self.composer.setFixedHeight(58)
            self.composer.send_requested.connect(self.send_message)
            self.composer.talk_started.connect(self.start_recording)
            self.composer.talk_stopped.connect(self.stop_recording)
            self.composer.close_requested.connect(self.close)
            self.send = self.button("➤", "Send", self.send_message)
            self.send.setObjectName("send")
            self.send.setFixedSize(40, 40)
            row.addWidget(self.composer, 1)
            row.addWidget(self.send)
            root.addLayout(row)

            self.setStyleSheet("""
                QWidget#shell { background: #121722; border: 1px solid #786cf0; border-radius: 17px; color: #f4f6fb; }
                QLabel { color: #f4f6fb; border: 0; }
                QLabel#status { color: #9aa5b9; font-size: 10px; }
                QTextBrowser#messages { background: #0d1119; border: 1px solid #293142; border-radius: 11px; padding: 7px; color: #eef1f7; }
                QTextBrowser#messages .hint { color: #9aa5b9; text-align: center; }
                QLabel#attachment { color: #63d7c4; background: #17302f; border-radius: 7px; padding: 4px 8px; }
                QPushButton { background: #202737; color: #b6bfd0; border: 1px solid #313a4e; border-radius: 8px; padding: 5px 8px; }
                QPushButton:hover { color: white; border-color: #786cf0; }
                QPushButton#send { background: #786cf0; color: white; font-size: 17px; border: 0; }
                QPlainTextEdit { background: #0d1119; color: #f4f6fb; border: 1px solid #343d51; border-radius: 10px; padding: 7px; selection-background-color: #786cf0; }
                QPlainTextEdit:focus { border-color: #9187ff; }
            """)

        def button(self, text, tooltip, callback=None):
            button = QPushButton(text)
            button.setToolTip(tooltip)
            if callback is not None:
                button.clicked.connect(callback)
            return button

        def show_at_cursor(self):
            cursor = QCursor.pos()
            screen = QApplication.screenAt(cursor) or QApplication.primaryScreen()
            geometry = screen.availableGeometry()
            x, y = position(
                cursor.x(), cursor.y(), geometry.x(), geometry.y(),
                geometry.width(), geometry.height(), self.width(), self.height(),
            )
            self.move(int(x), int(y))
            self.show()
            self.raise_()
            self.activateWindow()
            QTimer.singleShot(60, self.composer.setFocus)

        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton and event.position().y() < 52:
                self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event):
            if self.drag_offset is not None and event.buttons() & Qt.LeftButton:
                self.move(event.globalPosition().toPoint() - self.drag_offset)
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            self.drag_offset = None
            super().mouseReleaseEvent(event)

        def keyPressEvent(self, event):
            if event.key() == Qt.Key_Escape:
                self.close()
                return
            super().keyPressEvent(event)

        def open_full_petey(self):
            subprocess.Popen([sys.executable, str(project_root / "run_desktop.py")], cwd=str(project_root))
            self.close()

        def set_attachment(self, path: Path | None):
            self.attachment = path
            if path:
                self.attachment_label.setText(f"📎  {path.name}")
                self.attachment_label.show()
            else:
                self.attachment_label.hide()
            self.composer.setFocus()

        def choose_file(self):
            selected, _ = QFileDialog.getOpenFileName(self, "Attach a file")
            if selected:
                self.set_attachment(Path(selected))

        def capture(self, target):
            if shutil.which("cosmic-screenshot") is None:
                self.status.setText("COSMIC Screenshot is unavailable")
                return
            self.hide()
            QApplication.processEvents()
            command = ["cosmic-screenshot", "--notify=false", "--modal=false"]
            command.append("--interactive=false" if target == "screen" else "--interactive=true")
            try:
                result = subprocess.run(command, check=True, capture_output=True, text=True)
                path = screenshot_path(result.stdout)
                if path:
                    self.set_attachment(path)
                    self.status.setText("Screenshot attached")
                else:
                    self.status.setText("Capture cancelled")
            except subprocess.CalledProcessError:
                self.status.setText("Capture cancelled")
            finally:
                self.show_at_cursor()

        def append_bubble(self, who, text, color):
            self.chat_items.append([who, text, color, False])
            self.render_messages()
            return len(self.chat_items) - 1

        def render_messages(self):
            bubbles = []
            for who, text, color, error in self.chat_items:
                safe = html.escape(text).replace("\n", "<br>") or "…"
                text_color = "#ffaaa5" if error else "#eef1f7"
                bubbles.append(
                    f"<div style='margin:5px 0;padding:7px 9px;border-radius:9px;background:{color};color:{text_color}'>"
                    f"<b>{html.escape(who)}</b><br>{safe}</div>"
                )
            self.messages.setHtml("".join(bubbles))
            scrollbar = self.messages.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        def send_message(self):
            text = self.composer.toPlainText().strip()
            if self.busy or (not text and not self.attachment):
                return
            attachment = self.attachment
            self.busy = True
            self.send.setEnabled(False)
            self.composer.clear()
            self.set_attachment(None)
            label = text or f"Attached {attachment.name}"
            if attachment:
                label += f"\n📎 {attachment.name}"
            self.append_bubble("You", label, "#29264a")
            self.reply_text = ""
            self.reply_index = self.append_bubble("PETEY", "", "#202737")
            self.status.setText("Thinking…")
            threading.Thread(
                target=self.chat_worker, args=(text, attachment), daemon=True,
                name="petey-quick-chat",
            ).start()

        def chat_worker(self, text, attachment):
            opened = None
            try:
                data = {"message": text, "stream": "true"}
                files = None
                if attachment:
                    opened = attachment.open("rb")
                    files = {"attachment": (attachment.name, opened)}
                with requests.post(
                    f"{server_url}/api/desktop/chat", data=data, files=files,
                    stream=True, timeout=(10, 700),
                ) as response:
                    if not response.ok:
                        try:
                            detail = response.json().get("error")
                        except ValueError:
                            detail = None
                        raise RuntimeError(detail or f"PETEY could not reply ({response.status_code}).")
                    for line in response.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        event = json.loads(line)
                        self.events.chat.emit(str(event.get("type") or ""), event)
            except Exception as exc:
                self.events.chat.emit("error", {"error": str(exc)})
            finally:
                if opened is not None:
                    opened.close()

        def on_chat_event(self, kind, event):
            if kind == "delta":
                self.reply_text += str(event.get("text") or "")
                self.replace_reply(self.reply_text)
            elif kind == "done":
                self.reply_text = str(event.get("text") or self.reply_text)
                self.replace_reply(self.reply_text)
                self.finish_busy("Ready")
            elif kind == "status":
                self.status.setText(str(event.get("text") or "Thinking…"))
            elif kind == "error":
                self.replace_reply(str(event.get("error") or "PETEY could not reply."), error=True)
                self.finish_busy("Reply failed")

        def replace_reply(self, text, error=False):
            if self.reply_index is not None:
                self.chat_items[self.reply_index][1] = text
                self.chat_items[self.reply_index][3] = error
                self.render_messages()

        def finish_busy(self, label):
            self.busy = False
            self.send.setEnabled(True)
            self.status.setText(label)
            self.composer.setFocus()

        def start_recording(self):
            if self.recorder is not None or self.busy:
                return
            if shutil.which("pw-record") is None:
                self.status.setText("PipeWire recorder is unavailable")
                return
            descriptor, filename = tempfile.mkstemp(prefix="petey-quick-", suffix=".wav")
            os.close(descriptor)
            self.recording_path = Path(filename)
            try:
                self.recorder = subprocess.Popen(
                    ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", filename],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self.mic.setStyleSheet("color:#ff7b72;border-color:#ff7b72")
                self.status.setText("Listening… release to send")
            except OSError as exc:
                self.recorder = None
                self.status.setText(f"Microphone: {exc}")

        def stop_recording(self):
            if self.recorder is None:
                return
            recorder = self.recorder
            path = self.recording_path
            self.recorder = None
            self.recording_path = None
            recorder.terminate()
            try:
                recorder.wait(timeout=3)
            except subprocess.TimeoutExpired:
                recorder.kill()
            self.mic.setStyleSheet("")
            if path is None or not path.is_file() or path.stat().st_size < 128:
                if path:
                    path.unlink(missing_ok=True)
                self.status.setText("No speech detected")
                return
            self.busy = True
            self.send.setEnabled(False)
            self.status.setText("Transcribing…")
            threading.Thread(target=self.transcribe_worker, args=(path,), daemon=True).start()

        def transcribe_worker(self, path):
            try:
                with path.open("rb") as audio:
                    response = requests.post(
                        f"{server_url}/api/desktop/voice-input/transcribe",
                        files={"audio": (path.name, audio, "audio/wav")}, timeout=180,
                    )
                payload = response.json()
                if not response.ok:
                    raise RuntimeError(payload.get("error") or "Transcription failed.")
                self.events.transcript.emit(True, str(payload.get("transcript") or "").strip())
            except Exception as exc:
                self.events.transcript.emit(False, str(exc))
            finally:
                path.unlink(missing_ok=True)

        def on_transcript(self, ok, text):
            self.busy = False
            self.send.setEnabled(True)
            if ok and text:
                self.composer.setPlainText(text)
                self.send_message()
            else:
                self.status.setText(f"Microphone: {text}" if text else "No speech detected")
                self.composer.setFocus()

        def closeEvent(self, event):
            if self.recorder is not None:
                self.recorder.terminate()
            if self.recording_path:
                self.recording_path.unlink(missing_ok=True)
            super().closeEvent(event)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("petey-desktop")
    app.setDesktopFileName("petey-desktop")
    app.setWindowIcon(QIcon(str(icon_path)))
    window = QuickWindow()
    window.show_at_cursor()
    return app.exec()
