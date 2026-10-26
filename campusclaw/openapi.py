"""Handler annotations drive both dispatch and OpenAPI generation."""
import re


def string(maximum=None, minimum=None):
    result = {'type': 'string'}
    if maximum is not None:
        result['maxLength'] = maximum
    if minimum is not None:
        result['minLength'] = minimum
    return result


def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required)}


ID = {'type': 'integer', 'minimum': 1, 'maximum': 9223372036854775807}
BOOL = {'type': 'boolean'}
IDS = {'type': 'array', 'items': ID, 'uniqueItems': True}
USER = obj({'id': ID, 'user_id': ID, 'username': string(), 'role': {'type': 'string', 'enum': ['teacher', 'student']}, 'class_id': ID})
SOURCE = obj({'id': ID, 'material_id': ID, 'personal_material_id': ID, 'attachment_id': ID, 'kind': string(), 'material_title': string(), 'citation': string(), 'subject': string(),
              'content': string(), 'ordinal': {'type': 'integer'}, 'char_start': {'type': 'integer'},
              'char_end': {'type': 'integer'}, 'url': string(), 'score': {'type': 'number'}})
SOURCES = {'type': 'array', 'items': SOURCE}
TOOL_CALL = obj({'tool_ref': string(), 'status': {'type': 'string', 'enum': ['ok', 'error', 'denied']},
                 'message': string()}, ['tool_ref', 'status'])
SSE_META = obj({'conversation_id': ID, 'message_id': ID, 'skill': {'type': 'object', 'nullable': True},
                'context': {'type': 'object', 'description': '本轮技能与资料选择快照'},
                'sources': SOURCES, 'tool_calls': {'type': 'array', 'items': TOOL_CALL}},
               ['conversation_id', 'message_id', 'skill', 'sources', 'tool_calls'])
AGENT_INPUT = obj({'name': string(64, 1), 'prompt': string(2000), 'enabled': BOOL, 'subject': string(64, 1),
                   'skill_ids': IDS, 'material_ids': IDS}, ['name'])
AGENT = obj({**AGENT_INPUT['properties'], 'id': ID, 'class_id': ID, 'effective_prompt': string()})
SKILL = obj({'id': ID, 'class_id': ID, 'name': string(64, 1), 'conditions': string(500, 1), 'enabled': BOOL,
             'tool': {**string(129), 'description': '空、knowledge_search 或 工具名@服务器名；MCP 必须属于本班且连接后已发现'},
             'body': string(), 'content': string(8000, 1)})
CONVERSATION = obj({'id': ID, 'owner_id': ID, 'class_id': ID, 'agent_id': ID, 'created_at': string(), 'title': string(), 'agent_name': string(), 'last_activity': string()})
MESSAGE = obj({'id': ID, 'conversation_id': ID, 'turn_id': string(), 'role': string(), 'content': string(),
               'sources': SOURCES, 'status': {'type': 'string', 'enum': ['generating', 'completed', 'failed', 'partial']},
               'created_at': string(), 'context': {'type': 'object'}})
MATERIAL = obj({'id': ID, 'title': string(), 'filename': string(), 'class_id': ID, 'status': string(),
                'subject': string(), 'content': string(), 'index_status': string(), 'knowledge_entry_id': ID})


def wrapped(name, schema, many=False):
    return obj({name: {'type': 'array', 'items': schema} if many else schema}, [name])


def endpoint(method, path, summary, *, body=None, response=None, status=200, public=False,
             errors=(), parameters=(), stream=False):
    def decorate(fn):
        fn.api = dict(method=method.upper(), path=path, summary=summary, body=body, response=response,
                      status=status, public=public, errors=errors, parameters=parameters, stream=stream)
        pattern = re.escape(path)
        for name in re.findall(r'\{(\w+)\}', path):
            value = '[a-z][a-z0-9-]{0,63}' if name == 'key' else '[0-9]+'
            pattern = pattern.replace(re.escape('{' + name + '}'), '(?P<' + name + '>' + value + ')')
        fn.route = re.compile('^' + pattern + '$')
        return fn
    return decorate


def handlers(cls):
    result, seen = [], set()
    for name in dir(cls):
        fn = getattr(cls, name)
        if hasattr(fn, 'api'):
            key = (fn.api['method'], fn.api['path'])
            if key in seen:
                raise ValueError('duplicate annotated route')
            seen.add(key)
            result.append((name, fn))
    return result


