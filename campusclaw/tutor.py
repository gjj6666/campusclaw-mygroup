"""Class-scoped configuration and durable conversation storage."""
import json
import sqlite3
import uuid

from .skills import parse_skill

DEFAULT_ROLE = '你是耐心的课程助教。用中文清晰回答，帮助学生理解思路。'


class ApiError(Exception):
    def __init__(self, status, code, message=None):
        self.status, self.code, self.message = status, code, message
        super().__init__(message or code)


def not_found():
    raise ApiError(404, 'not_found')


def teacher(user):
    if user['role'] != 'teacher':
        raise ApiError(403, 'forbidden')


def text(value, name, maximum, minimum=0):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(f'{name}必须为{minimum}至{maximum}字')
    return value.strip()


class TutorStore:
    def __init__(self, conn, user):
        self.conn, self.user = conn, {**user, 'id': user.get('id', user.get('user_id'))}
        self.class_id = user['class_id']

    def get(self, table, identity):
        assert table in ('agents', 'skills', 'conversations')
        if type(identity) is not int or not 1 <= identity <= 9223372036854775807:
            not_found()
        sql = f'SELECT * FROM {table} WHERE id=? AND class_id=?'
        args = [identity, self.class_id]
        if table == 'conversations':
            sql += ' AND owner_id=?'
            args.append(self.user['id'])
        row = self.conn.execute(sql, args).fetchone()
        if row is None:
            not_found()
        result = dict(row)
        if table == 'agents':
            for kind in ('skill', 'material'):
                result[kind + '_ids'] = [r[0] for r in self.conn.execute(
                    f'SELECT {kind}_id FROM agent_{kind}s WHERE agent_id=? ORDER BY {kind}_id', (identity,))]
            result['effective_prompt'] = result['prompt'] or DEFAULT_ROLE
        if table in ('agents', 'skills'):
            result['enabled'] = bool(result['enabled'])
        return result

    def list(self, table):
        assert table in ('agents', 'skills', 'conversations')
        if table == 'conversations':
            return [dict(r) for r in self.conn.execute('''SELECT c.*,a.name AS agent_name,
              COALESCE((SELECT substr(content,1,30) FROM messages WHERE conversation_id=c.id AND role='user' ORDER BY id LIMIT 1),'新对话') AS title,
              COALESCE((SELECT MAX(created_at) FROM messages WHERE conversation_id=c.id),c.created_at) AS last_activity
              FROM conversations c JOIN agents a ON a.id=c.agent_id AND a.class_id=c.class_id
              WHERE c.class_id=? AND c.owner_id=? ORDER BY last_activity DESC,c.id DESC''', (self.class_id, self.user['id']))]
        sql = f'SELECT id FROM {table} WHERE class_id=?'
        args = [self.class_id]
        if table == 'conversations':
            sql += ' AND owner_id=?'
            args.append(self.user['id'])
        return [self.get(table, r[0]) for r in self.conn.execute(sql + ' ORDER BY id DESC', args)]

    def save_agent(self, data, identity=None):
        teacher(self.user)
        previous = self.get('agents', identity) if identity is not None else {}
        values = {**previous, **data}
        name = text(values.get('name'), '名称', 64, 1)
        prompt = text(values.get('prompt', ''), '提示词', 2000)
        subject = text(values.get('subject', '通用'), '学科', 64, 1)
        enabled = values.get('enabled', True)
        if type(enabled) is not bool:
            raise ValueError('enabled必须为布尔值')
        bindings = {}
        for kind in ('skill', 'material'):
            ids = values.get(kind + '_ids', [])
            if not isinstance(ids, list) or any(type(i) is not int or not 1 <= i <= 9223372036854775807 for i in ids):
                raise ValueError(f'{kind}_ids必须为正整数数组')
            bindings[kind] = sorted(set(ids))
        with self.conn:
            for kind, ids in bindings.items():
                for i in ids:
                    extra = " AND status='available'" if kind == 'material' else ''
                    if not self.conn.execute(f'SELECT 1 FROM {kind}s WHERE id=? AND class_id=?' + extra,
                                             (i, self.class_id)).fetchone():
                        not_found()
            if identity is None:
                identity = self.conn.execute('INSERT INTO agents(class_id,name,prompt,subject,enabled) VALUES(?,?,?,?,?)',
                                             (self.class_id, name, prompt, subject, enabled)).lastrowid
            else:
                self.conn.execute('UPDATE agents SET name=?,prompt=?,subject=?,enabled=? WHERE id=? AND class_id=?',
                                  (name, prompt, subject, enabled, identity, self.class_id))
            for kind, ids in bindings.items():
                self.conn.execute(f'DELETE FROM agent_{kind}s WHERE agent_id=?', (identity,))
                self.conn.executemany(f'INSERT INTO agent_{kind}s(agent_id,{kind}_id,class_id) VALUES(?,?,?)',
                                      [(identity, i, self.class_id) for i in ids])
        return self.get('agents', identity)

    def save_skill(self, data, identity=None):
        teacher(self.user)
        if identity is not None:
            self.get('skills', identity)
        parsed = parse_skill(data.get('content'))
        from .mcp_store import McpStore, _state_lock
        columns = ('name', 'conditions', 'enabled', 'tool', 'body', 'content')
        args = [parsed[k] for k in columns]
        try:
            with _state_lock, self.conn:
                if parsed['tool'] not in ('', 'knowledge_search'):
                    McpStore(self.conn, self.user).resolve(parsed['tool'])
                if identity is None:
                    identity = self.conn.execute('INSERT INTO skills(name,conditions,enabled,tool,body,content,class_id) '
                                                 'VALUES(?,?,?,?,?,?,?)', args + [self.class_id]).lastrowid
                else:
                    self.conn.execute('UPDATE skills SET name=?,conditions=?,enabled=?,tool=?,body=?,content=? '
                                      'WHERE id=? AND class_id=?', args + [identity, self.class_id])
        except sqlite3.IntegrityError as exc:
            raise ValueError('本班技能名称已存在') from exc
        return self.get('skills', identity)

    def delete_skill(self, identity):
        teacher(self.user)
        self.get('skills', identity)
        with self.conn:
            self.conn.execute('DELETE FROM skills WHERE id=? AND class_id=?', (identity, self.class_id))

    def create_conversation(self, agent_id):
        if type(agent_id) is not int:
            not_found()
        agent = self.get('agents', agent_id)
        if not agent['enabled']:
            not_found()
        with self.conn:
            identity = self.conn.execute('INSERT INTO conversations(owner_id,class_id,agent_id) VALUES(?,?,?)',
                                         (self.user['id'], self.class_id, agent_id)).lastrowid
        return self.get('conversations', identity)

    def messages(self, identity):
        self.get('conversations', identity)
        result = []
        for row in self.conn.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY id', (identity,)):
            item = dict(row)
            item['sources'] = json.loads(item['sources'])
            item['context'] = json.loads(item['context'])
            result.append(item)
        return result

    def history(self, identity):
        self.get('conversations', identity)
        rows = self.conn.execute("SELECT role,content FROM messages WHERE conversation_id=? AND status='completed' "
                                 'ORDER BY id DESC LIMIT 6', (identity,)).fetchall()
        return [{'role': r['role'], 'content': r['content'][:500]} for r in reversed(rows)]

    def start_turn(self, identity, question, sources, context=None):
        turn = uuid.uuid4().hex
        with self.conn:
            self.conn.execute("INSERT INTO messages(conversation_id,turn_id,role,content,status) VALUES(?,?,'user',?,'generating')",
                              (identity, turn, question))
            message = self.conn.execute("INSERT INTO messages(conversation_id,turn_id,role,sources,status) "
                                        "VALUES(?,?,'assistant',?,'generating')",
                                        (identity, turn, json.dumps(sources, ensure_ascii=False))).lastrowid
            self.conn.execute('UPDATE messages SET context=? WHERE turn_id=?',
                              (json.dumps(context or {}, ensure_ascii=False), turn))
        return turn, message

    def finish_turn(self, turn, answer, success):
        with self.conn:
            self.conn.execute("UPDATE messages SET status=? WHERE turn_id=? AND role='user'",
                              ('completed' if success else 'failed', turn))
            self.conn.execute("UPDATE messages SET content=?,status=? WHERE turn_id=? AND role='assistant'",
                              (answer, 'completed' if success else ('partial' if answer else 'failed'), turn))
