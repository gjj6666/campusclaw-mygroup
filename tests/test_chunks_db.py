import sqlite3
import unittest

from campusclaw.db import connect, initialize
from campusclaw.services import create_user, upload_material


class ChunkDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize(self.conn)
        self.conn.execute("INSERT INTO classes (id, name) VALUES (1, 'A 班'), (2, 'B 班')")
        teacher_id = create_user(
            self.conn, username="teacher", password="test", role="teacher", class_id=1
        )
        self.material = upload_material(
            self.conn,
            user={"user_id": teacher_id, "role": "teacher", "class_id": 1},
            filename="lesson.txt", content=b"lesson content",
        )
        self.entry_id = self.conn.execute(
            "SELECT id FROM knowledge_entries WHERE material_id = ?", (self.material["id"],)
        ).fetchone()[0]

    def tearDown(self):
        self.conn.close()

    def insert_chunk(self, class_id=1):
        return self.conn.execute(
            """INSERT INTO knowledge_chunks
               (knowledge_entry_id, material_id, class_id, ordinal, char_start, char_end,
                content, index_status, index_version)
               VALUES (?, ?, ?, 0, 0, 6, 'lesson', 'pending', 'v1')""",
            (self.entry_id, self.material["id"], class_id),
        ).lastrowid

    def test_chunk_and_terms_cascade_with_material(self):
        chunk_id = self.insert_chunk()
        self.conn.execute(
            "INSERT INTO chunk_terms (chunk_id, term, frequency) VALUES (?, 'le', 2)",
            (chunk_id,),
        )
        self.conn.execute("DELETE FROM materials WHERE id = ?", (self.material["id"],))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM chunk_terms").fetchone()[0], 0)

    def test_chunk_class_and_status_constraints(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_chunk(class_id=2)
        chunk_id = self.insert_chunk()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE knowledge_chunks SET index_status='partial' WHERE id=?", (chunk_id,))


if __name__ == "__main__":
    unittest.main()
