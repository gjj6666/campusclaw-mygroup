import io
import json
import unittest
from unittest.mock import patch

from campusclaw.vector_store import VectorStore, VectorStoreError


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class VectorStoreTests(unittest.TestCase):
    def test_collection_upsert_delete_and_class_filter(self):
        requests = []

        def transport(request, timeout):
            body = json.loads(request.data) if request.data else None
            requests.append((request.method, request.full_url, body))
            if request.method == "GET":
                result = {"config": {"params": {"vectors": {"size": 2048, "distance": "Cosine"}}}}
            elif request.full_url.endswith("/points/query"):
                result = {"points": [{"id": 12, "score": 0.9}]}
            else:
                result = True
            return Response(json.dumps({"status": "ok", "result": result}).encode())

        store = VectorStore("http://qdrant:6333", "course_v1", 2048)
        with patch("urllib.request.urlopen", side_effect=transport):
            store.ensure_collection()
            store.upsert([{"id": 12, "vector": [0.0] * 2048, "payload": {"class_id": 1}}])
            self.assertEqual(store.query([0.0] * 2048, 1, 5, 0.65, "v1"), [(12, 0.9)])
            store.delete([12])
        self.assertEqual(requests[1][2]["points"][0]["id"], 12)
        self.assertEqual(requests[2][2]["filter"]["must"][0]["match"]["value"], 1)
        self.assertEqual(requests[2][2]["score_threshold"], 0.65)
        self.assertEqual(requests[2][2]["filter"]["must"][1]["match"]["value"], "v1")

    def test_dimension_mismatch_rejected(self):
        reply = {"status": "ok", "result": {"config": {"params": {"vectors": {"size": 3, "distance": "Cosine"}}}}}
        with patch("urllib.request.urlopen", return_value=Response(json.dumps(reply).encode())):
            with self.assertRaises(VectorStoreError):
                VectorStore("http://qdrant:6333", "course_v1", 2048).ensure_collection()
