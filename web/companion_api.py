"""Narrow, bearer-authenticated native companion boundary. No Android dependencies."""
from __future__ import annotations

import hashlib
import io
import wave
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

from flask import g, jsonify, request

PREFIX = "/api/companion/v1"


class CompanionTokens:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    def _read(self):
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}

    def _write(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump(records, output)
        os.replace(temporary, self.path)

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def issue(self, root):
        token = secrets.token_urlsafe(32)
        with self.lock:
            records = self._read()
            records = {k: v for k, v in records.items() if v['expires'] > time.time() and v['root'] == self.digest(root)}
            if len(records) >= 32:
                raise ValueError('Device limit reached; rotate mobile access to revoke old devices.')
            records[self.digest(token)] = {'root': self.digest(root), 'expires': time.time() + 365 * 86400}
            self._write(records)
        return token

    def valid(self, token, root):
        with self.lock:
            record = self._read().get(self.digest(token), {})
        return record.get('expires', 0) > time.time() and hmac.compare_digest(record.get('root', ''), self.digest(root))

    def revoke(self, token):
        with self.lock:
            records = self._read()
            records.pop(self.digest(token), None)
            self._write(records)


def register_companion_api(app):
    tokens = CompanionTokens(Path(app.config['PETEY_STATE'].data_dir) / 'companion-devices.json')
    jobs = {}
    lock = threading.Lock()

    @app.before_request
    def companion_auth():
        if not request.path.startswith(PREFIX + '/'):
            return None
        request.max_content_length = 1024 * 1024
        root = app.config.get('PETEY_COMPANION_PAIRING_SECRET', '')
        if not root:
            return jsonify(error='Launch PETEY with authenticated remote access first.'), 503
        if request.content_length and request.content_length > 1024 * 1024:
            return jsonify(error='Companion request exceeds 1 MiB.'), 413
        authorization = request.headers.get('Authorization', '')
        supplied = authorization[7:] if authorization.startswith('Bearer ') else ''
        if request.path == PREFIX + '/pair':
            valid = bool(supplied) and hmac.compare_digest(supplied.encode(), root.encode())
        else:
            valid = bool(supplied) and tokens.valid(supplied, root)
        if not valid:
            return jsonify(error='Pairing required.'), 401
        g.companion_token = supplied

    @app.after_request
    def companion_no_cache(response):
        if request.path.startswith(PREFIX + '/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post(PREFIX + '/pair')
    def companion_pair():
        try:
            return jsonify(token=tokens.issue(app.config['PETEY_COMPANION_PAIRING_SECRET']), version=1)
        except ValueError as exc:
            return jsonify(error=str(exc)), 409

    @app.route(PREFIX + '/device', methods=['GET', 'DELETE'])
    def companion_device():
        if request.method == 'DELETE':
            tokens.revoke(g.companion_token)
        return jsonify(version=1, status='revoked' if request.method == 'DELETE' else 'connected')

    @app.post(PREFIX + '/transcribe')
    def companion_transcribe():
        uploaded = request.files.get('audio')
        if not uploaded:
            return jsonify(error='Provide a WAV request.'), 400
        audio = uploaded.read(1024 * 1024 + 1)
        try:
            with wave.open(io.BytesIO(audio)) as recording:
                if (recording.getnchannels(), recording.getsampwidth(), recording.getframerate(), recording.getcomptype()) != (1, 2, 16000, 'NONE'):
                    raise ValueError
                if not 1 <= recording.getnframes() <= 25 * 16000:
                    raise ValueError
                if len(recording.readframes(recording.getnframes())) != recording.getnframes() * 2:
                    raise ValueError
        except (wave.Error, EOFError, ValueError):
            return jsonify(error='Use mono 16 kHz PCM16 WAV, at most 25 seconds.'), 400
        with app.test_request_context('/api/desktop/voice-input/transcribe', method='POST', data={'audio': (io.BytesIO(audio), 'request.wav', 'audio/wav')}):
            return app.view_functions['desktop_voice_input_transcribe']()

    @app.post(PREFIX + '/chat')
    def companion_chat():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify(error='Expected a JSON object.'), 400
        message = payload.get('message', '')
        if not isinstance(message, str) or not message.strip() or len(message) > 16000:
            return jsonify(error='Provide a message of 1–16000 characters.'), 400
        # Reuse the established conversation/tool policy with a fixed mobile surface.
        with app.test_request_context('/api/desktop/chat', method='POST', data={'message': message, 'surface': 'mobile_petey'}):
            return app.view_functions['desktop_chat']()

    @app.post(PREFIX + '/speech')
    def companion_speech():
        if not isinstance(request.get_json(silent=True), dict):
            return jsonify(error='Expected a JSON object.'), 400
        response = app.make_response(app.view_functions['desktop_chat_speech']())
        if response.status_code == 202:
            job = response.get_json()['job']
            with lock:
                now = time.monotonic()
                for key, (_, expiry) in list(jobs.items()):
                    if expiry < now:
                        jobs.pop(key)
                jobs[job['id']] = (tokens.digest(g.companion_token), now + 600)
        return response

    def owns_job(job_id):
        with lock:
            owner, expiry = jobs.get(job_id, ('', 0))
        return expiry > time.monotonic() and hmac.compare_digest(owner, tokens.digest(g.companion_token))

    @app.get(PREFIX + '/speech/<job_id>')
    def companion_speech_status(job_id):
        if not owns_job(job_id):
            return jsonify(error='Speech job not found.'), 404
        return app.view_functions['desktop_media_job'](job_id)

    @app.get(PREFIX + '/speech/<job_id>/file')
    def companion_speech_file(job_id):
        if not owns_job(job_id):
            return jsonify(error='Speech job not found.'), 404
        return app.view_functions['desktop_media_job_file'](job_id)
