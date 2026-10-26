"""Class reading and owner-only immutable personal copies."""
import hashlib
from pathlib import PurePath

from .tutor import not_found, text
from .services import get_authorized_material


def file_text(filename, content, maximum=12000):
    filename = text(filename, '文件名', 200, 1)
    if PurePath(filename).suffix.lower() not in ('.md', '.txt') or '/' in filename or '\\' in filename:
        raise ValueError('只支持 UTF-8 .md/.txt 文件名')
    if not isinstance(content, str) or not content.strip() or len(content) > maximum or '\x00' in content:
        raise ValueError(f'正文须为非空纯文本，最多{maximum}字')
    try:
        if len(content.encode('utf-8')) > 32768:
            raise ValueError('文件最多32 KiB')
    except UnicodeError:
        raise ValueError('文件必须为合法 UTF-8 文本') from None
    return filename, content


class Library:
    def __init__(self, store):
        self.store, self.conn = store, store.conn

    def shared(self, identity):
        if type(identity) is not int or not 0 < identity <= 9223372036854775807:
            not_found()
        item = get_authorized_material(self.conn, material_id=identity, class_id=self.store.class_id)
        if not item:
            not_found()
        return item

    def materials(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT m.id,m.title,m.filename,m.subject,m.created_at,COALESCE(i.status,'unindexed') AS index_status "
            "FROM materials m LEFT JOIN material_index_states i ON i.material_id=m.id "
            "WHERE m.class_id=? AND m.status='available' ORDER BY m.id DESC", (self.store.class_id,))]

    def personal(self, identity):
        if type(identity) is not int or not 0 < identity <= 9223372036854775807:
            not_found()
        row = self.conn.execute('SELECT * FROM personal_materials WHERE id=? AND owner_id=? AND class_id=?',
                                (identity, self.store.user['id'], self.store.class_id)).fetchone()
        if row is None:
            not_found()
        return dict(row)

    def personals(self):
        return [dict(r) for r in self.conn.execute('SELECT * FROM personal_materials WHERE owner_id=? AND class_id=? '
            'ORDER BY id DESC', (self.store.user['id'], self.store.class_id))]

    def save(self, data):
        origin, origin_id, conversation_id = 'upload', None, None
        if 'source' in data:
            if set(data) != {'source'} or not isinstance(data['source'], dict):
                raise ValueError('复制时仅提供 source')
            source = data['source']; origin = source.get('kind'); origin_id = source.get('id')
            if origin == 'shared' and set(source) == {'kind', 'id'}:
                value = self.shared(origin_id)
            elif origin == 'attachment' and set(source) == {'kind', 'id', 'conversation_id'}:
                from .attachments import Attachments
                conversation_id = source['conversation_id']
                value = Attachments(self.store).get(conversation_id, origin_id)
                if value['kind'] != 'material':
                    raise ValueError('个人库仅支持资料，不能保存技能')
            else:
                raise ValueError('source 必须为 shared 或 attachment 来源')
            filename, content = file_text(value['filename'], value['content'])
            subject = value.get('subject', '通用')
        else:
            if set(data) - {'filename', 'content', 'subject'}:
                raise ValueError('不支持额外的个人资料字段')
            filename, content = file_text(data.get('filename'), data.get('content'))
            subject = text(data.get('subject', '通用'), '学科', 64, 1)
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        with self.conn:
            self.conn.execute('INSERT OR IGNORE INTO personal_materials(owner_id,class_id,title,filename,subject,content,'
                'origin_kind,origin_id,origin_conversation_id,content_hash) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (self.store.user['id'], self.store.class_id, filename, filename, subject, content,
                 origin, origin_id, conversation_id, digest))
            if origin == 'upload':
                identity = self.conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            else:
                identity = self.conn.execute('SELECT id FROM personal_materials WHERE owner_id=? AND class_id=? '
                    'AND origin_kind=? AND origin_id=? AND content_hash=?',
                    (self.store.user['id'], self.store.class_id, origin, origin_id, digest)).fetchone()[0]
        return self.personal(identity)
