"""Course MCP server. No dependencies; secrets enter only at runtime."""
import hmac
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROTOCOL = '2024-11-05'
SCHEMA = {'type': 'object', 'properties': {'question': {'type': 'string', 'minLength': 1, 'maxLength': 500}},
          'required': ['question'], 'additionalProperties': False}
TOOLS = [{'name': name, 'description': description, 'inputSchema': SCHEMA} for name, description in (
    ('formula_hint', '根据数学或物理问题提供公式与分步思考提示'),
    ('unit_convert', '从问题换算长度、质量、时间或摄氏/华氏温度；例如：把 100 cm 换算成 m'))]


def formula_hint(question):
    for words, hint in ((('力', '加速度', '牛顿'), '牛顿第二定律 F=ma：先画受力图，再统一质量和加速度单位。'),
                        (('速度', '路程', '时间'), '匀速运动 s=vt：先列已知量，再判断能否使用匀速假设。'),
                        (('方程', '二次'), '一元二次方程 ax²+bx+c=0：先检查 a≠0，再求判别式 Δ=b²−4ac。'),
                        (('面积', '圆'), '圆面积 S=πr²：先确认给出的是半径还是直径。')):
        if any(word in question for word in words):
            return hint + ' 请先写出你准备代入的量，再检查推理。'
    return '先列已知条件和目标量，再选择定义或公式；请补充题目中的学科与物理量，我会给下一步提示。'


def unit_convert(question):
    aliases = {'毫米': 'mm', '厘米': 'cm', '千米': 'km', '米': 'm', '千克': 'kg', '克': 'g',
               '小时': 'h', '分钟': 'min', '秒': 's', '摄氏度': 'c', '华氏度': 'f', '°c': 'c', '°f': 'f'}
    normalized = question.lower()
    for word, unit in aliases.items():
        normalized = normalized.replace(word, unit)
    match = re.search(r'([-+]?\d+(?:\.\d+)?)\s*(mm|cm|km|kg|min|m|g|h|s|c|f)(?![a-z]).*?(?:换算成|转换为|换成|转为|成|为|to|→|=)\s*(mm|cm|km|kg|min|m|g|h|s|c|f)(?![a-z])', normalized)
    if not match:
        return '请明确数值、原单位和目标单位，例如：把 100 cm 换算成 m。支持 mm/cm/m/km、g/kg、s/min/h、C/F。'
    number, source, target = float(match[1]), match[2], match[3]
    groups = ({'mm': .001, 'cm': .01, 'm': 1, 'km': 1000}, {'g': 1, 'kg': 1000}, {'s': 1, 'min': 60, 'h': 3600})
    if source == target:
        result = number
    elif source in ('c', 'f') and target in ('c', 'f'):
        result = number * 9 / 5 + 32 if source == 'c' else (number - 32) * 5 / 9
    else:
        group = next((group for group in groups if source in group and target in group), None)
        if not group:
            return '原单位和目标单位的量纲不同，不能转换。'
        result = number * group[source] / group[target]
    return f'{number:g} {source} = {result:g} {target}'


class RpcError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def dispatch(request):
    if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'), str):
        raise RpcError(-32600, '请求必须为 JSON-RPC 2.0 对象')
    if 'id' in request and (type(request['id']) not in (int, str) and request['id'] is not None):
        raise RpcError(-32600, '请求 id 必须为字符串、整数或 null')
    method, params = request['method'], request.get('params', {})
    if not isinstance(params, dict):
        raise RpcError(-32602, 'params 必须为对象')
    if method == 'notifications/initialized' and 'id' not in request:
        return None
    if method == 'initialize':
        if params.get('protocolVersion') != PROTOCOL:
            raise RpcError(-32602, '不支持的协议版本；使用 ' + PROTOCOL)
        return {'protocolVersion': PROTOCOL, 'capabilities': {'tools': {'listChanged': False}},
                'serverInfo': {'name': 'campus-tools', 'version': '1.0.0'}}
    if method == 'tools/list':
        return {'tools': TOOLS}
    if method == 'tools/call':
        name, arguments = params.get('name'), params.get('arguments')
        if name not in ('formula_hint', 'unit_convert'):
            raise RpcError(-32602, '未知工具')
        if (not isinstance(arguments, dict) or set(arguments) != {'question'} or
                not isinstance(arguments['question'], str) or not 1 <= len(arguments['question'].strip()) <= 500):
            raise RpcError(-32602, 'arguments 只接受 1 至 500 字的 question')
        value = (formula_hint if name == 'formula_hint' else unit_convert)(arguments['question'])
        return {'content': [{'type': 'text', 'text': value}], 'isError': False}
    raise RpcError(-32601, '未知方法')


def create_server(address, token):
    if not token or not token.strip() or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError('MCP_AUTH_TOKEN 必须为非空、无空白的 ASCII 令牌')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.send_json(200 if self.path == '/health' else 404,
                           {'status': 'ok'} if self.path == '/health' else {'error': 'not_found'})

        def do_POST(self):
            if self.path != '/mcp':
                self.send_json(404, {'error': 'not_found'})
                return
            supplied = self.headers.get('Authorization', '').encode('utf-8')
            if not hmac.compare_digest(supplied, ('Bearer ' + token).encode()):
                self.send_json(401, {'error': 'unauthorized'})
                return
            request, identity = None, None
            try:
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    raise RpcError(-32600, 'Content-Length 非法')
                if not 0 < length <= 65536:
                    raise RpcError(-32600, '请求体必须为 1 至 65536 字节')
                self.connection.settimeout(10)
                try:
                    request = json.loads(self.rfile.read(length))
                except (ValueError, UnicodeError):
                    raise RpcError(-32700, '无法解析 JSON')
                if isinstance(request, dict) and (type(request.get('id')) in (int, str) or request.get('id') is None):
                    identity = request.get('id')
                result = dispatch(request)
                if 'id' not in request:
                    self.send_response(202); self.send_header('Content-Length', '0'); self.end_headers()
                    return
                self.send_json(200, {'jsonrpc': '2.0', 'id': identity, 'result': result})
            except RpcError as exc:
                self.send_json(200, {'jsonrpc': '2.0', 'id': identity, 'error': {'code': exc.code, 'message': exc.message}})
            except (TimeoutError, ConnectionError):
                self.close_connection = True
            except Exception:
                self.send_json(200, {'jsonrpc': '2.0', 'id': identity,
                                     'error': {'code': -32603, 'message': '工具服务内部错误'}})

    return ThreadingHTTPServer(address, Handler)


if __name__ == '__main__':
    server = create_server(('0.0.0.0', int(os.environ.get('PORT', '8090'))), os.environ.get('MCP_AUTH_TOKEN'))
    server.serve_forever()
