import sqlite3
import unittest

from campusclaw.db import connect, initialize
from campusclaw.skills import GUIDANCE_EXAMPLE, parse_skill
from campusclaw.tutor import ApiError, DEFAULT_ROLE, TutorStore


class TutorStorageTests(unittest.TestCase):
    def test_migrates_original_week_four_schema_without_recreating_data(self):
        from campusclaw.db import SCHEMA
        old = connect(':memory:')
        self.addCleanup(old.close)
        old.executescript(SCHEMA)
        old.executescript("INSERT INTO classes VALUES(1,'old'); INSERT INTO users VALUES(1,'old','hash','teacher',1); "
                          "INSERT INTO materials VALUES(1,'old','old.txt',1,1,'available','2026-09-01');")
        initialize(old)
        initialize(old)
        row = dict(old.execute('SELECT * FROM materials').fetchone())
        self.assertEqual(row['created_at'], '2026-09-01')
        self.assertEqual(row['subject'], '通用')
        self.assertEqual(old.execute('SELECT count(*) FROM users').fetchone()[0], 1)

    def setUp(self):
        self.conn = connect(':memory:')
        initialize(self.conn)
        self.conn.executescript("""
        INSERT INTO classes VALUES(1,'A'),(2,'B');
        INSERT INTO users VALUES(1,'teacher','hash','teacher',1),(2,'student','hash','student',1),
          (3,'other','hash','student',2),(4,'peer','hash','student',1),(5,'teacherb','hash','teacher',2);
        INSERT INTO materials(id,title,filename,class_id,teacher_id,status) VALUES(1,'a','a',1,1,'available');
        """)
        self.teacher = TutorStore(self.conn, dict(id=1, class_id=1, role='teacher'))
        self.student = TutorStore(self.conn, dict(id=2, class_id=1, role='student'))
        self.other = TutorStore(self.conn, dict(id=3, class_id=2, role='student'))

    def tearDown(self):
        self.conn.close()

    def test_idempotency_and_cross_class_foreign_keys(self):
        skill = self.teacher.save_skill({'content': GUIDANCE_EXAMPLE})
        agent = self.teacher.save_agent({'name': '助教', 'skill_ids': [skill['id']], 'material_ids': [1]})
        conv = self.student.create_conversation(agent['id'])
        turn, mid = self.student.start_turn(conv['id'], '解题问题', [])
        self.student.finish_turn(turn, '完整回答', True)
        initialize(self.conn)
        initialize(self.conn)
        self.assertEqual(self.student.messages(conv['id'])[1]['content'], '完整回答')
        self.assertEqual(self.conn.execute('SELECT subject FROM materials').fetchone()[0], '通用')
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('INSERT INTO agent_skills VALUES(?,?,?)', (agent['id'], skill['id'], 2))
        self.conn.rollback()
        self.teacher.delete_skill(skill['id'])
        self.assertEqual(self.teacher.get('agents', agent['id'])['skill_ids'], [])

    def test_scope_and_atomic_binding_update(self):
        agent = self.teacher.save_agent({'name': '助教'})
        conv = self.student.create_conversation(agent['id'])
        for user in (self.other, TutorStore(self.conn, dict(id=4, class_id=1, role='student'))):
            self.assertEqual(user.list('conversations'), [])
            with self.assertRaises(ApiError) as err:
                user.get('conversations', conv['id'])
            self.assertEqual((err.exception.status, err.exception.code), (404, 'not_found'))
        with self.assertRaises(ApiError):
            self.teacher.save_agent({'name': 'changed', 'material_ids': [999]}, agent['id'])
        self.assertEqual(self.teacher.get('agents', agent['id'])['name'], '助教')
        self.teacher.save_agent({'enabled': False}, agent['id'])
        with self.assertRaises(ApiError):
            self.student.create_conversation(agent['id'])
        self.assertEqual(self.student.get('conversations', conv['id'])['agent_id'], agent['id'])

    def test_validation_and_permissions(self):
        agent = self.teacher.save_agent({'name': 'x' * 64, 'prompt': ' '})
        self.assertEqual(agent['effective_prompt'], DEFAULT_ROLE)
        for data in ({'name': 'x' * 65}, {'prompt': 'x' * 2001}, {'enabled': 'false'}):
            with self.assertRaises(ValueError):
                self.teacher.save_agent(data, agent['id'])
        with self.assertRaises(ApiError) as err:
            self.student.save_agent({'name': 'bad'})
        self.assertEqual(err.exception.status, 403)
        self.teacher.save_skill({'content': GUIDANCE_EXAMPLE})
        with self.assertRaisesRegex(ValueError, '名称已存在'):
            self.teacher.save_skill({'content': GUIDANCE_EXAMPLE})

    def test_parser_rejects_invalid_files(self):
        self.assertTrue(parse_skill(GUIDANCE_EXAMPLE.replace('：', ':'))['enabled'])
        for content in (GUIDANCE_EXAMPLE.replace('名称：解题引导\n', ''),
                        '名称：重复\n' + GUIDANCE_EXAMPLE,
                        GUIDANCE_EXAMPLE.replace('knowledge_search', 'shell'),
                        GUIDANCE_EXAMPLE.split('\n\n')[0], 'x' * 8001,
                        GUIDANCE_EXAMPLE.replace('启用：是', '启用：true'),
                        GUIDANCE_EXAMPLE.replace('启用：是', '未知：是'),
                        GUIDANCE_EXAMPLE.replace('解题引导', 'x' * 65)):
            with self.assertRaises(ValueError):
                parse_skill(content)

    def test_history_truncates_only_context_and_excludes_failed_turn(self):
        agent = self.teacher.save_agent({'name': '助教'})
        conv = self.student.create_conversation(agent['id'])
        for i in range(5):
            turn, _ = self.student.start_turn(conv['id'], f'问题{i}', [])
            self.student.finish_turn(turn, str(i) * 700, True)
        turn, _ = self.student.start_turn(conv['id'], '失败问题', [])
        self.student.finish_turn(turn, '未完成', False)
        history = self.student.history(conv['id'])
        self.assertEqual(len(history), 6)
        self.assertEqual(history[0]['content'], '问题2')
        self.assertEqual(len(history[-1]['content']), 500)
        self.assertEqual(len(self.student.messages(conv['id'])[-3]['content']), 700)
