import unittest

from campusclaw.security import hash_password, sign_session, verify_password, verify_session


class SecurityTests(unittest.TestCase):
    def test_password_hash_does_not_store_plaintext_and_verifies(self):
        hashed = hash_password("teacher-secret")

        self.assertNotIn("teacher-secret", hashed)
        self.assertTrue(verify_password("teacher-secret", hashed))
        self.assertFalse(verify_password("wrong", hashed))

    def test_session_signature_detects_tampering(self):
        token = sign_session(
            {"id": 1, "username": "teacher_a", "role": "teacher", "class_id": 1},
            "server-only-secret",
        )

        self.assertEqual(verify_session(token, "server-only-secret")["role"], "teacher")
        self.assertIsNone(verify_session(token + "tampered", "server-only-secret"))


if __name__ == "__main__":
    unittest.main()
