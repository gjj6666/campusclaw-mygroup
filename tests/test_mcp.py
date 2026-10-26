import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from apitest.mcp_support import DemoMcp, server_module
from campusclaw.db import connect, initialize
from campusclaw.mcp_client import McpClient, McpError, base_url
from campusclaw.mcp_store import McpStore
from campusclaw.skills import GUIDANCE_EXAMPLE
from campusclaw.tutor import TutorStore


class McpTests(unittest.TestCase):
    def setUp(self):
        self.remote = DemoMcp(); self.addCleanup(self.remote.close)
        self.client = McpClient(self.remote.url, self.remote.token)

    def raw(self, data, token=None):
        request = urllib.request.Request(self.remote.url + '/mcp', data=data,
                                         headers={'Authorization': 'Bearer ' + (token or self.remote.token)})
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read())

    def test_server_protocol_tools_and_auth(self):
        with urllib.request.urlopen(self.remote.url + '/health') as response:
            self.assertEqual(response.status, 200)
        for token in ('wrong', ''):
            request = urllib.request.Request(self.remote.url + '/mcp', data=b'{}', headers={'Authorization': token})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 401); error.exception.close()
        for payload, code in ((b'{', -32700), (b'[]', -32600), (b'{"jsonrpc":"1.0"}', -32600),
                              (b'{"jsonrpc":"2.0","method":"bad","id":7}', -32601),
                              (b'{"jsonrpc":"2.0","method":"tools/call","params":{},"id":7}', -32602)):
            result = self.raw(payload)
            self.assertEqual(result['error']['code'], code)
        self.assertEqual({t['name'] for t in self.client.discover()}, {'formula_hint', 'unit_convert'})
        self.assertIn('F=ma', self.client.call('formula_hint', '力和加速度'))
        self.assertIn('= 1 m', self.client.call('unit_convert', '把 100 cm 换算成 m'))
        self.assertIn('= 1 m', self.client.call('unit_convert', '把100厘米换算成米'))
        self.assertIn('32 f', self.client.call('unit_convert', '0 C to F'))
        with self.assertRaises(ValueError):
            self.remote.module.create_server(('127.0.0.1', 0), '')

    def store(self):
        conn = connect(':memory:'); self.addCleanup(conn.close); initialize(conn)
        conn.executescript("INSERT INTO classes VALUES(1,'A'),(2,'B'); INSERT INTO users VALUES(1,'teacher','hash','teacher',1);")
        user = dict(id=1, class_id=1, role='teacher')
        return conn, TutorStore(conn, user), McpStore(conn, user)

    def test_binding_execution_errors_and_state_change(self):
        conn, tutor, registry = self.store()
        server = registry.register(dict(name='campus-tools', base_url=self.remote.url, auth_token=self.remote.token))
        identity = server['id']; registry.connect(identity)
        self.assertNotIn(self.remote.token, json.dumps(registry.servers()))
        content = GUIDANCE_EXAMPLE.replace('knowledge_search', 'formula_hint@campus-tools')
        skill = tutor.save_skill({'content': content}); agent = tutor.save_agent({'name': 'A', 'skill_ids': [skill['id']]})
        conv = tutor.create_conversation(agent['id'])['id']
        result, value = registry.invoke(skill['tool'], '牛顿的力', conv)
        self.assertEqual(result['status'], 'ok'); self.assertIn('F=ma', value)
        with patch.object(McpClient, 'call', side_effect=McpError('MCP 工具执行失败')):
            self.assertEqual(registry.invoke(skill['tool'], '牛顿的力', conv)[0]['status'], 'error')
        def disconnect_during_call(*args):
            registry.disconnect(identity)
            return 'stale'
        with patch.object(McpClient, 'call', side_effect=disconnect_during_call):
            result, value = registry.invoke(skill['tool'], '牛顿的力', conv)
            self.assertEqual((result['status'], value), ('denied', ''))
        with patch.object(McpClient, 'call') as call:
            self.assertEqual(registry.invoke(skill['tool'], '牛顿的力', conv)[0]['status'], 'denied')
            call.assert_not_called()
        for reference in ('formula_hint@other', 'unknown@campus-tools', 'formula-hint@campus-tools'):
            with self.assertRaises(ValueError):
                tutor.save_skill({'content': content.replace(skill['tool'], reference)}, skill['id'])
        self.assertEqual(tutor.get('skills', skill['id'])['content'], content)
        self.assertEqual(len(registry.audits()), 4)

    def test_discovery_failure_is_atomic_and_incompatible_tools_cannot_bind(self):
        conn, tutor, registry = self.store()
        identity = registry.register(dict(name='campus-tools', base_url=self.remote.url, auth_token=self.remote.token))['id']
        registry.connect(identity)
        with patch.object(self.remote.module, 'TOOLS', [{'name': 'bad-tool', 'inputSchema': {'type': 'object'}}]):
            from campusclaw.tutor import ApiError
            with self.assertRaises(ApiError): registry.connect(identity)
        self.assertEqual(registry.tools(identity), [])
        self.assertEqual(registry.servers()[0]['status'], 'disconnected')
        with patch.object(self.remote.module, 'TOOLS', [{'name': 'formula_hint', 'description': 'different contract',
                                                        'inputSchema': {'type': 'object', 'required': ['x'],
                                                                        'properties': {'x': {'type': 'number'}}}}]):
            registry.connect(identity)
        self.assertFalse(registry.tools(identity)[0]['bindable'])
        with self.assertRaises(ValueError):
            tutor.save_skill({'content': GUIDANCE_EXAMPLE.replace('knowledge_search', 'formula_hint@campus-tools')})
        registry.disconnect(identity)
        def concurrent_disconnect(*args):
            registry.disconnect(identity)
            return self.remote.module.TOOLS
        with patch.object(McpClient, 'discover', side_effect=concurrent_disconnect):
            with self.assertRaises(ApiError) as error: registry.connect(identity)
            self.assertEqual(error.exception.status, 409)
        self.assertEqual(registry.tools(identity), [])

    def test_cross_class_reference_is_denied_without_network_request(self):
        conn, tutor, registry = self.store()
        conn.execute("INSERT INTO mcp_servers(class_id,name,base_url,auth_token,status) VALUES(2,'other-tools',?,'unused','connected')", (self.remote.url,))
        conn.commit()
        messages = []
        for name in ('other-tools', 'absent-tools'):
            with self.assertRaises(ValueError) as error: registry.resolve('formula_hint@' + name)
            messages.append(str(error.exception))
        self.assertEqual(messages[0], messages[1])
        agent = tutor.save_agent({'name': 'A'}); conv = tutor.create_conversation(agent['id'])['id']
        with patch.object(McpClient, 'call') as call:
            result, _ = registry.invoke('formula_hint@other-tools', 'question', conv)
            self.assertEqual(result['status'], 'denied'); call.assert_not_called()

    def test_schema_migration_preserves_data_and_foreign_keys(self):
        conn, tutor, registry = self.store()
        skill = tutor.save_skill({'content': GUIDANCE_EXAMPLE})
        agent = tutor.save_agent({'name': 'A', 'skill_ids': [skill['id']]})
        conv = tutor.create_conversation(agent['id'])
        turn, _ = tutor.start_turn(conv['id'], 'old question', []); tutor.finish_turn(turn, 'old answer', True)
        # Recreate exact old schema to exercise the migration with live associations.
        from campusclaw.tutor_schema import SCHEMA
        old_table = SCHEMA[SCHEMA.index('CREATE TABLE IF NOT EXISTS skills'):SCHEMA.index('CREATE UNIQUE INDEX')]
        conn.commit(); conn.execute('PRAGMA foreign_keys=OFF')
        conn.execute('CREATE TEMP TABLE saved_skills AS SELECT * FROM skills')
        conn.execute('DROP TABLE skills'); conn.executescript(old_table)
        conn.execute('INSERT INTO skills SELECT * FROM saved_skills'); conn.execute('DROP TABLE saved_skills')
        conn.execute("DELETE FROM schema_migrations WHERE name='week06_mcp'"); conn.commit()
        conn.execute('PRAGMA foreign_keys=ON')
        initialize(conn); initialize(conn)
        self.assertEqual(tutor.get('agents', agent['id'])['skill_ids'], [skill['id']])
        self.assertEqual(tutor.messages(conv['id'])[-1]['content'], 'old answer')
        self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(conn.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        registry.connect(registry.register(dict(name='campus-tools', base_url=self.remote.url, auth_token=self.remote.token))['id'])
        tutor.save_skill({'content': GUIDANCE_EXAMPLE.replace('knowledge_search', 'formula_hint@campus-tools')}, skill['id'])

    def test_client_rejects_invalid_remote_responses_and_redirects(self):
        for value in ('file:///tmp/a', 'http://user:pass@localhost', 'http://localhost?a=1', 'http://localhost#x'):
            with self.assertRaises(ValueError): base_url(value)
        class Handler(BaseHTTPRequestHandler):
            mode = 'id'
            def log_message(self, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                if self.mode == 'redirect':
                    self.send_response(302); self.send_header('Location', '/leak'); self.end_headers(); return
                self.send_response(200); self.end_headers()
                try:
                    if self.mode == 'slow':
                        for _ in range(10):
                            self.wfile.write(b' '); self.wfile.flush(); time.sleep(.06)
                    elif self.mode == 'large': self.wfile.write(b'x' * 1048577)
                    elif self.mode == 'invalid': self.wfile.write(b'not json')
                    else: self.wfile.write(b'{"jsonrpc":"2.0","id":"wrong","result":{}}')
                except ConnectionError:
                    pass
        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        self.addCleanup(http.server_close); self.addCleanup(http.shutdown)
        client = McpClient(f'http://127.0.0.1:{http.server_port}', 'test', timeout=.2)
        for mode in ('id', 'large', 'invalid', 'redirect', 'slow'):
            Handler.mode = mode
            with self.assertRaises(McpError): client.rpc('tools/list')


if __name__ == '__main__':
    unittest.main()