def generate(cls):
    paths = {}
    error_schema = obj({'error': string(), 'message': string()}, ['error'])
    descriptions = {400: '参数、模板、技能或命名校验失败', 401: '需要有效Bearer令牌', 403: '仅教师可用',
                    404: '资源不存在或不可访问（相同响应）', 409: '状态冲突、同名资源或会话忙',
                    413: '请求过大', 502: '远端协议、工具或生成结果无效', 503: '依赖暂不可用'}
    for name, fn in handlers(cls):
        a = fn.api
        params = [{'name': n, 'in': 'path', 'required': True,
                   'schema': {'type': 'string', 'pattern': '^[a-z][a-z0-9-]{0,63}$'} if n == 'key' else ID}
                  for n in re.findall(r'\{(\w+)\}', a['path'])]
        params += list(a['parameters'])
        media = 'text/event-stream' if a['stream'] else 'application/json'
        responses = {str(a['status']): {'description': '成功', 'content': {media: {'schema': a['response'] or {'type': 'object'}}}}}
        errors = set(a['errors']) | ({401} if not a['public'] else set())
        for code in sorted(errors):
            responses[str(code)] = {'description': descriptions.get(code, '错误'),
                                     'content': {'application/json': {'schema': error_schema}}}
        operation = dict(operationId=name, summary=a['summary'], parameters=params, responses=responses,
                         security=[] if a['public'] else [{'bearerAuth': []}])
        if a['body']:
            operation['requestBody'] = {'required': True, 'content': {'application/json': {'schema': a['body']}}}
        if a['stream']:
            operation['x-sse-events'] = {'meta': SSE_META, 'delta': obj({'text': string()}),
                                         'done': obj({'message_id': ID, 'status': string()}), 'error': error_schema}
            operation['description'] = ('消息 context 可省略以保留应用默认；skill:null 关闭技能，显式 {source:shared/upload,id} 直接选择；'
                                         'materials:[] 关闭资料，引用列表最多三份，支持shared/upload/personal资料来源；个人资料仅本人本班可跨会话复用。meta.context 与历史保留本轮选择。'
                                         'SSE事件：meta={conversation_id,message_id,skill,sources,tool_calls,context}；'
                                         'tool_calls 为数组，每项 {tool_ref,status,message}，status 为 ok/error/denied，无调用为 []；'
                                         'delta={text}仅新增文本；'
                                         'done={message_id,status}提交数据库后发送；error={code,message}失败且无done。'
                                         '开始流式前返回HTTP错误，开始后用error事件。可在/tutor逐段观察。')
        paths.setdefault(a['path'], {})[a['method'].lower()] = operation
    return {'openapi': '3.0.3', 'info': {'title': 'CampusClaw AI 应用平台 API', 'version': '0.7.0'},
            'paths': paths, 'components': {'schemas': {'ToolCall': TOOL_CALL, 'SseMeta': SSE_META},
                                           'securitySchemes': {'bearerAuth': {'type': 'http', 'scheme': 'bearer'}}}}


def swagger_page():
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>CampusClaw Swagger</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css">
<p id="fallback">接口文档加载中；若浏览器无法加载资源，可查看 <a href="/openapi.json">OpenAPI JSON</a>。
流式消息请在 <a href="/tutor">解题助手</a> 观察增量。</p>
<p><button id="use-login" type="button">使用当前登录鉴权</button><span id="auth-state" role="status"></span></p><div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
<script>if(window.SwaggerUIBundle){window.ui=SwaggerUIBundle({url:'/openapi.json',dom_id:'#swagger-ui',
persistAuthorization:false});document.getElementById('fallback').hidden=true;}
document.getElementById('use-login').onclick=()=>{const token=sessionStorage.getItem('campusclaw_access_token');
if(token&&window.ui){window.ui.preauthorizeApiKey('bearerAuth',token);document.getElementById('auth-state').textContent='已使用当前登录；刷新后需重新授权';}
else{document.getElementById('auth-state').textContent='请先在 CampusClaw 登录，或使用 Authorize 输入 Bearer 令牌';}};</script></html>'''
