import unittest
from dataclasses import replace
from unittest.mock import patch

from campusclaw.config import Config
from campusclaw.db import connect, initialize
from campusclaw.orchestration import prepare, validate_answer
from campusclaw.rag import RagService, InvalidAnswer
from campusclaw.services import upload_material
from campusclaw.tutor import TutorStore
from campusclaw.vector_store import VectorStore
from tests.test_rag import FakeEmbedder, FakeVectors


class ScopedVectors(FakeVectors):
    def query(self, vector, class_id, limit, min_score, index_version, material_ids=None):
        self.last_scope = material_ids
        return [(i, .9) for i, p in self.points.items() if p['payload']['class_id'] == class_id
                and (material_ids is None or p['payload']['material_id'] in material_ids)][:limit]


class OrchestrationTests(unittest.TestCase):
    def test_scope_before_top_four_then_subject_no_refill(self):
        conn = connect(':memory:')
        self.addCleanup(conn.close)
        initialize(conn)
        conn.executescript("INSERT INTO classes VALUES(1,'A'); INSERT INTO users VALUES(1,'a','hash','teacher',1);")
        config = Config('test', ':memory:', 10000, False, None, None, embedding_dim=2)
        vectors = ScopedVectors()
        rag = RagService(conn, config, embedder=FakeEmbedder(), vectors=vectors)
        teacher = dict(user_id=1, class_id=1, role='teacher')
        store = TutorStore(conn, teacher)
        unbound = upload_material(conn, user=teacher, filename='unbound.txt', content=b'alpha alpha alpha alpha')
        rag.index_material(unbound['id'])
        ids = []
        for i in range(5):
            material = upload_material(conn, user=teacher, filename=f'{i}.txt', content=b'alpha', subject='数学' if i % 2 else '物理')
            ids.append(material['id'])
            rag.index_material(material['id'])
        agent = store.save_agent({'name': '助教', 'material_ids': ids, 'subject': '数学'})
        conv = store.create_conversation(agent['id'])
        _, messages, sources, _ = prepare(store, rag, conv['id'], 'alpha 问题')
        self.assertEqual(vectors.last_scope, ids)
        self.assertEqual([s['material_id'] for s in sources], [ids[1], ids[3]])
        self.assertEqual([s['citation'] for s in sources], ['S1', 'S2'])
        self.assertIn('[S2]', messages[-1]['content'])
        self.assertNotIn('资料：', messages[0]['content'])
        store.save_agent({'material_ids': []}, agent['id'])
        _, messages, sources, _ = prepare(store, rag, conv['id'], 'alpha 问题')
        self.assertEqual(sources, [])
        self.assertIn('仍应', messages[0]['content'])
        self.assertEqual(messages[-1]['content'], 'alpha 问题')
        validate_answer('普通回答', [])
        for answer, evidence in (('伪造[S1]', []), ('无引用', [{'citation': 'S1'}]), ('伪造[S9]', [{'citation': 'S1'}]),
                                 ('未找到', []), ('未找到相关资料。', []), ('伪造[1]', [])):
            with self.assertRaises(InvalidAnswer):
                validate_answer(answer, evidence)

    def test_qdrant_material_filter_sent_to_backend(self):
        seen = []
        def request(method, path, payload):
            seen.append(payload)
            return {'result': {'points': []}}
        store = VectorStore('http://example', 'course', 2)
        with patch.object(store, '_request', side_effect=request):
            store.query([.5, .5], 1, 4, .6, 'v1', material_ids=[7, 8])
        self.assertIn({'key': 'material_id', 'match': {'any': [7, 8]}}, seen[0]['filter']['must'])
