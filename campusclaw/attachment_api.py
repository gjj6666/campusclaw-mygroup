"""Authenticated per-conversation context endpoints for both roles."""
from .attachments import Attachments
from .openapi import endpoint, obj, wrapped, string, ID

REF = obj({'source': {'type': 'string', 'enum': ['shared', 'upload']}, 'id': ID}, ['source', 'id'])
MATERIAL_REF = obj({'source': {'type': 'string', 'enum': ['shared', 'upload', 'personal']}, 'id': ID}, ['source', 'id'])
CONTEXT = obj({'skill': {'allOf': [REF], 'nullable': True},
               'materials': {'type': 'array', 'items': MATERIAL_REF, 'maxItems': 3, 'uniqueItems': True}})
ATTACHMENT = obj({'id': ID, 'conversation_id': ID, 'kind': {'type': 'string', 'enum': ['skill', 'material']},
                  'filename': string(200), 'name': string(), 'content': string(12000), 'created_at': string(),
                  'skill': {'type': 'object'}})


class AttachmentApi:
    @endpoint('GET', '/api/conversations/{id}/context', '本人会话可选共享技能、资料和私有附件',
              response=obj({'skills': {'type': 'array', 'items': {'type': 'object'}},
                            'materials': {'type': 'array', 'items': {'type': 'object'}},
                            'attachments': {'type': 'array', 'items': ATTACHMENT},
                            'personal': {'type': 'array', 'items': {'type': 'object'}},
                            'defaults': {'type': 'array', 'items': ID}}), errors=(404,))
    def context_choices(self, id):
        self._json(200, Attachments(self.store).choices(id))

    @endpoint('GET', '/api/conversations/{id}/attachments', '读取本人当前会话的私有附件',
              response=wrapped('attachments', ATTACHMENT, True), errors=(404,))
    def attachments_list(self, id):
        self._json(200, {'attachments': Attachments(self.store).list(id)})

    @endpoint('POST', '/api/conversations/{id}/attachments', '教师和学生上传本人会话 UTF-8 技能或资料（32 KiB）',
              body=obj({'kind': {'type': 'string', 'enum': ['skill', 'material']},
                        'filename': string(200, 1), 'content': string(12000, 1)}, ['kind', 'filename', 'content']),
              response=wrapped('attachment', ATTACHMENT), status=201, errors=(400, 404, 413))
    def attachments_upload(self, id):
        self._json(201, {'attachment': Attachments(self.store).upload(id, self._read_payload())})

    @endpoint('GET', '/api/conversations/{id}/attachments/{attachment_id}', '预览本人原会话私有附件',
              response=wrapped('attachment', ATTACHMENT), errors=(404,))
    def attachments_get(self, id, attachment_id):
        self._json(200, {'attachment': Attachments(self.store).get(id, attachment_id)})
