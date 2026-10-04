"""Direct bridge policy, real stdio, Streamable HTTP, and settings routes."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

from petey.general_mcp import GeneralMCPManager, MCPHTTPClient
from petey.mcp_client import MCPError
from petey.tools.registry import ToolError, ToolRegistry
from tests.test_mcp_client import FAKE_SERVER

TOOLS = [
    {'name': 'read', 'description': 'Read something', 'inputSchema': {'type': 'object'}},
    {'name': 'write', 'inputSchema': {'type': 'object'}},
]

class FakeClient:
    def __init__(self, config):
        self.running = False
        self.calls = []
        self.result = {'content': [{'type': 'text', 'text': 'done'}]}
        self.tools = TOOLS
    def list_tools(self):
        self.running = True
        return self.tools
    def call_tool(self, name, args):
        self.running = True
        self.calls.append((name, args))
        return self.result
    def close(self):
        self.running = False

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clients = []
        def factory(config):
            client = FakeClient(config); self.clients.append(client); return client
        self.state = SimpleNamespace(data_dir=Path(self.temp.name))
        self.manager = GeneralMCPManager(self.state, factory)
        self.addCleanup(self.manager.close)
        self.key = self.manager.import_config({'mcpServers': {'notes': {
            'command': 'fake', 'args': ['secret-arg'], 'env': {'TOKEN': 'private-token'},
        }}})['servers'][0]['id']
    def enable(self):
        self.manager.test(self.key)
        self.manager.update(self.key, {'allowed_tools': ['read'], 'enabled': True, 'keywords': ['notes', 'note']})
    def test_import_is_off_no_process_and_private(self):
        self.assertEqual(self.clients, [])
        status = self.manager.public_status()['servers'][0]
        self.assertFalse(status['enabled']); self.assertEqual(status['allowed_tools'], [])
        self.assertNotIn('private-token', json.dumps(status))
        self.assertNotIn('secret-arg', json.dumps(status))
        self.assertEqual(os.stat(self.manager.path).st_mode & 0o777, 0o600)

    def test_petey_life_grants_are_removed_on_reload(self):
        self.enable()
        self.manager._servers[self.key]['surfaces']['petey_life'] = True
        self.manager._save()
        reloaded = GeneralMCPManager(self.state, FakeClient)
        self.addCleanup(reloaded.close)
        self.assertNotIn('petey_life', reloaded.public_status()['servers'][0]['surfaces'])
        self.assertEqual(reloaded.tool_specs('petey_life'), [])
        with self.assertRaisesRegex(ValueError, 'supported chat surfaces'):
            reloaded.update(self.key, {'surfaces': {'petey_life': True}})
    def test_allowlist_intent_surfaces_and_disable_stale_registry(self):
        with self.assertRaises(ValueError): self.manager.update(self.key, {'enabled': True})
        self.enable()
        registry = ToolRegistry(self.manager.tool_specs())
        self.assertEqual(registry.schemas_for('very cool'), [])
        self.assertEqual(registry.schemas_for('noteworthy'), [])
        schemas = registry.schemas_for('read my notes')
        self.assertEqual(len(schemas), 1)
        name = schemas[0]['function']['name']
        self.assertEqual(registry.execute(name, {}, 'read my notes'), self.clients[-1].result)
        self.assertEqual(self.clients[-1].calls, [('read', {})])
        self.assertEqual(self.manager.tool_specs('discord'), [])
        with self.assertRaises(ToolError): self.manager.call(self.key, 'write', {}, 'petey_desktop')
        with self.assertRaises(ToolError): self.manager.call(self.key, 'read', {}, 'discord')
        self.manager.update(self.key, {'enabled': False})
        self.assertFalse(self.clients[-1].running)
        with self.assertRaises(ToolError): registry.execute(name, {}, 'read notes')
    def test_remove_invalidates_existing_registry(self):
        self.enable(); registry = ToolRegistry(self.manager.tool_specs())
        name = registry.schemas_for('notes')[0]['function']['name']
        self.manager.remove(self.key)
        self.assertEqual(registry.schemas_for('notes'), [])
        with self.assertRaises(ToolError): registry.execute(name, {}, 'notes')
    def test_reimport_disables_and_clears_selection_and_cache(self):
        self.enable()
        status = self.manager.import_config({'mcpServers': {'notes': {'command': 'new'}}})['servers'][0]
        self.assertEqual(status['id'], self.key); self.assertFalse(status['enabled'])
        self.assertEqual(status['tools'], []); self.assertEqual(status['allowed_tools'], [])
        self.assertFalse(self.clients[-1].running)
        self.assertEqual(GeneralMCPManager(self.state).public_status()['servers'][0]['tools'], [])
    def test_restart_uses_saved_discovery_without_spawning_and_namespace_bounded(self):
        self.manager.test(self.key)
        long_name = 'x' * 100
        self.clients[-1].tools = [{'name': long_name, 'inputSchema': {'type': 'object'}}]
        self.manager.test(self.key)
        self.manager.update(self.key, {'allowed_tools': [long_name], 'enabled': True})
        fresh = GeneralMCPManager(self.state, lambda config: self.fail('Must not connect for schemas'))
        self.addCleanup(fresh.close)
        spec = fresh.tool_specs()[0]
        self.assertLessEqual(len(spec.name), 64)
        self.assertEqual(len(fresh.public_status()['servers'][0]['tools']), 1)
    def test_tool_failure_is_not_reported_as_success_and_result_is_bounded(self):
        self.enable(); client = self.clients[-1]
        client.result = {'isError': True, 'content': [{'text': 'SECRET'}]}
        with self.assertRaises(ToolError) as caught: self.manager.call(self.key, 'read', {}, 'petey_desktop')
        self.assertNotIn('SECRET', str(caught.exception))
        client.result = {'content': [{'text': 'x' * 100000}]}
        result = self.manager.call(self.key, 'read', {}, 'petey_desktop')
        self.assertTrue(result['truncated']); self.assertEqual(len(result['result']), 64000)
    def test_server_failure_sanitized_and_no_retry(self):
        self.enable(); client = self.clients[-1]
        client.call_tool = MagicMock(side_effect=RuntimeError('SECRET'))
        with self.assertRaises(ToolError) as caught: self.manager.call(self.key, 'read', {}, 'petey_desktop')
        self.assertNotIn('SECRET', str(caught.exception)); self.assertEqual(client.call_tool.call_count, 1)
        self.assertFalse(client.running)
    def test_batch_import_validation_is_atomic(self):
        with self.assertRaises(ValueError): self.manager.import_config({'mcpServers': {
            'valid': {'command': 'valid'}, 'invalid': {'url': 'file:///etc/passwd'}}})
        self.assertEqual(len(self.manager.public_status()['servers']), 1)
        with self.assertRaises(ValueError): self.manager.import_config({'mcpServers': {'legacy': {'url': 'https://example.com/sse', 'type': 'sse'}}})
        with self.assertRaises(ValueError): self.manager.import_config({'mcpServers': {'bad': {'command': 'bad\0command'}}})
    def test_credential_validation_and_existing_grants_cleared(self):
        key = self.manager.import_config({'mcpServers': {'remote': {'url': 'https://example.com/mcp'}}})['servers'][-1]['id']
        for credential in ({'type': 'bearer', 'value': ''}, {'type': 'api_key', 'value': 'bad\nvalue'}, {'type': 'other', 'value': 'secret'}):
            with self.assertRaises(ValueError): self.manager.update(key, {'credential': credential})
        with self.assertRaises(ValueError): self.manager.update(self.key, {'credential': {'type': 'bearer', 'value': 'secret'}})
        self.manager.test(key)
        self.manager.update(key, {'enabled': True, 'allowed_tools': ['read']})
        status = self.manager.update(key, {'credential': {'type': 'api_key', 'value': 'api-secret'}})
        server = status['servers'][-1]
        self.assertTrue(server['has_authentication']); self.assertFalse(server['enabled'])
        self.assertEqual(server['authentication_type'], 'api_key'); self.assertEqual(server['allowed_tools'], [])
        self.assertNotIn('api-secret', json.dumps(status))

    def test_http_credentials_hidden_in_status(self):
        status = self.manager.import_config({'mcpServers': {'remote': {
            'url': 'https://example.com/mcp?token=PRIVATE', 'headers': {'Authorization': 'Bearer SECRET'}}}})
        self.assertNotIn('PRIVATE', json.dumps(status)); self.assertNotIn('SECRET', json.dumps(status))
    def test_actual_stdio_process_and_cleanup(self):
        server = self.state.data_dir / 'server.py'; server.write_text(FAKE_SERVER.replace('2025-06-18', '2024-11-05'))
        real = GeneralMCPManager(self.state); self.addCleanup(real.close)
        key = real.import_config({'mcpServers': {'local': {'command': sys.executable, 'args': [str(server)], 'cwd': str(self.state.data_dir)}}})['servers'][-1]['id']
        real.test(key); real.update(key, {'allowed_tools': ['read_text_file'], 'enabled': True})
        client = real._clients[key]; process = client._process
        result = real.call(key, 'read_text_file', {'path': 'test.txt'}, 'petey_desktop')
        self.assertEqual(result['content'][0]['text'], 'hello from test.txt')
        real.update(key, {'enabled': False}); self.assertIsNotNone(process.poll())

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.messages, self.mode, self.deletes = [], 'json', 0
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                message = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.messages.append((message, dict(self.headers)))
                if owner.mode == 'auth' or (owner.mode == 'auth-required' and self.headers.get('Authorization') != 'Bearer test-secret'): self.send_response(401); self.end_headers(); return
                if owner.mode == 'expired': self.send_response(404); self.end_headers(); return
                if 'id' not in message: self.send_response(202); self.end_headers(); return
                method = message.get('method')
                if method == 'initialize': result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}}
                elif method == 'tools/list':
                    result = {'tools': TOOLS[1:]} if message['params'].get('cursor') else {'tools': TOOLS[:1], 'nextCursor': 'second'}
                else: result = {'content': [{'type': 'text', 'text': 'remote-done'}]}
                payload = {'jsonrpc': '2.0', 'id': message['id'], 'result': result}
                if owner.mode == 'wrong-id': payload['id'] = 999
                self.send_response(200); self.send_header('Mcp-Session-Id', 'session-123')
                if owner.mode == 'sse':
                    data = ('event: message\ndata: ' + json.dumps(payload) + '\n\n').encode()
                    self.send_header('Content-Type', 'text/event-stream')
                else:
                    data = json.dumps(payload).encode(); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
            def do_DELETE(self):
                owner.deletes += 1; self.send_response(204); self.end_headers()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True); thread.start()
        def cleanup(): self.server.shutdown(); self.server.server_close(); thread.join(2)
        self.addCleanup(cleanup)
        self.client = MCPHTTPClient(f'http://127.0.0.1:{self.server.server_port}/mcp', {'Authorization': 'Bearer test'}, timeout=2)
        self.addCleanup(self.client.close)
    def test_manager_preserves_auth_diagnostic_and_connects_after_credential_save(self):
        self.mode = 'auth-required'
        with tempfile.TemporaryDirectory() as directory:
            manager = GeneralMCPManager(SimpleNamespace(data_dir=Path(directory)))
            self.addCleanup(manager.close)
            key = manager.import_config({'mcpServers': {'remote': {'url': self.client.url}}})['servers'][0]['id']
            with self.assertRaises(MCPError) as caught:
                manager.test(key)
            self.assertIn('Authentication failed', str(caught.exception))
            self.assertIn('401/403', manager.public_status()['servers'][0]['error'])
            status = manager.update(key, {'credential': {'type': 'bearer', 'value': 'test-secret'}})
            self.assertTrue(status['servers'][0]['has_authentication'])
            self.assertNotIn('test-secret', json.dumps(status))
            self.assertEqual(status['servers'][0]['error'], '')
            status = manager.test(key)
            self.assertEqual([t['name'] for t in status['servers'][0]['tools']], ['read', 'write'])
            manager.update(key, {'allowed_tools': ['read'], 'enabled': True})
            old_client = manager._clients[key]
            status = manager.update(key, {'credential': {'type': 'clear'}})
            server = status['servers'][0]
            self.assertFalse(server['enabled']); self.assertFalse(server['has_authentication'])
            self.assertEqual(server['allowed_tools'], []); self.assertEqual(server['tools'], [])
            self.assertFalse(old_client.running)
            self.assertFalse(GeneralMCPManager(SimpleNamespace(data_dir=Path(directory))).public_status()['servers'][0]['has_authentication'])

    def test_json_handshake_pagination_call_headers_cleanup(self):
        self.assertEqual([t['name'] for t in self.client.list_tools()], ['read', 'write'])
        result = self.client.call_tool('read', {})
        self.assertEqual(result['content'][0]['text'], 'remote-done')
        methods = [m.get('method') for m, h in self.messages]
        self.assertEqual(methods, ['initialize', 'notifications/initialized', 'tools/list', 'tools/list', 'tools/call'])
        headers = self.messages[-1][1]
        self.assertEqual(headers['Mcp-Session-Id'], 'session-123')
        self.assertEqual(headers['MCP-Protocol-Version'], '2025-06-18')
        self.assertEqual(headers['Authorization'], 'Bearer test')
        self.client.close(); self.assertEqual(self.deletes, 1)
    def test_sse_responses(self):
        self.mode = 'sse'; self.assertEqual(len(self.client.list_tools()), 2)
        self.assertEqual(self.client.call_tool('read', {})['content'][0]['text'], 'remote-done')
    def test_expired_action_never_retries(self):
        self.client.start(); self.mode = 'expired'
        with self.assertRaises(MCPError): self.client.call_tool('write', {})
        self.assertEqual(sum(m.get('method') == 'tools/call' for m, _ in self.messages), 1)
        self.assertFalse(self.client.running)
    def test_auth_and_wrong_request_response(self):
        self.mode = 'auth'
        with self.assertRaises(MCPError): self.client.start()
        self.mode = 'wrong-id'
        with self.assertRaises(MCPError): self.client.start()

class RouteTests(unittest.TestCase):
    def test_settings_import_discovery_enable_dispatch_and_secret_redaction(self):
        from petey.desktop_state import DesktopState
        from web.desktop_app import create_desktop_app
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            manager = GeneralMCPManager(state, FakeClient)
            app = create_desktop_app(state=state, memory=MagicMock(), general_mcp_manager=manager,
                                     job_manager=MagicMock())
            self.addCleanup(app.config['PETEY_RUNTIME'].close)
            self.addCleanup(manager.close)
            client = app.test_client()
            html = client.get('/').get_data(as_text=True)
            self.assertIn('id="general-mcp-settings"', html); self.assertIn('/static/mcp.js?', html)
            with client.get('/static/mcp.js') as asset:
                self.assertEqual(asset.status_code, 200)
            response = client.post('/api/desktop/mcp/servers/import', json={'mcpServers': {'notes': {'command': 'fake', 'env': {'TOKEN': 'SECRET'}}}})
            self.assertEqual(response.status_code, 200); self.assertNotIn('SECRET', response.get_data(as_text=True))
            key = response.json['servers'][0]['id']
            self.assertEqual(client.put(f'/api/desktop/mcp/servers/{key}', json={'enabled': True}).status_code, 400)
            self.assertEqual(client.post(f'/api/desktop/mcp/servers/{key}/test').status_code, 200)
            response = client.put(f'/api/desktop/mcp/servers/{key}', json={'enabled': True, 'allowed_tools': ['read'], 'surfaces': {'discord': True}})
            self.assertEqual(response.status_code, 200)
            specs = app.config['PETEY_DISCORD'].addon_tools_getter().schemas_for('notes')
            self.assertTrue(any(s['function']['name'].startswith('mcp_') for s in specs))
            from petey.assistant import AssistantReply
            with patch('web.desktop_app.AssistantService') as service_type:
                service_type.return_value.respond = AsyncMock(return_value=AssistantReply('done'))
                for surface in ('petey_desktop', 'mobile_petey'):
                    reply = client.post('/api/desktop/chat', data={'message': 'read notes', 'surface': surface})
                    self.assertEqual(reply.status_code, 200)
                    registry = service_type.call_args.kwargs['tool_registry']
                    schemas = registry.schemas_for('read notes')
                    names = [s['function']['name'] for s in schemas if s['function']['name'].startswith('mcp_')]
                    self.assertEqual(len(names), 1)
                    self.assertEqual(registry.execute(names[0], {}, 'read notes')['content'][0]['text'], 'done')
            response = client.delete(f'/api/desktop/mcp/servers/{key}')
            self.assertEqual(response.json['servers'], [])
            self.assertEqual(client.post('/api/desktop/mcp/servers/import', json={'mcpServers': {'bad': {'command': 'x', 'args': 'wrong'}}}).status_code, 400)
