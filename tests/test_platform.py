import tempfile
import threading
import unittest
from pathlib import Path

from campusclaw import catalog
from campusclaw.db import connect, initialize
from campusclaw.platform_store import PlatformStore, render, variables
from campusclaw.skills import GUIDANCE_EXAMPLE, parse_skill
from campusclaw.tutor import TutorStore, ApiError


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(':memory:'); self.addCleanup(self.conn.close); initialize(self.conn)
        self.conn.executescript("INSERT INTO classes VALUES(1,'A'),(2,'B'); "
                               "INSERT INTO users VALUES(1,'teacher','hash','teacher',1),(2,'student','hash','student',1),"
                               "(3,'peer','hash','student',1),(4,'other','hash','teacher',2);")
        self.tutor = TutorStore(self.conn, dict(id=1, class_id=1, role='teacher'))
        self.store = PlatformStore(self.tutor)

    def test_catalog_content_and_read_only_listing(self):
        self.assertEqual(len(self.store.applications()), 3)
        self.assertEqual(len(self.store.templates()), 3)
        self.assertEqual(len(self.store.library()), 3)
        for entry in catalog.skills().values():
            self.assertIn(parse_skill(entry['content'])['tool'], ('', 'knowledge_search'))
        copy = catalog.apps(); copy.clear()
        self.assertEqual(len(catalog.apps()), 3)
        for table in ('agents', 'skills', 'conversations'):
            self.assertEqual(self.conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 0)

    def test_launch_config_persistence_class_isolation_and_disabled(self):
        student = PlatformStore(TutorStore(self.conn, dict(id=2, class_id=1, role='student')))
        conversations = [student.launch(key, {}) for key in catalog.apps()]
        agent = self.tutor.get('agents', conversations[0]['agent_id'])
        self.assertTrue(agent['skill_ids']); self.assertEqual(agent['material_ids'], [])
        self.tutor.save_agent({'name': '教师自定义名称', 'prompt': '保存的独立角色'}, agent['id'])
        turn, _ = student.tutor.start_turn(conversations[0]['id'], '旧问题', [])
        student.tutor.finish_turn(turn, '旧回答', True)
        initialize(self.conn); initialize(self.conn)
        next_conv = student.launch('course-qa', {})
        self.assertEqual(next_conv['agent_id'], agent['id'])
        self.assertEqual(self.tutor.get('agents', agent['id'])['prompt'], '保存的独立角色')
        self.assertEqual(student.tutor.messages(conversations[0]['id'])[-1]['content'], '旧回答')
        other = PlatformStore(TutorStore(self.conn, dict(id=4, class_id=2, role='teacher')))
        self.assertNotEqual(other.launch('course-qa', {})['agent_id'], agent['id'])
        self.assertNotIn('教师自定义名称', [a['name'] for a in other.applications()])
        self.tutor.save_agent({'enabled': False}, agent['id'])
        self.assertFalse(next(a for a in student.applications() if a.get('key') == 'course-qa')['enabled'])
        with self.assertRaises(ApiError): student.launch('course-qa', {})
        self.assertEqual(self.conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        with self.assertRaises(ValueError): student.launch('study-plan', {'prompt': 'forged'})

    def test_skills_install_conflict_edit_delete_and_reinstall(self):
        installed = self.store.install({'builtin_key': 'guided-solving'})
        modified = installed['content'].replace('逐步检查推理', '先进行单位检查')
        self.tutor.save_skill({'content': modified}, installed['id'])
        self.assertEqual(self.store.install({'builtin_key': 'guided-solving'})['content'], modified)
        self.tutor.delete_skill(installed['id'])
        self.assertEqual(self.store.library()[0]['installed_id'], None)
        self.store.install({'builtin_key': 'guided-solving'})
        manual = self.tutor.save_skill({'content': catalog.skills()['study-plan']['content']})
        with self.assertRaises(ApiError) as exc: self.store.launch('study-plan', {})
        self.assertEqual(exc.exception.status, 409)
        self.assertEqual(self.tutor.get('skills', manual['id'])['content'], manual['content'])
        self.assertEqual(self.conn.execute('SELECT count(*) FROM agents').fetchone()[0], 0)

    def test_templates_render_snapshot_and_invalid_input(self):
        values = {'subject': '物理', 'audience': '初中生', 'goal': '理解受力'}
        prompt = self.store.preview({'source': 'builtin', 'key': 'guided-solving', 'variables': values})
        self.assertIn('物理', prompt); self.assertNotIn('{{', prompt)
        template = self.store.save_template({'name': '我的模板', 'content': '{{subject}}课程，目标{{goal}}'})
        rendered = self.store.preview({'source': 'custom', 'id': template['id'], 'variables': {'subject': '数学', 'goal': '方程'}})
        agent = self.tutor.save_agent({'name': '快照应用', 'prompt': rendered})
        self.store.save_template({'content': '新的静态角色'}, template['id']); self.store.delete_template(template['id'])
        self.assertEqual(self.tutor.get('agents', agent['id'])['prompt'], rendered)
        self.assertEqual(render('{{subject}}', {'subject': '{{goal}}'}), '{{goal}}')
        for content in ('{{unknown}}', '{{subject}', '{{subject.__class__}}', '{{1+1}}'):
            with self.assertRaises(ValueError): variables(content)
        for data in ({}, {'subject': ''}, {'subject': 'x', 'goal': 'extra'}):
            with self.assertRaises(ValueError): render('{{subject}}', data)
        with self.assertRaises(ValueError): render('a' * 1900 + '{{subject}}', {'subject': 'b' * 300})
        for data in ({'name': '', 'content': 'role'}, {'name': 'x', 'content': '{{bad}}'}):
            with self.assertRaises(ValueError): self.store.save_template(data)

    def test_upload_validation_has_no_partial_writes(self):
        for filename, content in (('bad.py', GUIDANCE_EXAMPLE), ('../bad.md', GUIDANCE_EXAMPLE),
                                  ('bad.md', '\ud800'), ('bad.txt', 'x' * 32769),
                                  ('bad.md', '名称：不完整'), ('bad.md', GUIDANCE_EXAMPLE.replace('knowledge_search', 'tool@missing'))):
            with self.assertRaises(ValueError): self.store.upload(dict(filename=filename, content=content))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM skills').fetchone()[0], 0)
        saved = self.store.upload(dict(filename='lesson.md', content='\ufeff' + GUIDANCE_EXAMPLE))
        self.assertEqual(saved['name'], '解题引导')
        with self.assertRaises(ValueError): self.store.upload(dict(filename='lesson.txt', content=GUIDANCE_EXAMPLE))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM skills').fetchone()[0], 1)

    def test_teacher_and_class_boundaries(self):
        template = self.store.save_template({'name': 'A', 'content': 'role'})
        for identity, class_id in ((2, 1), (4, 2)):
            scoped = PlatformStore(TutorStore(self.conn, dict(id=identity, class_id=class_id,
                                                            role='student' if identity == 2 else 'teacher')))
            with self.assertRaises(ApiError) as exc: scoped.template(template['id'])
            self.assertEqual(exc.exception.status, 403 if identity == 2 else 404)
        student = PlatformStore(TutorStore(self.conn, dict(id=2, class_id=1, role='student')))
        for operation in (lambda: student.install({'builtin_key': 'study-plan'}), student.library,
                          lambda: student.upload({'filename': 'x.md', 'content': GUIDANCE_EXAMPLE}),
                          lambda: student.save_template({'name': 'x', 'content': 'x'})):
            with self.assertRaises(ApiError) as exc: operation()
            self.assertEqual(exc.exception.status, 403)

    def test_concurrent_first_launch_is_single_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'test.db')
            db = connect(path); initialize(db)
            db.executescript("INSERT INTO classes VALUES(1,'A'); INSERT INTO users VALUES(1,'s','x','student',1),(2,'p','x','student',1);")
            db.close(); barrier = threading.Barrier(2); results, failures = [], []
            def launch(identity):
                conn = connect(path)
                try:
                    scoped = PlatformStore(TutorStore(conn, dict(id=identity, class_id=1, role='student')))
                    barrier.wait(3); results.append(scoped.launch('guided-solving', {}))
                except Exception as exc: failures.append(type(exc).__name__)
                finally: conn.close()
            threads = [threading.Thread(target=launch, args=(identity,)) for identity in (1, 2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(5)
            self.assertEqual(failures, []); self.assertEqual(len(results), 2)
            self.assertEqual(len({row['agent_id'] for row in results}), 1)
            self.assertEqual({row['owner_id'] for row in results}, {1, 2})
            db = connect(path)
            try:
                for table in ('agents', 'skills', 'agent_skills', 'builtin_app_bindings', 'builtin_skill_bindings'):
                    self.assertEqual(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 1)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            finally: db.close()


if __name__ == '__main__':
    unittest.main()
