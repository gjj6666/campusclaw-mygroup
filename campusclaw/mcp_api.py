"""Teacher-only MCP management endpoints and OpenAPI annotations."""
from .mcp_store import McpStore
from .openapi import endpoint, obj, wrapped, string, ID, BOOL

SERVER = obj({'id': ID, 'name': string(64, 1), 'base_url': string(2000, 1),
              'has_token': BOOL, 'status': {'type': 'string', 'enum': ['connected', 'disconnected']},
              'last_error': string(), 'created_at': string()})
TOOL = obj({'name': string(), 'description': string(), 'inputSchema': {'type': 'object'},
            'reference': string(), 'bindable': BOOL})
AUDIT = obj({'id': ID, 'class_id': ID, 'user_id': ID, 'username': string(), 'conversation_id': ID,
             'tool_ref': string(), 'status': {'type': 'string', 'enum': ['ok', 'error', 'denied']},
             'detail': string(), 'created_at': string()})


class McpApi:
    @endpoint('PUT', '/api/mcp/servers/{id}', '教师编辑Base URL/令牌；空令牌保留，变更后断开并清缓存',
              body=obj({'base_url': string(2000, 1), 'auth_token': {**string(4096), 'writeOnly': True, 'format': 'password'}}),
              response=wrapped('server', SERVER), errors=(400, 403, 404))
    def mcp_update(self, id):
        self._json(200, {'server': self.mcp.update(id, self._read_payload())})

    @endpoint('DELETE', '/api/mcp/servers/{id}', '教师移除服务器与发现缓存，保留既有审计',
              response=obj({'deleted': ID}), errors=(403, 404))
    def mcp_remove(self, id):
        self.mcp.remove(id)
        self._json(200, {'deleted': id})

    @property
    def mcp(self):
        return McpStore(self.conn, self.store.user)

    @endpoint('POST', '/api/mcp/servers', '教师登记本班 MCP；令牌只写不返回', status=201,
              body=obj({'name': string(64, 1), 'base_url': string(2000, 1),
                        'auth_token': {**string(4096, 1), 'writeOnly': True, 'format': 'password'}},
                       ['name', 'base_url', 'auth_token']), response=wrapped('server', SERVER), errors=(400, 403, 413))
    def mcp_register(self):
        self._json(201, {'server': self.mcp.register(self._read_payload())})

    @endpoint('GET', '/api/mcp/servers', '教师读取本班 MCP 服务器（脱敏）',
              response=wrapped('servers', SERVER, True), errors=(403,))
    def mcp_servers(self):
        self._json(200, {'servers': self.mcp.servers()})

    @endpoint('POST', '/api/mcp/servers/{id}/connect', '教师握手并发现工具；失败断开且清缓存',
              response=wrapped('server', SERVER), errors=(403, 404, 409, 502))
    def mcp_connect(self, id):
        self._json(200, {'server': self.mcp.connect(id)})

    @endpoint('POST', '/api/mcp/servers/{id}/disconnect', '教师断开并清空发现缓存',
              response=wrapped('server', SERVER), errors=(403, 404))
    def mcp_disconnect(self, id):
        self._json(200, {'server': self.mcp.disconnect(id)})

    @endpoint('GET', '/api/mcp/servers/{id}/tools', '教师读取本班已发现工具及技能引用',
              response=wrapped('tools', TOOL, True), errors=(403, 404))
    def mcp_tools(self, id):
        self._json(200, {'tools': self.mcp.tools(id)})

    @endpoint('GET', '/api/mcp/audits', '教师查询本班最近 200 条 MCP 调用审计',
              response=wrapped('audits', AUDIT, True), errors=(403,))
    def mcp_audits(self):
        self._json(200, {'audits': self.mcp.audits()})
