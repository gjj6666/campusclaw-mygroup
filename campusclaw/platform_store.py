"""Application catalog, prompt snapshots and trusted skill installation."""
import re
import sqlite3

from . import catalog
from .skills import parse_skill
from .tutor import ApiError, teacher, text, not_found

PLACEHOLDER = re.compile(r'\{\{\s*(subject|audience|goal)\s*\}\}')


def variables(content):
    remainder = PLACEHOLDER.sub('', content)
    if '{{' in remainder or '}}' in remainder:
        raise ValueError('模板只支持 {{subject}}、{{audience}}、{{goal}} 占位符，且必须成对')
    return sorted(set(PLACEHOLDER.findall(content)))


def render(content, values):
    needed = variables(content)
    if not isinstance(values, dict) or set(values) != set(needed):
        raise ValueError('变量必须与模板一致，不可缺失或额外提供')
    values = {key: text(value, key, 300, 1) for key, value in values.items()}
    result = PLACEHOLDER.sub(lambda match: values[match[1]], content)
    return text(result, '渲染结果', 2000, 1)


class PlatformStore:
    def __init__(self, tutor):
        self.tutor, self.conn, self.user, self.class_id = tutor, tutor.conn, tutor.user, tutor.class_id

    def applications(self):
        bindings = {row['builtin_key']: row for row in self.conn.execute(
            'SELECT b.builtin_key,a.id,a.enabled,a.name FROM builtin_app_bindings b JOIN agents a '
            'ON a.id=b.agent_id AND a.class_id=b.class_id WHERE b.class_id=?', (self.class_id,))}
        result = []
        for key, item in catalog.apps().items():
            bound = bindings.get(key)
            result.append(dict(key=key, source='builtin', name=bound['name'] if bound else item['name'],
                               description=item['description'], example=item['example'], icon=item['icon'],
                               agent_id=bound['id'] if bound else None, enabled=bool(bound['enabled']) if bound else True))
        mapped = {row['id'] for row in bindings.values()}
        result.extend(dict(source='custom', agent_id=agent['id'], name=agent['name'],
                           description=agent['subject'] + ' · 本班自定义应用', example='', icon='自', enabled=True)
                      for agent in self.tutor.list('agents') if agent['enabled'] and agent['id'] not in mapped)
        return result

    def _install(self, key):
        library = catalog.skills()
        if not isinstance(key, str) or key not in library:
            not_found()
        previous = self.conn.execute('SELECT skill_id FROM builtin_skill_bindings WHERE class_id=? AND builtin_key=?',
                                      (self.class_id, key)).fetchone()
        if previous:
            return previous['skill_id']
        parsed = parse_skill(library[key]['content'])
        if self.conn.execute('SELECT 1 FROM skills WHERE class_id=? AND name=?', (self.class_id, parsed['name'])).fetchone():
            raise ApiError(409, 'skill_name_conflict', '本班已有同名技能，请先改名；不会覆盖原技能')
        columns = ('name', 'conditions', 'enabled', 'tool', 'body', 'content')
        identity = self.conn.execute('INSERT INTO skills(name,conditions,enabled,tool,body,content,class_id) '
                                     'VALUES(?,?,?,?,?,?,?)', [parsed[key] for key in columns] + [self.class_id]).lastrowid
        self.conn.execute('INSERT INTO builtin_skill_bindings(class_id,builtin_key,skill_id) VALUES(?,?,?)',
                          (self.class_id, key, identity))
        return identity

    def install(self, data):
        teacher(self.user)
        with self.conn:
            self.conn.execute('BEGIN IMMEDIATE')
            identity = self._install(data.get('builtin_key'))
        return self.tutor.get('skills', identity)

    def library(self):
        teacher(self.user)
        installed = {row['builtin_key']: row['skill_id'] for row in self.conn.execute(
            'SELECT * FROM builtin_skill_bindings WHERE class_id=?', (self.class_id,))}
        return [dict(key=key, **item, installed_id=installed.get(key)) for key, item in catalog.skills().items()]

    def launch(self, key, data):
        if data:
            raise ValueError('启动内置应用不接受自定义配置，请由教师在配置区修改')
        applications = catalog.apps()
        if key not in applications:
            not_found()
        with self.conn:
            self.conn.execute('BEGIN IMMEDIATE')
            row = self.conn.execute('SELECT agent_id FROM builtin_app_bindings WHERE class_id=? AND builtin_key=?',
                                     (self.class_id, key)).fetchone()
            if row:
                agent_id = row['agent_id']
            else:
                item = applications[key]
                skill_id = self._install(item['skill'])
                prompt = render(catalog.templates()[key]['content'],
                                {'subject': '通用课程', 'audience': '本班学生', 'goal': '理解知识并独立学习'})
                agent_id = self.conn.execute('INSERT INTO agents(class_id,name,prompt,subject,enabled) VALUES(?,?,?,?,1)',
                                             (self.class_id, item['name'], prompt, '通用')).lastrowid
                self.conn.execute('INSERT INTO agent_skills(agent_id,skill_id,class_id) VALUES(?,?,?)',
                                  (agent_id, skill_id, self.class_id))
                self.conn.execute('INSERT INTO builtin_app_bindings(class_id,builtin_key,agent_id) VALUES(?,?,?)',
                                  (self.class_id, key, agent_id))
            agent = self.tutor.get('agents', agent_id)
            if not agent['enabled']:
                not_found()
            identity = self.conn.execute('INSERT INTO conversations(owner_id,class_id,agent_id) VALUES(?,?,?)',
                                         (self.user['id'], self.class_id, agent_id)).lastrowid
        return self.tutor.get('conversations', identity)

    def upload(self, data):
        teacher(self.user)
        filename = text(data.get('filename'), '文件名', 200, 1)
        if '/' in filename or '\\' in filename or not filename.lower().endswith(('.md', '.txt')):
            raise ValueError('技能上传只接受 .md/.txt 文件名，不接受服务器路径')
        content = data.get('content')
        if not isinstance(content, str):
            raise ValueError('技能文件必须为 UTF-8 文本')
        try:
            size = len(content.encode('utf-8'))
        except UnicodeError:
            raise ValueError('技能文件必须为有效 UTF-8 文本') from None
        if size > 32768:
            raise ValueError('技能文件不可超过 32 KiB')
        return self.tutor.save_skill({'content': content.removeprefix('\ufeff')})

    @staticmethod
    def template_item(row):
        return {**dict(row), 'source': 'custom', 'variables': variables(row['content'])}

    def template(self, identity):
        teacher(self.user)
        row = self.conn.execute('SELECT * FROM prompt_templates WHERE id=? AND class_id=?',
                                (identity, self.class_id)).fetchone()
        if row is None:
            not_found()
        return self.template_item(row)

    def templates(self):
        teacher(self.user)
        builtins = [dict(source='builtin', key=key, **item, variables=variables(item['content']))
                    for key, item in catalog.templates().items()]
        return builtins + [self.template_item(row) for row in self.conn.execute(
            'SELECT * FROM prompt_templates WHERE class_id=? ORDER BY id', (self.class_id,))]

    def save_template(self, data, identity=None):
        teacher(self.user)
        previous = self.template(identity) if identity is not None else {}
        data = {**previous, **data}
        name = text(data.get('name'), '模板名称', 64, 1)
        description = text(data.get('description', ''), '模板说明', 500)
        content = text(data.get('content'), '模板正文', 2000, 1)
        variables(content)
        try:
            with self.conn:
                if identity is None:
                    identity = self.conn.execute('INSERT INTO prompt_templates(class_id,name,description,content) VALUES(?,?,?,?)',
                                                 (self.class_id, name, description, content)).lastrowid
                else:
                    self.conn.execute('UPDATE prompt_templates SET name=?,description=?,content=? WHERE id=? AND class_id=?',
                                      (name, description, content, identity, self.class_id))
        except sqlite3.IntegrityError:
            raise ValueError('本班模板名称已存在') from None
        return self.template(identity)

    def delete_template(self, identity):
        self.template(identity)
        with self.conn:
            self.conn.execute('DELETE FROM prompt_templates WHERE id=? AND class_id=?', (identity, self.class_id))

    def preview(self, data):
        teacher(self.user)
        if data.get('source') == 'builtin':
            key = data.get('key')
            if not isinstance(key, str) or key not in catalog.templates():
                not_found()
            content = catalog.templates()[key]['content']
        elif data.get('source') == 'custom':
            identity = data.get('id')
            if type(identity) is not int or not 1 <= identity <= 9223372036854775807:
                not_found()
            content = self.template(identity)['content']
        else:
            raise ValueError('模板来源必须为 builtin 或 custom')
        return render(content, data.get('variables', {}))
