import sqlite3
import unittest

from campusclaw.db import connect, initialize
from campusclaw.security import verify_password
from campusclaw.services import (
    authenticate,
    create_user,
    get_authorized_material,
    get_user_by_id,
    list_materials_for_class,
    upload_material,
)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize(self.conn)
        self.conn.execute("INSERT INTO classes (id, name) VALUES (1, 'A 班'), (2, 'B 班')")
        self.teacher_id = create_user(
            self.conn,
            username="teacher_a",
            password="teacher-pass",
            role="teacher",
            class_id=1,
        )
        self.student_id = create_user(
            self.conn,
            username="student_a",
            password="student-pass",
            role="student",
            class_id=1,
        )
        self.teacher_b_id = create_user(
            self.conn,
            username="teacher_b",
            password="teacher-pass",
            role="teacher",
            class_id=2,
        )

    def test_user_model_stores_role_class_and_password_hash_only(self):
        row = self.conn.execute("SELECT * FROM users WHERE username = 'teacher_a'").fetchone()

        self.assertEqual(row["role"], "teacher")
        self.assertEqual(row["class_id"], 1)
        self.assertIn("password_hash", row.keys())
        self.assertNotIn("password", row.keys())
        self.assertNotEqual(row["password_hash"], "teacher-pass")
        self.assertTrue(verify_password("teacher-pass", row["password_hash"]))

    def test_teacher_and_student_can_login_but_wrong_password_fails(self):
        teacher = authenticate(self.conn, "teacher_a", "teacher-pass")
        student = authenticate(self.conn, "student_a", "student-pass")

        self.assertEqual(teacher["role"], "teacher")
        self.assertEqual(student["role"], "student")
        self.assertIsNone(authenticate(self.conn, "teacher_a", "wrong"))

    def test_token_user_lookup_reflects_current_role_and_class(self):
        self.conn.execute(
            "UPDATE users SET role = 'student', class_id = 2 WHERE id = ?", (self.teacher_id,)
        )
        user = get_user_by_id(self.conn, self.teacher_id)
        self.assertEqual(user["user_id"], self.teacher_id)
        self.assertEqual((user["role"], user["class_id"]), ("student", 2))
        self.conn.execute("DELETE FROM users WHERE id = ?", (self.teacher_id,))
        self.assertIsNone(get_user_by_id(self.conn, self.teacher_id))

    def test_teacher_upload_creates_material_and_knowledge_for_own_class(self):
        teacher = {"user_id": self.teacher_id, "role": "teacher", "class_id": 1}
        material = upload_material(
            self.conn,
            user=teacher,
            filename="lesson.txt",
            content="教学材料".encode("utf-8"),
        )

        self.assertEqual(material["class_id"], 1)
        self.assertEqual(len(list_materials_for_class(self.conn, class_id=1)), 1)
        self.assertEqual(len(list_materials_for_class(self.conn, class_id=2)), 0)

    def test_cross_class_material_access_is_rejected_by_query(self):
        teacher = {"user_id": self.teacher_id, "role": "teacher", "class_id": 1}
        material = upload_material(
            self.conn,
            user=teacher,
            filename="lesson.txt",
            content=b"class A only",
        )

        self.assertIsNone(
            get_authorized_material(self.conn, material_id=material["id"], class_id=2)
        )

    def test_student_upload_is_rejected_without_records(self):
        student = {"user_id": self.student_id, "role": "student", "class_id": 1}

        with self.assertRaises(PermissionError):
            upload_material(self.conn, user=student, filename="x.txt", content=b"no")

        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM knowledge_entries").fetchone()[0], 0)

    def test_parse_failure_does_not_create_visible_record(self):
        teacher = {"user_id": self.teacher_id, "role": "teacher", "class_id": 1}

        with self.assertRaises(ValueError):
            upload_material(self.conn, user=teacher, filename="bad.bin", content=b"\xff\xfe")

        self.assertEqual(list_materials_for_class(self.conn, class_id=1), [])

    def test_records_must_reference_classes(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                """
                INSERT INTO materials (title, filename, class_id, teacher_id, status)
                VALUES ('bad', 'bad.txt', 999, ?, 'available')
                """,
                (self.teacher_id,),
            )


if __name__ == "__main__":
    unittest.main()
