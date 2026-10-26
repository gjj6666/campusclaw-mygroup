import json
import threading
import unittest
from dataclasses import replace
from unittest.mock import patch

from campusclaw.db import connect, initialize
from campusclaw.config import Config
from campusclaw.library import Library
from campusclaw.attachments import Attachments
from campusclaw.index_policy import normalize, split_policy, preview, current
from campusclaw.orchestration import prepare
from campusclaw.rag import RagService
from campusclaw.services import upload_material
from campusclaw.tutor import TutorStore, ApiError
from campusclaw.mcp_store import McpStore
from campusclaw.mcp_client import McpClient
from apitest.mcp_support import DemoMcp
from tests.test_rag import FakeEmbedder, FakeVectors


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.conn=connect(':memory:'); self.addCleanup(self.conn.close); initialize(self.conn)
        self.conn.executescript("INSERT INTO classes VALUES(1,'A'),(2,'B'); INSERT INTO users VALUES "
            "(1,'teacher','hash','teacher',1),(2,'student','hash','student',1),(3,'peer','hash','student',1),(4,'other','hash','teacher',2);")
        self.teacher=TutorStore(self.conn,dict(id=1,class_id=1,role='teacher'))
        self.student=TutorStore(self.conn,dict(id=2,class_id=1,role='student'))
        self.library=Library(self.student)
        self.agent=self.teacher.save_agent({'name':'Assistant'})
        self.conv=self.student.create_conversation(self.agent['id'])['id']
        self.config=Config('secret',':memory:',1048576,False,None,None,embedding_dim=2)
        self.vectors=FakeVectors(); self.embedder=FakeEmbedder()
        self.rag=RagService(self.conn,self.config,vectors=self.vectors,embedder=self.embedder)

    def material(self, content='alpha '+('A long paragraph.\n'*40)):
        return upload_material(self.conn,user=dict(user_id=1,class_id=1,role='teacher'),filename='a.md',content=content.encode(),subject='数学')['id']

    def test_personal_copy_cross_conversation_and_ownership(self):
        material=self.material()
        copied=self.library.save({'source':dict(kind='shared',id=material)})
        self.assertEqual(copied['id'],self.library.save({'source':dict(kind='shared',id=material)})['id'])
        second=self.student.create_conversation(self.agent['id'])['id']
        context=dict(skill=None,materials=[dict(source='personal',id=copied['id'])])
        _,messages,sources,_=prepare(self.student,self.rag,second,'一个问题',context=context)
        self.assertEqual(sources[0]['kind'],'personal');self.assertIn('alpha',messages[-1]['content'])
        self.assertNotIn('alpha',messages[0]['content']);self.assertEqual(self.vectors.points,{})
        for user in [dict(id=1,class_id=1,role='teacher'),dict(id=3,class_id=1,role='student'),dict(id=4,class_id=2,role='teacher')]:
            store=TutorStore(self.conn,user)
            with self.assertRaises(ApiError) as exc: Library(store).personal(copied['id'])
            self.assertEqual(exc.exception.status,404);self.assertEqual(Library(store).personals(),[])
        self.assertNotIn(copied['id'],[r['id'] for r in self.conn.execute('SELECT id FROM conversation_attachments')])

    def test_promote_preserves_attachment_boundary_and_validation(self):
        files=Attachments(self.student)
        item=files.upload(self.conv,dict(kind='material',filename='private.txt',content='private'))
        copied=self.library.save({'source':dict(kind='attachment',id=item['id'],conversation_id=self.conv)})
        other=self.student.create_conversation(self.agent['id'])['id']
        with self.assertRaises(ApiError): files.get(other,item['id'])
        self.assertEqual(self.library.personal(copied['id'])['content'],'private')
        for data in [dict(filename='x.pdf',content='text'),dict(filename='x.md',content='中'*11000),
                     dict(filename='x.md',content='\ud800'),dict(filename='x.md',content='a',owner_id=1)]:
            with self.assertRaises(ValueError): self.library.save(data)
        with self.assertRaises(ValueError): files.resolve(self.conv,dict(skill=dict(source='personal',id=copied['id'])))
        one=self.library.save(dict(filename='a.md',content='a'*10000));two=self.library.save(dict(filename='b.md',content='b'*10000))
        with self.assertRaises(ValueError): files.resolve(self.conv,dict(materials=[dict(source='personal',id=x['id']) for x in (one,two)]))

    def test_policy_preview_positions_no_network_and_bounds(self):
        content='  中国古诗。\n\n'+('abcdef！？ hello\n'*150)+'  '
        for separator in ('paragraph','newline','sentence'):
            for trim in (True,False):
                p=normalize(dict(mode='custom',size=101,ratio=40,separator=separator,trim=trim),self.config)
                chunks=split_policy(content,p)
                self.assertEqual(chunks,split_policy(content,p))
                self.assertTrue(all(content[c.char_start:c.char_end]==c.content for c in chunks))
                self.assertTrue(all(0<len(c.content)<=101 for c in chunks))
                self.assertEqual(preview(content,p)['total'],len(chunks))
                self.assertLessEqual(len(preview(content,p)['chunks']),20)
        for data in [dict(mode='custom',size=99,ratio=0),dict(mode='custom',size=True,ratio=1),
                     dict(mode='custom',size=100,ratio=41),dict(mode='bad')]:
            with self.assertRaises(ValueError):normalize(data,self.config)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM knowledge_chunks').fetchone()[0],0)

    def test_mixed_policy_versions_and_failed_rebuild_retry(self):
        old=self.material();self.assertEqual(self.rag.index_material(old),'ready')
        first=self.rag.search('alpha',1,'keyword')[0]
        self.conn.execute('INSERT INTO class_index_policies VALUES(?,?,1)',(1,json.dumps(dict(mode='custom',size=100,ratio=10,separator='newline',trim=True))))
        self.conn.commit()
        new=self.material();self.assertEqual(self.rag.index_material(new),'ready')
        self.assertEqual({x['material_id'] for x in self.rag.search('alpha',1,'keyword')},{old,new})
        # A failed replacement is never mixed into a successful old generation.
        self.embedder.fail=True;self.assertEqual(self.rag.index_material(old,force=True),'failed')
        self.assertIsNone(self.rag._source(first['id'],1))
        self.assertEqual({x['material_id'] for x in self.rag.search('alpha',1,'keyword')},{new})
        self.embedder.fail=False;self.assertEqual(self.rag.index_material(old,force=True),'ready')
        state=self.conn.execute('SELECT * FROM material_index_states WHERE material_id=?',(old,)).fetchone()
        self.assertEqual(json.loads(state['policy'])['mode'],'custom')
        self.assertEqual({x['material_id'] for x in self.rag.search('alpha',1,'keyword')},{old,new})
        changed=RagService(self.conn,replace(self.config,embedding_model='different'),vectors=self.vectors,embedder=self.embedder)
        self.assertEqual(changed.search('alpha',1,'keyword'),[])

    def test_rebuild_lock_policy_snapshot_and_migration(self):
        material=self.material();seen=[]
        def embed(text):
            with self.assertRaises(ApiError) as exc:self.rag.index_material(material,force=True)
            self.assertEqual(exc.exception.status,409)
            if not seen:
                self.conn.execute('INSERT INTO class_index_policies VALUES(?,?,1)',(1,json.dumps(dict(mode='custom',size=100,ratio=0))))
                self.conn.commit();seen.append(True)
            return [.5,.5]
        with patch.object(self.embedder,'embed',side_effect=embed):self.assertEqual(self.rag.index_material(material),'ready')
        before=self.conn.execute('SELECT active_version FROM material_index_states').fetchone()[0]
        initialize(self.conn);initialize(self.conn)
        self.assertEqual(self.conn.execute('SELECT active_version FROM material_index_states').fetchone()[0],before)
        self.assertEqual(json.loads(self.conn.execute('SELECT policy FROM material_index_states').fetchone()[0])['mode'],'auto')
        self.assertEqual(current(self.conn,1,self.config)['policy']['mode'],'custom')
        self.assertEqual(self.conn.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_mcp_update_remove_and_inflight_re_registration(self):
        with DemoMcp() as remote:
            registry=McpStore(self.conn,self.teacher.user)
            server=registry.register(dict(name='tools',base_url=remote.url,auth_token=remote.token));identity=server['id']
            registry.connect(identity)
            self.assertEqual(registry.update(identity,dict(auth_token=''))['status'],'connected')
            self.assertNotIn('auth_token',registry.update(identity,dict(base_url=remote.url+'/alternate')))
            self.assertEqual(registry.tools(identity),[])
            registry.update(identity,dict(base_url=remote.url));registry.connect(identity)
            def replace_server(*args):
                registry.remove(identity)
                replacement=registry.register(dict(name='tools',base_url=remote.url,auth_token=remote.token))
                registry.connect(replacement['id'])
                return 'stale data'
            teacher_conv=self.teacher.create_conversation(self.agent['id'])['id']
            with patch.object(McpClient,'call',side_effect=replace_server):
                call,value=registry.invoke('formula_hint@tools','question',teacher_conv)
            self.assertEqual(call['status'],'denied');self.assertEqual(value,'')
            registry.remove(registry.servers()[0]['id'])
            with patch.object(McpClient,'call') as network:
                self.assertEqual(registry.invoke('formula_hint@tools','question',teacher_conv)[0]['status'],'denied');network.assert_not_called()
            self.assertEqual(len(registry.audits()),2)
