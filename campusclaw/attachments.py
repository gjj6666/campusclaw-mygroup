"""Private, immutable conversation context; never writes class shared resources."""
import json
from pathlib import PurePath

from .tutor import not_found, text
from .skills import parse_skill


def migrate(conn):
    conn.executescript('''CREATE TABLE IF NOT EXISTS conversation_attachments (
      id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id),
      user_id INTEGER NOT NULL REFERENCES users(id),
      conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
      kind TEXT NOT NULL CHECK(kind IN ('skill','material')), filename TEXT NOT NULL,
      content TEXT NOT NULL, skill TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
      CREATE INDEX IF NOT EXISTS idx_attachments_conversation ON conversation_attachments(conversation_id);''')
    if 'context' not in {r['name'] for r in conn.execute('PRAGMA table_info(messages)')}:
        conn.execute("ALTER TABLE messages ADD COLUMN context TEXT NOT NULL DEFAULT '{}'")


class Attachments:
    def __init__(self, store):
        self.store, self.conn = store, store.conn

    def get(self, conversation, identity):
        self.store.get('conversations', conversation)
        if type(identity) is not int or not 0 < identity <= 9223372036854775807:
            not_found()
        row = self.conn.execute('SELECT * FROM conversation_attachments WHERE id=? AND conversation_id=? '
                                'AND class_id=? AND user_id=?',
                                (identity, conversation, self.store.class_id, self.store.user['id'])).fetchone()
        if row is None:
            not_found()
        item = dict(row)
        item['skill'] = json.loads(item['skill'])
        item['name'] = item['skill'].get('name', item['filename'])
        return item

    def list(self, conversation):
        self.store.get('conversations', conversation)
        return [self.get(conversation, r[0]) for r in self.conn.execute(
            'SELECT id FROM conversation_attachments WHERE conversation_id=? ORDER BY id DESC', (conversation,))]

    def upload(self, conversation, data):
        self.store.get('conversations', conversation)
        kind = data.get('kind')
        if kind not in ('skill', 'material'):
            raise ValueError('kind 必须为 skill 或 material')
        filename = text(data.get('filename'), '文件名', 200, 1)
        if PurePath(filename).suffix.lower() not in ('.md', '.txt') or '/' in filename or '\\' in filename:
            raise ValueError('只支持 UTF-8 .md/.txt 文件名')
        content = data.get('content')
        if not isinstance(content, str) or not content.strip():
            raise ValueError('文件内容不能为空')
        try:
            size = len(content.encode('utf-8'))
        except UnicodeError:
            raise ValueError('文件必须为合法 UTF-8 文本') from None
        if size > 32768 or '\x00' in content:
            raise ValueError('文件须为纯文本，最多 32 KiB')
        if len(content) > (8000 if kind == 'skill' else 12000):
            raise ValueError('技能最多8000字，资料最多12000字')
        parsed = parse_skill(content) if kind == 'skill' else {}
        if parsed and not parsed['enabled']:
            raise ValueError('请将上传技能的启用字段设置为是')
        from .mcp_store import McpStore, _state_lock
        with _state_lock, self.conn:
            if parsed.get('tool', '') not in ('', 'knowledge_search'):
                McpStore(self.conn, self.store.user).resolve(parsed['tool'])
            identity = self.conn.execute('INSERT INTO conversation_attachments '
                '(class_id,user_id,conversation_id,kind,filename,content,skill) VALUES(?,?,?,?,?,?,?)',
                (self.store.class_id, self.store.user['id'], conversation, kind, filename, content,
                 json.dumps(parsed, ensure_ascii=False))).lastrowid
        return self.get(conversation, identity)

    def choices(self, conversation):
        from .library import Library
        conv = self.store.get('conversations', conversation)
        shared_skills = [dict(id=r['id'], source='shared', name=r['name'], content=r['content']) for r in
                         self.conn.execute('SELECT * FROM skills WHERE class_id=? AND enabled=1', (self.store.class_id,))]
        shared_materials = [dict(id=r['id'], source='shared', name=r['title']) for r in self.conn.execute(
            "SELECT m.* FROM materials m WHERE m.class_id=? AND m.status='available' AND EXISTS "
            "(SELECT 1 FROM knowledge_chunks k WHERE k.material_id=m.id AND k.index_status='ready')", (self.store.class_id,))]
        return dict(skills=shared_skills, materials=shared_materials, attachments=self.list(conversation),
                    personal=Library(self.store).personals(),
                    defaults=self.store.get('agents', conv['agent_id'])['material_ids'])

    def resolve(self, conversation, context):
        self.store.get('conversations', conversation)
        if context is None:
            context = {}
        if not isinstance(context, dict) or set(context) - {'skill', 'materials'}:
            raise ValueError('context 仅支持 skill 和 materials')
        result = {'snapshot': {}, 'uploads': []}

        def reference(ref, kind):
            if not isinstance(ref, dict) or set(ref) != {'source', 'id'} or ref['source'] not in ('shared', 'upload', 'personal'):
                raise ValueError('上下文引用须包含 source(shared/upload/personal) 与 id')
            identity = ref['id']
            if type(identity) is not int or not 0 < identity <= 9223372036854775807:
                raise ValueError('上下文 id 必须为正整数')
            if ref['source'] == 'personal':
                if kind != 'material':
                    raise ValueError('personal 来源仅支持资料')
                from .library import Library
                value = {**Library(self.store).personal(identity), 'origin': 'personal'}
            elif ref['source'] == 'upload':
                item = self.get(conversation, identity)
                if item['kind'] != kind:
                    raise ValueError('附件类型不匹配')
                value = {**item['skill'], 'id': identity} if kind == 'skill' else item
            elif kind == 'skill':
                value = self.store.get('skills', identity)
                if not value['enabled']:
                    raise ValueError('技能已停用')
            else:
                row = self.conn.execute('SELECT * FROM materials WHERE id=? AND class_id=?',
                                        (identity, self.store.class_id)).fetchone()
                if row is None:
                    not_found()
                value = dict(row)
                if value['status'] != 'available' or not self.conn.execute(
                    "SELECT 1 FROM knowledge_chunks WHERE material_id=? AND index_status='ready'", (identity,)).fetchone():
                    raise ValueError('资料尚未就绪')
            snap = {**ref, 'name': value.get('name', value.get('title', value.get('filename', '')))}
            return value, snap

        if 'skill' in context:
            if context['skill'] is None:
                result.update(skill=None, private_skill=False)
                result['snapshot']['skill'] = None
            else:
                value, snap = reference(context['skill'], 'skill')
                result.update(skill=value, private_skill=context['skill']['source'] == 'upload')
                result['snapshot']['skill'] = snap
        if 'materials' in context:
            refs = context['materials']
            if not isinstance(refs, list) or len(refs) > 3:
                raise ValueError('每轮最多选择三份资料')
            ids, snapshots, seen, total = [], [], set(), 0
            for ref in refs:
                value, snap = reference(ref, 'material')
                key = (ref['source'], ref['id'])
                if key in seen:
                    raise ValueError('资料不可重复')
                seen.add(key)
                snapshots.append(snap)
                if ref['source'] in ('upload', 'personal'):
                    total += len(value['content'])
                    result['uploads'].append(value)
                else:
                    ids.append(value['id'])
            if total > 18000:
                raise ValueError('本轮个人与会话资料合计最多18000字')
            result['material_ids'] = ids
            result['snapshot']['materials'] = snapshots
        return result
