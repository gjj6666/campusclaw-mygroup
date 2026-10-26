import json
import threading
import urllib.error
from dataclasses import replace

from campusclaw.skills import GUIDANCE_EXAMPLE
from campusclaw.gateway import GatewayUnavailable
from campusclaw.openapi import endpoint, generate, obj, string
from tests import test_web


class StreamChat:
    def __init__(self):
        self.requests = []
        self.fail = False
        self.invalid = False
        self.entered = threading.Event()
        self.release = None
        self.pause_after_delta = None

    def stream(self, messages):
        self.requests.append(messages)
        self.entered.set()
        if self.release:
            self.release.wait(5)
        evidence = '[S1]' in messages[-1]['content']
        guide = '技能：' in messages[0]['content']
        yield '先列出已知条件。' if guide else '可以从定义开始。'
        if self.pause_after_delta:
            self.pause_after_delta.wait(5)
        if self.fail:
            raise GatewayUnavailable('simulated')
        yield '接下来你准备使用哪个公式？' if guide else '逐步检查推理。'
        if evidence:
            yield '[S99]' if self.invalid else '[S1]'
        elif self.invalid:
            yield '[S1]'


class TutorWebTests(test_web.WebTests):
    def setUp(self):
        super().setUp()
        self.app.config = replace(self.config, chat_base_url='http://example/v1', chat_api_key='test')
        self.chat = StreamChat()
        self.app.rag.chat = self.chat
        self.teacher_token = self.login_token('teacher_a', 'teacher-pass')
        self.student_token = self.login_token('student_a', 'student-pass')
        self.other_token = self.login_token('teacher_b', 'teacher-pass')

    def api(self, path, method='GET', data=None, token=None):
        try:
            response = self.request(path, method=method, data=data, token=token or self.teacher_token)
            return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def new_agent(self, **data):
        status, result = self.api('/api/agents', 'POST', {'name': '助教', **data})
        self.assertEqual(status, 201)
        return result['agent']['id']

    def new_conversation(self, agent):
        status, result = self.api('/api/conversations', 'POST', {'agent_id': agent}, self.student_token)
        self.assertEqual(status, 201)
        return result['conversation']['id']

    def frames(self, conv, question='解题如何开始'):
        response = self.request(f'/api/conversations/{conv}/messages', method='POST',
                                data={'question': question}, token=self.student_token)
        self.assertEqual(response.headers['X-Accel-Buffering'], 'no')
        frames = []
        event = None
        for raw in response:
            line = raw.decode().strip()
            if line.startswith('event: '):
                event = line[7:]
            if line.startswith('data: '):
                frames.append((event, json.loads(line[6:])))
        return frames

    def test_http_configuration_scope_and_validation(self):
        _, result = self.api('/api/skills', 'POST', {'content': GUIDANCE_EXAMPLE})
        skill = result['skill']['id']
        agent = self.new_agent(skill_ids=[skill], prompt=' ')
        self.assertEqual(self.api('/api/agents', 'POST', {'name': 'bad'}, self.student_token)[0], 403)
        self.assertEqual(self.api('/api/skills', 'POST', {'content': GUIDANCE_EXAMPLE}, self.student_token)[0], 403)
        self.assertEqual(self.api('/api/skills', 'POST', {'content': GUIDANCE_EXAMPLE})[0], 400)
        for resource, identity in (('agents', agent), ('skills', skill)):
            self.assertEqual(self.api(f'/api/{resource}/{identity}', token=self.other_token),
                             self.api(f'/api/{resource}/999999', token=self.other_token))
        for value in (None, 999999):
            self.assertEqual(self.api('/api/conversations', 'POST', {'agent_id': value}, self.student_token),
                             (404, {'error': 'not_found'}))
        self.assertEqual(self.api('/api/conversations', 'POST', {'agent_id': agent}, self.other_token),
                         (404, {'error': 'not_found'}))
        for data in ({'name': 'x' * 65}, {'prompt': 'x' * 2001}, {'material_ids': [999]}):
            self.assertIn(self.api(f'/api/agents/{agent}', 'PUT', data)[0], (400, 404))
        self.assertEqual(self.app.conn.execute('SELECT name FROM agents WHERE id=?', (agent,)).fetchone()[0], '助教')
        self.api(f'/api/skills/{skill}', 'DELETE')
        self.assertEqual(self.api(f'/api/agents/{agent}')[1]['agent']['skill_ids'], [])

    def test_unicode_skill_file_and_prompt_accept_exact_limits(self):
        prefix = '名称：长文件\n适用条件：解题\n启用：是\n\n'
        content = prefix + '文' * (8000 - len(prefix))
        status, result = self.api('/api/skills', 'POST', {'content': content})
        self.assertEqual(status, 201)
        self.assertEqual(len(result['skill']['content']), 8000)
        self.assertEqual(self.api('/api/skills', 'POST', {'content': content + '文'})[0], 400)
        agent = self.new_agent(name='名' * 64, prompt='文' * 2000)
        self.assertEqual(len(self.api(f'/api/agents/{agent}')[1]['agent']['prompt']), 2000)
        self.assertEqual(self.api('/api/agents/' + '9' * 80), (404, {'error': 'not_found'}))

    def test_http_conversation_ownership_and_disabled_agent(self):
        agent = self.new_agent()
        conv = self.new_conversation(agent)
        self.assertEqual(self.api('/api/conversations', token=self.other_token)[1]['conversations'], [])
        for path in (f'/api/conversations/{conv}', f'/api/conversations/{conv}/messages'):
            self.assertEqual(self.api(path, token=self.other_token), (404, {'error': 'not_found'}))
        self.assertEqual(self.api(f'/api/conversations/{conv}/messages', 'POST', {'question': '问题'}, self.other_token),
                         self.api('/api/conversations/999999/messages', 'POST', {'question': '问题'}, self.other_token))
        self.api(f'/api/agents/{agent}', 'PUT', {'enabled': False})
        self.assertEqual(self.api('/api/conversations', 'POST', {'agent_id': agent}, self.student_token)[0], 404)
        self.assertEqual(self.frames(conv)[-1][0], 'done')

    def test_stream_and_database_and_immediate_skill_switch(self):
        skill = self.api('/api/skills', 'POST', {'content': GUIDANCE_EXAMPLE})[1]['skill']['id']
        skill2 = self.api('/api/skills', 'POST', {'content': GUIDANCE_EXAMPLE.replace('解题引导', '解题引导二')})[1]['skill']['id']
        agent = self.new_agent(skill_ids=[skill, skill2])
        conv = self.new_conversation(agent)
        frames = self.frames(conv)
        self.assertEqual(frames[0][1]['skill']['id'], skill)
        self.assertEqual(len([e for e, _ in frames if e == 'delta']), 2)
        answer = ''.join(d['text'] for e, d in frames if e == 'delta')
        self.assertIn('你准备', answer)
        self.assertEqual(self.chat.requests[-1][0]['content'].count('技能：'), 1)
        rows = self.api(f'/api/conversations/{conv}/messages', token=self.student_token)[1]['messages']
        self.assertEqual(rows[-1]['content'], answer)
        self.assertEqual(rows[-1]['status'], 'completed')
        for identity, content in ((skill, GUIDANCE_EXAMPLE), (skill2, GUIDANCE_EXAMPLE.replace('解题引导', '解题引导二'))):
            self.api(f'/api/skills/{identity}', 'PUT', {'content': content.replace('启用：是', '启用：否')})
        self.assertIsNone(self.frames(conv)[0][1]['skill'])
        self.assertNotIn('技能：', self.chat.requests[-1][0]['content'])

    def test_failed_partial_excluded_from_history(self):
        conv = self.new_conversation(self.new_agent())
        self.chat.fail = True
        frames = self.frames(conv)
        self.assertEqual(frames[-1][0], 'error')
        self.assertNotIn('done', [e for e, _ in frames])
        rows = self.api(f'/api/conversations/{conv}/messages', token=self.student_token)[1]['messages']
        self.assertEqual([r['status'] for r in rows], ['failed', 'partial'])
        self.chat.fail = False
        self.frames(conv)
        self.assertEqual(len(self.chat.requests[-1]), 2)
        self.chat.invalid = True
        self.assertEqual(self.frames(conv)[-1][0], 'error')

    def test_concurrent_streams_and_incremental_arrival(self):
        agent = self.new_agent()
        conv = self.new_conversation(agent)
        other_conv = self.new_conversation(agent)
        self.chat.release = threading.Event()
        response = self.request(f'/api/conversations/{conv}/messages', method='POST',
                                data={'question': '解题问题'}, token=self.student_token)
        self.assertEqual(response.readline().decode().strip(), 'event: meta')
        self.assertTrue(self.chat.entered.wait(2))
        self.assertEqual(self.api(f'/api/conversations/{conv}/messages', 'POST', {'question': '解题问题'}, self.student_token)[0], 409)
        response2 = self.request(f'/api/conversations/{other_conv}/messages', method='POST',
                                 data={'question': '解题问题'}, token=self.student_token)
        self.assertEqual(response2.readline().decode().strip(), 'event: meta')
        self.chat.release.set()
        self.assertIn(b'event: done', response.read())
        self.assertIn(b'event: done', response2.read())
        self.assertEqual(self.frames(conv)[-1][0], 'done')

    def test_openapi_annotation_source(self):
        status, doc = self.api('/openapi.json')
        self.assertEqual(status, 200)
        self.assertEqual(doc['paths']['/api/login']['post']['security'], [])
        self.assertEqual(doc['paths']['/api/agents']['post']['security'], [{'bearerAuth': []}])
        self.assertIn('403', doc['paths']['/api/skills']['post']['responses'])
        self.assertIn('text/event-stream', doc['paths']['/api/conversations/{id}/messages']['post']['responses']['200']['content'])
        class Example:
            @endpoint('GET', '/original', '示例', response=obj({'text': string()}))
            def handler(self):
                pass
        Example.handler.api['path'] = '/changed'
        self.assertIn('/changed', generate(Example)['paths'])
        class Duplicate(Example):
            handler2 = Example.handler
        with self.assertRaises(ValueError):
            generate(Duplicate)

    def test_delta_is_visible_before_generation_finishes(self):
        conv = self.new_conversation(self.new_agent())
        self.chat.pause_after_delta = threading.Event()
        response = self.request(f'/api/conversations/{conv}/messages', method='POST',
                                data={'question': '解题问题'}, token=self.student_token)
        for raw in response:
            if raw.startswith(b'event: delta'):
                break
        self.assertEqual(self.app.conn.execute("SELECT status FROM messages WHERE conversation_id=? AND role='assistant'", (conv,)).fetchone()[0], 'generating')
        self.chat.pause_after_delta.set()
        self.assertIn(b'event: done', response.read())

    def test_disconnect_records_failure_and_releases_lock(self):
        import socket
        import struct
        import time
        conv = self.new_conversation(self.new_agent())
        self.chat.release = threading.Event()
        sock = socket.create_connection(('127.0.0.1', self.server.server_port))
        body = json.dumps({'question': '解题问题'}).encode()
        header = (f'POST /api/conversations/{conv}/messages HTTP/1.0\r\nHost: localhost\r\n'
                  f'Authorization: Bearer {self.student_token}\r\nContent-Type: application/json\r\n'
                  f'Content-Length: {len(body)}\r\n\r\n').encode()
        sock.sendall(header + body)
        self.assertTrue(self.chat.entered.wait(2))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('hh', 1, 0))
        sock.close()
        self.chat.release.set()
        deadline = time.monotonic() + 3
        while conv in self.app.generating and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertNotIn(conv, self.app.generating)
        rows = self.app.conn.execute('SELECT status FROM messages WHERE conversation_id=?', (conv,)).fetchall()
        self.assertTrue(rows)
        self.assertTrue(all(r[0] in ('failed', 'partial') for r in rows))
