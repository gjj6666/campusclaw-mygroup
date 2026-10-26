"""Class-scoped server registry, discovered tools, execution and audit."""
import json
import sqlite3
import threading
import uuid

from .mcp_client import McpClient, McpError, REFERENCE, SERVER_NAME, base_url, supports_question
from .tutor import ApiError, teacher, text, not_found

# State changes and call admission are serialized, network I/O is outside the lock.
_state_lock = threading.RLock()


class McpStore:
    def __init__(self, conn, user):
        self.conn, self.user, self.class_id = conn, user, user['class_id']

    def _get(self, identity):
        row = self.conn.execute('SELECT * FROM mcp_servers WHERE id=? AND class_id=?',
                                (identity, self.class_id)).fetchone()
        if row is None:
            not_found()
        return dict(row)

    @staticmethod
    def public(row):
        return {**{k: row[k] for k in ('id', 'name', 'base_url', 'status', 'last_error', 'created_at')},
                'has_token': bool(row['auth_token'])}

    def register(self, data):
        teacher(self.user)
        name = text(data.get('name'), '服务器名称', 64, 1)
        if not SERVER_NAME.fullmatch(name):
            raise ValueError('服务器名称必须以小写字母开头，只含小写字母、数字、下划线或连字符')
        url = base_url(data.get('base_url'))
        token = text(data.get('auth_token'), 'Bearer 令牌', 4096, 1)
        if not token.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in token):
            raise ValueError('Bearer 令牌必须为无空白的可打印 ASCII 字符')
        try:
            with _state_lock, self.conn:
                identity = self.conn.execute('INSERT INTO mcp_servers(class_id,name,base_url,auth_token,state_nonce) VALUES(?,?,?,?,?)',
                                             (self.class_id, name, url, token, uuid.uuid4().hex)).lastrowid
        except sqlite3.IntegrityError:
            raise ValueError('本班服务器名称已存在') from None
        return self.public(self._get(identity))

    def update(self, identity, data):
        teacher(self.user)
        with _state_lock, self.conn:
            old = self._get(identity)
            if set(data) - {'base_url', 'auth_token'}:
                raise ValueError('仅可编辑 Base URL 和令牌，服务器名称不可修改')
            url = base_url(data.get('base_url', old['base_url']))
            raw = data.get('auth_token', '')
            if not isinstance(raw, str):
                raise ValueError('令牌须为字符串')
            token = raw or old['auth_token']
            if not token.isascii() or len(token) > 4096 or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in token):
                raise ValueError('Bearer 令牌必须为无空白的可打印 ASCII 字符')
            if (url, token) != (old['base_url'], old['auth_token']):
                self.conn.execute("UPDATE mcp_servers SET base_url=?,auth_token=?,status='disconnected',version=version+1,"
                                  "state_nonce=?,last_error='' WHERE id=?", (url, token, uuid.uuid4().hex, identity))
                self.conn.execute('DELETE FROM mcp_tools WHERE server_id=?', (identity,))
        return self.public(self._get(identity))

    def remove(self, identity):
        teacher(self.user)
        with _state_lock, self.conn:
            self._get(identity)
            self.conn.execute('DELETE FROM mcp_servers WHERE id=?', (identity,))

    def servers(self):
        teacher(self.user)
        return [self.public(dict(row)) for row in self.conn.execute(
            'SELECT * FROM mcp_servers WHERE class_id=? ORDER BY id', (self.class_id,))]

    def tools(self, identity):
        teacher(self.user)
        server = self._get(identity)
        if server['status'] != 'connected':
            return []
        return [{'name': row['name'], 'description': row['description'], 'inputSchema': json.loads(row['input_schema']),
                 'reference': row['name'] + '@' + server['name'],
                 'bindable': supports_question(json.loads(row['input_schema']))}
                for row in self.conn.execute('SELECT * FROM mcp_tools WHERE server_id=? ORDER BY name', (identity,))]

    def disconnect(self, identity):
        teacher(self.user)
        with _state_lock, self.conn:
            self._get(identity)
            self.conn.execute("UPDATE mcp_servers SET status='disconnected',version=version+1,state_nonce=?,last_error='' WHERE id=?", (uuid.uuid4().hex, identity))
            self.conn.execute('DELETE FROM mcp_tools WHERE server_id=?', (identity,))
        return self.public(self._get(identity))

    def connect(self, identity):
        teacher(self.user)
        with _state_lock:
            self.disconnect(identity)
            server = self._get(identity)
        try:
            tools = McpClient(server['base_url'], server['auth_token']).discover()
        except McpError as exc:
            with _state_lock, self.conn:
                self.conn.execute('UPDATE mcp_servers SET last_error=? WHERE id=? AND version=? AND state_nonce=?',
                                  (str(exc), identity, server['version'], server['state_nonce']))
            raise ApiError(502, 'mcp_connection_failed', str(exc)) from None
        with _state_lock, self.conn:
            latest = self.conn.execute('SELECT * FROM mcp_servers WHERE id=? AND class_id=?', (identity, self.class_id)).fetchone()
            if not latest or latest['version'] != server['version'] or latest['state_nonce'] != server['state_nonce']:
                raise ApiError(409, 'mcp_state_changed', '连接状态已改变，请重试')
            self.conn.executemany('INSERT INTO mcp_tools(server_id,name,description,input_schema) VALUES(?,?,?,?)',
                                  [(identity, tool['name'], tool['description'], json.dumps(tool['inputSchema'])) for tool in tools])
            self.conn.execute("UPDATE mcp_servers SET status='connected',last_error='' WHERE id=?", (identity,))
        return self.public(self._get(identity))

    def resolve(self, reference):
        match = REFERENCE.fullmatch(reference)
        if not match:
            raise ValueError('工具引用必须为 工具名@服务器名')
        name, server_name = match.groups()
        row = self.conn.execute('SELECT * FROM mcp_servers WHERE name=? AND class_id=?',
                                (server_name, self.class_id)).fetchone()
        if row is None:
            raise ValueError('本班服务器不存在或不可用')
        server = dict(row)
        if server['status'] != 'connected':
            raise ValueError('MCP 服务器未连接')
        tool = self.conn.execute('SELECT * FROM mcp_tools WHERE server_id=? AND name=?', (server['id'], name)).fetchone()
        if tool is None:
            raise ValueError('MCP 工具未发现，请重新连接服务器')
        if not supports_question(json.loads(tool['input_schema'])):
            raise ValueError('MCP 工具不支持 question 字符串输入契约')
        return server, name

    def invoke(self, reference, question, conversation_id):
        # The conversation owner and class are checked independently of skill routing.
        user_id = self.user.get('id', self.user.get('user_id'))
        if not self.conn.execute('SELECT 1 FROM conversations WHERE id=? AND class_id=? AND owner_id=?',
                                 (conversation_id, self.class_id, user_id)).fetchone():
            not_found()
        result, detail, value = 'denied', '', ''
        try:
            with _state_lock:
                server, name = self.resolve(reference)
            value = McpClient(server['base_url'], server['auth_token']).call(name, question)
            with _state_lock:
                latest = self.conn.execute('SELECT * FROM mcp_servers WHERE id=? AND class_id=?', (server['id'], self.class_id)).fetchone()
                if not latest or latest['state_nonce'] != server['state_nonce'] or latest['version'] != server['version'] or latest['status'] != 'connected':
                    raise ValueError('MCP 连接已失效')
            result = 'ok'
        except ValueError:
            detail, value = 'MCP 工具未获授权、未连接或未发现', ''
        except McpError as exc:
            result, detail, value = 'error', str(exc), ''
        with self.conn:
            self.conn.execute('INSERT INTO mcp_audits(class_id,user_id,conversation_id,tool_ref,status,detail) VALUES(?,?,?,?,?,?)',
                              (self.class_id, user_id, conversation_id, reference, result, detail))
        return {'tool_ref': reference, 'status': result, 'message': detail}, value

    def audits(self):
        teacher(self.user)
        return [dict(row) for row in self.conn.execute(
            'SELECT a.*,u.username FROM mcp_audits a JOIN users u ON u.id=a.user_id AND u.class_id=a.class_id '
            'WHERE a.class_id=? ORDER BY a.id DESC LIMIT 200', (self.class_id,))]
