import json
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from campusclaw.config import Config
from campusclaw.gateway import ChatClient
from campusclaw.rag import RagService
from campusclaw.services import create_user
from campusclaw.skills import GUIDANCE_EXAMPLE
from campusclaw.web import Application, create_handler


class Embedder:
    def embed(self, text):
        return [.5, .5]


class Vectors:
    def __init__(self):
        self.points = {}
    def ensure_collection(self):
        pass
    def upsert(self, points):
        self.points.update({p['id']: p for p in points})
    def delete(self, ids):
        for identity in ids:
            self.points.pop(identity, None)
    def query(self, vector, class_id, limit, min_score, index_version, material_ids=None):
        # Keyword ranking supplies deterministic evidence; unit tests separately
        # verify Qdrant filtering and forged-vector authorization.
        return []


class ModelHandler(BaseHTTPRequestHandler):
    requests = []
    def log_message(self, *args):
        pass
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(data)
        guide = '技能：' in data['messages'][0]['content']
        sourced = '[S1]' in data['messages'][-1]['content']
        parts = ['先列出已知条件。', '接下来你准备使用哪个公式？'] if guide else ['可以从定义开始。', '逐步检查推理。']
        if sourced:
            parts.append('[S1]')
        if not data.get('stream'):
            answer = json.dumps({'choices': [{'message': {'content': ''.join(parts)}}]}, ensure_ascii=False).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(answer))); self.end_headers(); self.wfile.write(answer)
            return
        self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
        for part in parts:
            wire = ('data: ' + json.dumps({'choices': [{'delta': {'content': part}, 'finish_reason': None}]}, ensure_ascii=False) + '\n\n').encode()
            self.wfile.write(wire[:15]); self.wfile.flush()
            time.sleep(.02)
            self.wfile.write(wire[15:]); self.wfile.flush()
        self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'); self.wfile.flush()


class Context:
    def __init__(self, live=False):
        self.live = live
        self.tmp = tempfile.TemporaryDirectory()
        self.password = 'local-test-password'
        self.model = None
        if live:
            self.config = replace(Config.from_env(), database_path=self.tmp.name + '/live.db', seed_demo_users=False,
                                  qdrant_collection='campusclaw_apitest_' + secrets.token_hex(6))
            if self.config.validate_rag():
                raise RuntimeError('本机网关配置不完整')
        else:
            self.model = ThreadingHTTPServer(('127.0.0.1', 0), ModelHandler)
            self.model.requests = []
            threading.Thread(target=self.model.serve_forever, daemon=True).start()
            self.config = Config('isolated-test-secret', self.tmp.name + '/test.db', 10000, False, None, None,
                                 embedding_base_url='http://example/v1', embedding_api_key='test', embedding_dim=2,
                                 chat_base_url=f'http://127.0.0.1:{self.model.server_port}/v1', chat_api_key='test')
        self.app = Application(self.config)
        self.app.conn.executescript("INSERT INTO classes VALUES(1,'A'),(2,'B');")
        for name, role, class_id in (('teacher', 'teacher', 1), ('student', 'student', 1), ('peer', 'student', 1), ('other', 'teacher', 2)):
            create_user(self.app.conn, username=name, password=self.password, role=role, class_id=class_id)
        if not live:
            self.app.rag = RagService(self.app.conn, self.config, embedder=Embedder(), vectors=Vectors(),
                                      chat=ChatClient(self.config.chat_base_url, 'test', 'course-chat'))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), create_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.tokens = {}
        self.evidence = []
        for name in ('teacher', 'student', 'peer', 'other'):
            status, data = self.request('/api/login', 'POST', {'username': name, 'password': self.password}, auth=None)
            assert status == 200
            self.tokens[name] = data['access_token']

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)
        if self.model:
            self.model.shutdown(); self.model.server_close()
        if self.live and self.config.qdrant_collection.startswith('campusclaw_apitest_'):
            from campusclaw.vector_store import VectorStoreError
            try:
                self.app.rag.vectors._request('DELETE', self.app.rag.vectors.path)
            except VectorStoreError:
                pass  # Collection may not have been created when preflight failed.
        self.app.close(); self.tmp.cleanup()

    def request(self, path, method='GET', data=None, auth='teacher'):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if auth is not None:
            headers['Authorization'] = 'Bearer ' + self.tokens[auth]
        req = urllib.request.Request(self.base + path, method=method, headers=headers,
                                     data=None if data is None else json.dumps(data).encode())
        try:
            response = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as exc:
            result = json.loads(exc.read())
            self.record(path, method, exc.code, data, result)
            return exc.code, result
        with response:
            if response.headers.get('Content-Type', '').startswith('text/event-stream'):
                frames, event = [], None
                for raw in response:
                    line = raw.decode().strip()
                    if line.startswith('event: '):
                        event = line[7:]
                    if line.startswith('data: '):
                        frames.append((event, json.loads(line[6:])))
                self.record(path, method, response.status, data, frames)
                return response.status, frames
            if response.headers.get('Content-Type', '').startswith('text/html'):
                page = response.read().decode('utf-8')
                self.record(path, method, response.status, data, {'html': '页面返回成功'})
                return response.status, page
            result = json.loads(response.read())
            self.record(path, method, response.status, data, result)
            return response.status, result

    def record(self, path, method, status, data, result):
        def redact(value):
            if isinstance(value, dict):
                return {k: '[REDACTED]' if any(secret in k.lower() for secret in ('token', 'password', 'secret', 'api_key', 'authorization'))
                        else redact(v) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                return [redact(v) for v in value]
            if isinstance(value, str):
                return value.encode('utf-8', errors='replace').decode('utf-8')
            return value
        if path == '/api/login':
            result = {k: v for k, v in result.items() if k not in ('access_token',)}
        if self.live:
            # Live runs save only the separately selected course-answer evidence.
            result = {'shape': type(result).__name__}
        self.evidence.append({'method': method, 'path': path, 'status': status,
                              'request': redact(data), 'response': redact(result)})

    def row(self, table, identity):
        assert table in ('users', 'agents', 'skills', 'conversations', 'messages', 'materials', 'knowledge_chunks')
        row = self.app.conn.execute(f'SELECT * FROM {table} WHERE id=?', (identity,)).fetchone()
        return dict(row) if row else None

    def skill(self, content=GUIDANCE_EXAMPLE):
        status, data = self.request('/api/skills', 'POST', {'content': content})
        assert status == 201, data
        return data['skill']

    def agent(self, **values):
        status, data = self.request('/api/agents', 'POST', {'name': '测试助教', **values})
        assert status == 201, data
        return data['agent']

    def conversation(self, agent=None):
        agent = agent or self.agent()
        status, data = self.request('/api/conversations', 'POST', {'agent_id': agent['id']}, 'student')
        assert status == 201, data
        return data['conversation']

    def material(self, content='牛顿第一定律：物体不受外力时保持运动状态。', subject='物理'):
        status, data = self.request('/api/materials', 'POST', {'filename': 'lesson.txt', 'content': content, 'subject': subject})
        assert status == 201, data
        return data['material']
