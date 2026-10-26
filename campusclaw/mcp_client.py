"""Bounded JSON-RPC HTTP client; never expose remote payloads as errors."""
import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

PROTOCOL = '2024-11-05'
TOOL_NAME = re.compile(r'[a-z][a-z0-9_]{0,63}')
SERVER_NAME = re.compile(r'[a-z][a-z0-9_-]{0,63}')
REFERENCE = re.compile(r'([a-z][a-z0-9_]{0,63})@([a-z][a-z0-9_-]{0,63})')


class McpError(Exception):
    pass


def base_url(value):
    if not isinstance(value, str) or len(value) > 2000 or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('Base URL 非法')
    parsed = urllib.parse.urlsplit(value)
    try:
        valid = parsed.scheme in ('http', 'https') and parsed.hostname and parsed.port != 0
    except ValueError:
        valid = False
    if not valid or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValueError('Base URL 仅支持无凭证、查询或片段的 http/https 地址')
    return value.rstrip('/')


def supports_question(schema):
    if not isinstance(schema, dict) or schema.get('type') != 'object':
        return False
    properties, required = schema.get('properties', {}), schema.get('required', [])
    return (isinstance(properties, dict) and isinstance(properties.get('question'), dict)
            and properties['question'].get('type') == 'string' and isinstance(required, list)
            and all(key == 'question' for key in required))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class McpClient:
    def __init__(self, url, token, timeout=10):
        self.url, self.token, self.timeout = base_url(url) + '/mcp', token, timeout
        # Direct access is deliberate: Docker/local hosts must not go through a proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def rpc(self, method, params=None, notification=False, deadline=None):
        request_id = uuid.uuid4().hex
        payload = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if not notification:
            payload['id'] = request_id
        timeout = min(self.timeout, deadline - time.monotonic()) if deadline else self.timeout
        if timeout <= 0:
            raise McpError('MCP 请求超时')
        expires = time.monotonic() + timeout
        request = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers={
            'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json',
            'Accept': 'application/json', 'MCP-Protocol-Version': PROTOCOL})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                if notification and response.status in (200, 202, 204):
                    return None
                chunks, size = [], 0
                socket = response.fp.raw._sock
                while True:
                    if response.isclosed():
                        break
                    remaining = expires - time.monotonic()
                    if remaining <= 0:
                        raise McpError('MCP 请求超时')
                    socket.settimeout(remaining)
                    chunk = response.read1(min(65536, 1048577 - size))
                    if not chunk:
                        break
                    chunks.append(chunk); size += len(chunk)
                    if size > 1048576:
                        raise McpError('MCP 响应过大')
                raw = b''.join(chunks)
                result = json.loads(raw)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise McpError('MCP 认证失败' if exc.code in (401, 403) else 'MCP HTTP 请求失败') from None
        except (OSError, urllib.error.URLError, http.client.HTTPException):
            raise McpError('MCP 网络不可用或请求超时') from None
        except (ValueError, UnicodeError, RecursionError):
            raise McpError('MCP 响应不是有效 JSON') from None
        if (not isinstance(result, dict) or result.get('jsonrpc') != '2.0' or result.get('id') != request_id
                or 'error' in result or not isinstance(result.get('result'), dict)):
            raise McpError('MCP 协议错误或远端拒绝请求')
        return result['result']

    def discover(self):
        deadline = time.monotonic() + self.timeout
        result = self.rpc('initialize', {'protocolVersion': PROTOCOL, 'capabilities': {},
                                        'clientInfo': {'name': 'CampusClaw', 'version': '0.6.0'}}, deadline=deadline)
        capabilities = result.get('capabilities')
        if (result.get('protocolVersion') != PROTOCOL or not isinstance(capabilities, dict)
                or not isinstance(capabilities.get('tools'), dict)):
            raise McpError('MCP 协议版本或工具能力不兼容')
        self.rpc('notifications/initialized', notification=True, deadline=deadline)
        tools, cursor, seen = [], None, set()
        for _ in range(10):
            result = self.rpc('tools/list', {'cursor': cursor} if cursor else {}, deadline=deadline)
            page = result.get('tools')
            if not isinstance(page, list) or len(tools) + len(page) > 200:
                raise McpError('MCP 工具清单非法或过大')
            for tool in page:
                if (not isinstance(tool, dict) or not isinstance(tool.get('name'), str)
                        or not TOOL_NAME.fullmatch(tool['name']) or tool['name'] in seen
                        or not isinstance(tool.get('inputSchema'), dict)
                        or tool['inputSchema'].get('type') != 'object'
                        or not isinstance(tool['inputSchema'].get('properties', {}), dict)
                        or not isinstance(tool['inputSchema'].get('required', []), list)
                        or any(not isinstance(key, str) for key in tool['inputSchema'].get('required', []))
                        or not isinstance(tool.get('description', ''), str)):
                    raise McpError('MCP 工具名称或 schema 非法')
                seen.add(tool['name'])
                tools.append({'name': tool['name'], 'description': tool.get('description', '')[:2000],
                              'inputSchema': tool['inputSchema']})
            cursor = result.get('nextCursor')
            if not cursor:
                return tools
            if not isinstance(cursor, str):
                raise McpError('MCP 工具分页非法')
        raise McpError('MCP 工具分页过多')

    def call(self, name, question):
        result = self.rpc('tools/call', {'name': name, 'arguments': {'question': question}})
        content = result.get('content')
        if result.get('isError') or not isinstance(content, list):
            raise McpError('MCP 工具执行失败')
        texts = [item['text'] for item in content if isinstance(item, dict)
                 and item.get('type') == 'text' and isinstance(item.get('text'), str)]
        value = '\n'.join(texts)
        if not value.strip() or len(value) > 8000:
            raise McpError('MCP 工具文本为空或过长')
        return value
