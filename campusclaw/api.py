"""Annotated HTTP handlers for the tutor APIs."""
import json

from .gateway import GatewayError
from .orchestration import prepare, validate_answer
from .rag import InvalidAnswer, RagUnavailable
from .tutor import ApiError
from .mcp_api import McpApi
from .platform_api import PlatformApi
from .attachment_api import AttachmentApi, CONTEXT
from .attachments import Attachments
from .workspace_api import WorkspaceApi
from .openapi import (endpoint, obj, wrapped, string, ID, USER, SOURCE, SOURCES, AGENT_INPUT, AGENT,
                      SKILL, CONVERSATION, MESSAGE, MATERIAL)


class TutorApi(McpApi, PlatformApi, AttachmentApi, WorkspaceApi):
    @endpoint('GET', '/api/agents', '本班智能体列表', response=wrapped('agents', AGENT, True))
    def agents_list(self):
        self._json(200, {'agents': self.store.list('agents')})

    @endpoint('POST', '/api/agents', '教师创建智能体及绑定', body=AGENT_INPUT,
              response=wrapped('agent', AGENT), status=201, errors=(400, 403, 404, 413))
    def agents_create(self):
        self._json(201, {'agent': self.store.save_agent(self._read_payload())})

    @endpoint('GET', '/api/agents/{id}', '读取本班智能体', response=wrapped('agent', AGENT), errors=(404,))
    def agents_get(self, id):
        self._json(200, {'agent': self.store.get('agents', id)})

    @endpoint('PUT', '/api/agents/{id}', '教师更新智能体及绑定', body=obj(AGENT_INPUT['properties']),
              response=wrapped('agent', AGENT), errors=(400, 403, 404, 413))
    def agents_update(self, id):
        self._json(200, {'agent': self.store.save_agent(self._read_payload(), id)})

    @endpoint('GET', '/api/skills', '本班技能列表', response=wrapped('skills', SKILL, True))
    def skills_list(self):
        self._json(200, {'skills': self.store.list('skills')})

    @endpoint('POST', '/api/skills', '教师解析并创建技能文件', body=obj({'content': string(8000, 1)}, ['content']),
              response=wrapped('skill', SKILL), status=201, errors=(400, 403, 413))
    def skills_create(self):
        self._json(201, {'skill': self.store.save_skill(self._read_payload())})

    @endpoint('GET', '/api/skills/{id}', '读取本班技能', response=wrapped('skill', SKILL), errors=(404,))
    def skills_get(self, id):
        self._json(200, {'skill': self.store.get('skills', id)})

    @endpoint('PUT', '/api/skills/{id}', '教师重新解析并更新技能', body=obj({'content': string(8000, 1)}, ['content']),
              response=wrapped('skill', SKILL), errors=(400, 403, 404, 413))
    def skills_update(self, id):
        self._json(200, {'skill': self.store.save_skill(self._read_payload(), id)})

    @endpoint('DELETE', '/api/skills/{id}', '教师删除技能及绑定', response=obj({'deleted': ID}, ['deleted']), errors=(403, 404))
    def skills_delete(self, id):
        self.store.delete_skill(id)
        self._json(200, {'deleted': id})

    @endpoint('GET', '/api/conversations', '本人本班会话列表', response=wrapped('conversations', CONVERSATION, True))
    def conversations_list(self):
        self._json(200, {'conversations': self.store.list('conversations')})

    @endpoint('POST', '/api/conversations', '选择本班已启用智能体新建会话', body=obj({'agent_id': ID}, ['agent_id']),
              response=wrapped('conversation', CONVERSATION), status=201, errors=(400, 404, 413))
    def conversations_create(self):
        self._json(201, {'conversation': self.store.create_conversation(self._read_payload().get('agent_id'))})

    @endpoint('GET', '/api/conversations/{id}', '读取本人会话', response=wrapped('conversation', CONVERSATION), errors=(404,))
    def conversations_get(self, id):
        self._json(200, {'conversation': self.store.get('conversations', id)})

    @endpoint('GET', '/api/conversations/{id}/messages', '读取完整历史与生成状态', response=wrapped('messages', MESSAGE, True), errors=(404,))
    def messages_get(self, id):
        self._json(200, {'messages': self.store.messages(id)})

    @endpoint('POST', '/api/conversations/{id}/messages', '先检索再流式生成并落库',
              body=obj({'question': string(500, 2), 'context': CONTEXT}, ['question']), response={'type': 'string'},
              errors=(400, 404, 409, 413, 503), stream=True)
    def messages_send(self, id):
        # Authorize before locking, reading configuration, or invoking dependencies.
        self.store.get('conversations', id)
        payload = self._read_payload()
        from .tutor import text
        question = text(payload.get('question'), '提问', 500, 2)
        if 'context' in payload and not isinstance(payload['context'], dict):
            raise ValueError('context 必须为对象')
        selected = Attachments(self.store).resolve(id, payload.get('context'))
        with self.app.lock_guard:
            if id in self.app.generating:
                raise ApiError(409, 'conversation_busy')
            self.app.generating.add(id)
        started, turn, answer, success = False, None, '', False
        try:
            if not self.app.config.chat_base_url or not self.app.config.chat_api_key:
                raise ApiError(503, 'answer_unavailable')
            question, messages, sources, skill, tool_calls = prepare(self.store, self.rag, id, question, include_tools=True, resolved=selected)
            snapshot = {**selected['snapshot']}
            if 'skill' not in snapshot:
                snapshot['skill'] = {**skill, 'source': 'shared', 'mode': 'auto'} if skill else None
            if 'materials' not in snapshot:
                agent = self.store.get('agents', self.store.get('conversations', id)['agent_id'])
                snapshot['materials'] = [dict(id=i, source='shared', mode='default', name=next(
                    (r[0] for r in self.store.conn.execute('SELECT title FROM materials WHERE id=? AND class_id=?',
                     (i, self.store.class_id))), f'资料 {i}')) for i in agent['material_ids']]
            turn, message_id = self.store.start_turn(id, question, sources, snapshot)
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Accel-Buffering', 'no')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            started = True
            self._event('meta', {'conversation_id': id, 'message_id': message_id, 'skill': skill, 'sources': sources,
                                 'tool_calls': tool_calls, 'context': snapshot})
            stream = self.rag.chat.stream(messages)
            try:
                for delta in stream:
                    if not isinstance(delta, str):
                        raise InvalidAnswer('模型增量格式错误')
                    answer += delta
                    if len(answer) > 100000:
                        raise InvalidAnswer('模型回答过长')
                    self._event('delta', {'text': delta})
            finally:
                if hasattr(stream, 'close'):
                    stream.close()
            validate_answer(answer, sources)
            self.store.finish_turn(turn, answer, True)
            success = True
            self._event('done', {'message_id': message_id, 'status': 'completed'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (GatewayError, RagUnavailable, InvalidAnswer) as exc:
            if not started:
                raise ApiError(503, 'answer_unavailable') from exc
            self._safe_error('generation_failed', '生成失败，请重试；当前回答未完成。')
        except Exception:
            if not started:
                raise
            self._safe_error('generation_failed', '生成失败，请重试；当前回答未完成。')
        finally:
            try:
                if turn and not success:
                    self.store.finish_turn(turn, answer, False)
            finally:
                with self.app.lock_guard:
                    self.app.generating.discard(id)

    def _event(self, event, value):
        frame = f'event: {event}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n'
        self.wfile.write(frame.encode('utf-8'))
        self.wfile.flush()

    def _safe_error(self, code, message):
        try:
            self._event('error', {'code': code, 'message': message})
        except (BrokenPipeError, ConnectionResetError):
            pass

    # Legacy handlers remain the source of business behavior. Their annotations
    # register the exact same dispatch paths as the new handlers.
    @endpoint('POST', '/api/login', '登录换取一小时Bearer令牌', public=True,
              body=obj({'username': string(), 'password': string()}, ['username', 'password']),
              response=obj({'access_token': string(), 'token_type': string(), 'expires_in': {'type': 'integer'}, 'user': USER}),
              errors=(400, 401, 413, 503))
    def login_api(self):
        self._legacy_POST()

    @endpoint('GET', '/health', '服务健康检查', public=True,
              response=obj({'status': string(), 'missing': {'type': 'array', 'items': string()}}), errors=(503,))
    def health_api(self):
        self._legacy_GET()

    @endpoint('GET', '/api/search', '检索本班材料', response=wrapped('results', SOURCE, True), errors=(400, 503),
              parameters=({'name': 'q', 'in': 'query', 'required': True, 'schema': string(2000, 1)},
                          {'name': 'mode', 'in': 'query', 'schema': {'type': 'string', 'enum': ['keyword', 'vector', 'hybrid'], 'default': 'hybrid'}},
                          {'name': 'limit', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1, 'maximum': 100, 'default': 5}}))
    def search_api(self):
        self._legacy_GET()

    @endpoint('POST', '/api/ask', '第4课有依据的单次问答', body=obj({'question': string(2000, 1)}, ['question']),
              response=obj({'status': string(), 'answer': string(), 'sources': SOURCES}), errors=(400, 413, 502, 503))
    def ask_api(self):
        self._legacy_POST()

    @endpoint('GET', '/materials', '读取本班材料列表；浏览器可请求HTML',
              response=obj({'user': USER, 'materials': {'type': 'array', 'items': MATERIAL}}))
    def materials_api(self):
        self._legacy_GET()

    @endpoint('GET', '/materials/{id}', '读取本班材料原文', response=wrapped('material', MATERIAL), errors=(403,))
    def material_api(self, id):
        self._legacy_GET()

    @endpoint('POST', '/api/materials', '教师上传材料并建立索引', status=201, response=wrapped('material', MATERIAL),
              body=obj({'filename': string(), 'content': string(), 'subject': string(64, 1)}, ['filename', 'content']), errors=(400, 403, 413))
    def upload_api(self):
        self._legacy_POST()
