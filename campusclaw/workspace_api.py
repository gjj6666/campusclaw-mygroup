"""Owner library and teacher administration routes."""
import json

from .library import Library
from .tutor import teacher, not_found
from .index_policy import current, normalize, preview, public_policy
from .openapi import endpoint, obj, wrapped, string, ID, BOOL, MATERIAL

PERSONAL = obj({**MATERIAL['properties'], 'owner_id': ID, 'origin_kind': string(), 'created_at': string()})
POLICY = obj({'mode': {'type': 'string', 'enum': ['auto', 'custom']}, 'size': {'type': 'integer', 'minimum': 100, 'maximum': 2000},
              'ratio': {'type': 'integer', 'minimum': 0, 'maximum': 40},
              'separator': {'type': 'string', 'enum': ['paragraph', 'newline', 'sentence']}, 'trim': BOOL})
STATE = obj({'policy': POLICY, 'revision': {'type': 'integer'}})
PERSONAL_INPUT = obj({'filename': string(200, 1), 'content': string(12000, 1), 'subject': string(64, 1),
                     'source': obj({'kind': {'type': 'string', 'enum': ['shared', 'attachment']}, 'id': ID, 'conversation_id': ID}, ['kind', 'id'])})


class WorkspaceApi:
    @property
    def library(self):
        return Library(self.store)

    @endpoint('GET', '/api/me', '当前鉴权身份与班级名称', response=obj({'user': {'type': 'object'}}))
    def identity_get(self):
        user = {k: self.store.user[k] for k in ('id', 'username', 'role', 'class_id')}
        user['class_name'] = self.conn.execute('SELECT name FROM classes WHERE id=?', (user['class_id'],)).fetchone()[0]
        self._json(200, {'user': user})

    @endpoint('GET', '/api/library/materials', '本班资料分类浏览（不含任何个人资料）', response=wrapped('materials', MATERIAL, True))
    def library_list(self):
        self._json(200, {'materials': self.library.materials()})

    @endpoint('GET', '/api/library/materials/{id}', '本班共享资料原文；越权和缺失统一404', response=wrapped('material', MATERIAL), errors=(404,))
    def library_get(self, id):
        self._json(200, {'material': self.library.shared(id)})

    @endpoint('GET', '/api/personal-materials', '本人本班可跨会话复用的个人资料', response=wrapped('materials', PERSONAL, True))
    def personal_list(self):
        self._json(200, {'materials': self.library.personals()})

    @endpoint('GET', '/api/personal-materials/{id}', '读取本人个人资料原文', response=wrapped('material', PERSONAL), errors=(404,))
    def personal_get(self, id):
        self._json(200, {'material': self.library.personal(id)})

    @endpoint('POST', '/api/personal-materials', '上传个人文本，或从本班共享/本人原会话资料复制；同源同内容幂等',
              body=PERSONAL_INPUT, response=wrapped('material', PERSONAL), status=201, errors=(400, 404, 413))
    def personal_create(self):
        self._json(201, {'material': self.library.save(self._read_payload())})

    @endpoint('GET', '/api/admin/students', '教师读取本班学生只读名单（不含私人内容）',
              response=wrapped('students', obj({'id': ID, 'username': string()}), True), errors=(403,))
    def admin_students(self):
        teacher(self.store.user)
        self._json(200, {'students': [dict(r) for r in self.conn.execute("SELECT id,username FROM users WHERE class_id=? AND role='student' ORDER BY id", (self.store.class_id,))]})

    def _policy(self):
        teacher(self.store.user)
        value = current(self.conn, self.store.class_id, self.app.config)
        return dict(policy=public_policy(value['policy']), revision=value['revision'])

    @endpoint('GET', '/api/admin/index-policy', '教师读取本班分段策略和部署默认值', response=STATE, errors=(403,))
    def policy_get(self):
        self._json(200, self._policy())

    @endpoint('PUT', '/api/admin/index-policy', '教师保存本班策略；不自动重建旧材料', body=POLICY, response=STATE, errors=(400, 403))
    def policy_save(self):
        teacher(self.store.user)
        data = self._read_payload()
        normalize(data, self.app.config)
        with self.conn:
            self.conn.execute('INSERT INTO class_index_policies(class_id,policy,revision) VALUES(?,?,1) '
                'ON CONFLICT(class_id) DO UPDATE SET policy=excluded.policy,revision=revision+1',
                (self.store.class_id, json.dumps(data, sort_keys=True)))
        self._json(200, self._policy())

    @endpoint('POST', '/api/admin/index-policy/preview', '教师预览分段；仅返回前20段与总数，不写入索引',
              body=obj({'content': string(), 'material_id': ID, 'policy': POLICY}),
              response=obj({'total': {'type': 'integer'}, 'chunks': {'type': 'array', 'items': {'type': 'object'}}, 'has_more': BOOL}), errors=(400, 403, 404, 413))
    def policy_preview(self):
        teacher(self.store.user)
        data = self._read_payload()
        content = self.library.shared(data['material_id'])['content'] if 'material_id' in data else data.get('content')
        policy = normalize(data['policy'], self.app.config) if 'policy' in data else current(self.conn, self.store.class_id, self.app.config)['policy']
        self._json(200, preview(content, policy))

    @endpoint('GET', '/api/admin/materials', '教师本班资料、已应用策略、索引状态和重建提示',
              response=wrapped('materials', {'type': 'object'}, True), errors=(403,))
    def admin_materials(self):
        teacher(self.store.user)
        policy = current(self.conn, self.store.class_id, self.app.config)['policy']
        result = self.library.materials()
        for item in result:
            state = self.conn.execute('SELECT * FROM material_index_states WHERE material_id=?', (item['id'],)).fetchone()
            applied = json.loads(state['policy']) if state else None
            item.update(applied_policy=public_policy(applied) if applied else None,
                        needs_reindex=not state or applied != policy or state['embedding_signature'] != self.rag.signature,
                        last_error=state['last_error'] if state else '')
        self._json(200, {'materials': result})

    @endpoint('POST', '/api/admin/materials/{id}/reindex', '教师按当前策略重建指定本班资料；返回真实索引状态',
              response=obj({'material_id': ID, 'index_status': {'type': 'string', 'enum': ['ready', 'failed']}}), errors=(403, 404, 409, 503))
    def material_reindex(self, id):
        teacher(self.store.user)
        self.library.shared(id)
        status = self.rag.index_material(id, force=True)
        self._json(200, {'material_id': id, 'index_status': status})
