import json
import unittest
from types import SimpleNamespace

from campusclaw.attachments import Attachments
from campusclaw.db import connect, initialize
from campusclaw.orchestration import prepare, validate_answer
from campusclaw.skills import GUIDANCE_EXAMPLE
from campusclaw.tutor import TutorStore, ApiError


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(':memory:'); self.addCleanup(self.conn.close); initialize(self.conn)
        self.conn.executescript("INSERT INTO classes VALUES(1,'A'),(2,'B'); "
            "INSERT INTO users VALUES(1,'teacher','hash','teacher',1),(2,'student','hash','student',1),"
            "(3,'peer','hash','student',1),(4,'other','hash','student',2);")
        self.teacher = TutorStore(self.conn, dict(id=1, class_id=1, role='teacher'))
        self.student = TutorStore(self.conn, dict(id=2, class_id=1, role='student'))
        self.skill = self.teacher.save_skill({'content': GUIDANCE_EXAMPLE})
        self.agent = self.teacher.save_agent({'name': 'test', 'skill_ids': [self.skill['id']], 'subject': '数学'})
        self.conv = self.student.create_conversation(self.agent['id'])['id']
        self.files = Attachments(self.student)

    def upload(self, kind='material', content='私人资料：三角形内角和为180度。'):
        return self.files.upload(self.conv, dict(kind=kind, filename='lesson.md', content=content))

    def test_private_uploads_and_validation(self):
        item = self.upload()
        self.assertEqual(self.files.list(self.conv)[0]['id'], item['id'])
        for kind, filename, content in [('bad', 'a.md', 'text'), ('material', 'a.pdf', 'text'),
            ('material', '../a.md', 'text'), ('material', 'a.md', ''), ('material', 'a.md', '\ud800'),
            ('material', 'a.md', 'a' * 12001), ('material', 'a.md', '中' * 11000),
            ('skill', 'a.md', 'invalid'), ('skill', 'a.md', GUIDANCE_EXAMPLE.replace('启用：是', '启用：否'))]:
            with self.subTest(filename=filename, kind=kind, size=len(content)), self.assertRaises(ValueError):
                self.files.upload(self.conv, dict(kind=kind, filename=filename, content=content))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM materials').fetchone()[0], 0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM skills').fetchone()[0], 1)
        teacher_conv = self.teacher.create_conversation(self.agent['id'])['id']
        self.assertEqual(Attachments(self.teacher).upload(teacher_conv, dict(kind='skill', filename='s.txt', content=GUIDANCE_EXAMPLE))['kind'], 'skill')

    def test_isolation_and_limits_before_dependencies(self):
        item = self.upload()
        for user in [dict(id=1, class_id=1, role='teacher'), dict(id=3, class_id=1, role='student'), dict(id=4, class_id=2, role='student')]:
            with self.assertRaises(ApiError) as exc: Attachments(TutorStore(self.conn, user)).get(self.conv, item['id'])
            self.assertEqual(exc.exception.status, 404)
        other_conv = self.student.create_conversation(self.agent['id'])['id']
        with self.assertRaises(ApiError): self.files.get(other_conv, item['id'])
        ref = dict(source='upload', id=item['id'])
        for context in ({'materials': [ref, ref]}, {'materials': [ref] * 4}, {'skill': ref},
                        {'materials': 'bad'}, {'skill': {'source': 'upload', 'id': True}}, {'unknown': []}):
            with self.assertRaises(ValueError): self.files.resolve(self.conv, context)
        a = self.upload(content='a' * 10000); b = self.upload(content='b' * 10000)
        with self.assertRaises(ValueError): self.files.resolve(self.conv, {'materials': [dict(source='upload', id=i['id']) for i in (a, b)]})
        disabled = self.teacher.save_skill({'content': GUIDANCE_EXAMPLE.replace('启用：是', '启用：否')}, self.skill['id'])
        with self.assertRaises(ValueError): self.files.resolve(self.conv, {'skill': dict(source='shared', id=disabled['id'])})

    def test_user_level_skill_sources_snapshot_and_default_compatibility(self):
        private = self.upload('skill', GUIDANCE_EXAMPLE.replace('你是解题引导老师。', 'PRIVATE_SKILL_MARKER'))
        material = self.upload()
        calls = []
        def search(*args, **kwargs): calls.append(kwargs); return []
        rag = SimpleNamespace(search=search)
        context = dict(skill=dict(source='upload', id=private['id']), materials=[dict(source='upload', id=material['id'])])
        selected = self.files.resolve(self.conv, context)
        _, messages, sources, skill = prepare(self.student, rag, self.conv, '任意一个问题', resolved=selected)
        self.assertNotIn('PRIVATE_SKILL_MARKER', messages[0]['content'])
        self.assertIn('PRIVATE_SKILL_MARKER', messages[-1]['content'])
        self.assertEqual(calls[-1]['material_ids'], [])
        self.assertEqual(sources[0]['citation'], 'S1'); self.assertEqual(sources[0]['kind'], 'attachment')
        validate_answer('180度[S1]', sources)
        turn, _ = self.student.start_turn(self.conv, '问题', sources, selected['snapshot'])
        self.student.finish_turn(turn, '180度[S1]', True)
        self.assertEqual(self.student.messages(self.conv)[0]['context']['skill']['source'], 'upload')
        _, messages, sources, skill = prepare(self.student, rag, self.conv, '解题问题', context={'skill': None, 'materials': []})
        self.assertIsNone(skill); self.assertEqual(sources, [])
        _, messages, sources, skill = prepare(self.student, rag, self.conv, '解题问题')
        self.assertEqual(skill['id'], self.skill['id']); self.assertIn('技能：', messages[0]['content'])

    def test_additive_migration_retains_old_messages(self):
        self.conn.execute('ALTER TABLE messages DROP COLUMN context')
        self.conn.execute("INSERT INTO messages(conversation_id,turn_id,role,content,status) VALUES(?,'old','user','旧问题','completed')", (self.conv,))
        self.conn.commit(); initialize(self.conn); initialize(self.conn)
        self.assertEqual(self.student.messages(self.conv)[0]['context'], {})
        self.assertEqual(self.student.messages(self.conv)[0]['content'], '旧问题')
        self.assertEqual(self.teacher.get('agents', self.agent['id'])['skill_ids'], [self.skill['id']])
        self.assertEqual(self.conn.execute('PRAGMA foreign_key_check').fetchall(), [])
