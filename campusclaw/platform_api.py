"""Annotated platform APIs; existing conversation and agent APIs remain valid."""
from .openapi import endpoint, obj, wrapped, string, ID, BOOL, SKILL, CONVERSATION
from .platform_store import PlatformStore

APP = obj({'key': string(), 'source': string(), 'name': string(), 'description': string(), 'example': string(),
           'icon': string(), 'agent_id': {**ID, 'nullable': True}, 'enabled': BOOL})
TEMPLATE_INPUT = obj({'name': string(64, 1), 'description': string(500), 'content': string(2000, 1)}, ['name', 'content'])
TEMPLATE = obj({**TEMPLATE_INPUT['properties'], 'id': ID, 'key': string(), 'source': string(),
                'variables': {'type': 'array', 'items': string()}})
LIBRARY_SKILL = obj({'key': string(), 'name': string(), 'description': string(), 'content': string(8000),
                     'installed_id': {**ID, 'nullable': True}})


class PlatformApi:
    @property
    def platform(self):
        return PlatformStore(self.store)

    @endpoint('GET', '/api/apps', '内置应用与本班自定义应用', response=wrapped('apps', APP, True))
    def apps_list(self):
        self._json(200, {'apps': self.platform.applications()})

    @endpoint('POST', '/api/apps/{key}/launch', '一键启动内置应用并创建本人会话', body=obj({}),
              response=wrapped('conversation', CONVERSATION), status=201, errors=(400, 404, 409))
    def apps_launch(self, key):
        self._json(201, {'conversation': self.platform.launch(key, self._read_payload())})

    @endpoint('GET', '/api/skill-library', '教师预览内置技能及班内安装状态',
              response=wrapped('skills', LIBRARY_SKILL, True), errors=(403,))
    def skill_library(self):
        self._json(200, {'skills': self.platform.library()})

    @endpoint('POST', '/api/skills/install', '教师安装内置技能；重复安装返回现有副本',
              body=obj({'builtin_key': string()}, ['builtin_key']), response=wrapped('skill', SKILL), errors=(400, 403, 404, 409))
    def skills_install(self):
        self._json(200, {'skill': self.platform.install(self._read_payload())})

    @endpoint('POST', '/api/skills/import', '教师上传 UTF-8 .md/.txt 技能（32 KiB / 8000 字）',
              body=obj({'filename': string(200, 1), 'content': string(8000, 1)}, ['filename', 'content']),
              response=wrapped('skill', SKILL), status=201, errors=(400, 403, 413))
    def skills_import(self):
        self._json(201, {'skill': self.platform.upload(self._read_payload())})

    @endpoint('GET', '/api/prompt-templates', '教师读取内置及本班提示词模板',
              response=wrapped('templates', TEMPLATE, True), errors=(403,))
    def templates_list(self):
        self._json(200, {'templates': self.platform.templates()})

    @endpoint('POST', '/api/prompt-templates', '教师创建本班提示词模板', body=TEMPLATE_INPUT,
              response=wrapped('template', TEMPLATE), status=201, errors=(400, 403, 413))
    def templates_create(self):
        self._json(201, {'template': self.platform.save_template(self._read_payload())})

    @endpoint('GET', '/api/prompt-templates/{id}', '教师读取本班自定义模板',
              response=wrapped('template', TEMPLATE), errors=(403, 404))
    def templates_get(self, id):
        self._json(200, {'template': self.platform.template(id)})

    @endpoint('PUT', '/api/prompt-templates/{id}', '教师修改本班模板，不追溯改变已应用角色',
              body=obj(TEMPLATE_INPUT['properties']), response=wrapped('template', TEMPLATE), errors=(400, 403, 404, 413))
    def templates_update(self, id):
        self._json(200, {'template': self.platform.save_template(self._read_payload(), id)})

    @endpoint('DELETE', '/api/prompt-templates/{id}', '教师删除本班模板，保留已应用角色快照',
              response=obj({'deleted': ID}), errors=(403, 404))
    def templates_delete(self, id):
        self.platform.delete_template(id)
        self._json(200, {'deleted': id})

    @endpoint('POST', '/api/prompt-templates/render', '教师预览模板；仅文本替换，无表达式执行',
              body=obj({'source': {'type': 'string', 'enum': ['builtin', 'custom']}, 'key': string(), 'id': ID,
                        'variables': {'type': 'object', 'additionalProperties': string(300, 1)}}, ['source', 'variables']),
              response=obj({'prompt': string(2000)}), errors=(400, 403, 404, 413))
    def templates_render(self):
        self._json(200, {'prompt': self.platform.preview(self._read_payload())})
