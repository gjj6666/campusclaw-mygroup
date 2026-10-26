import time
import unittest
from unittest.mock import patch

from campusclaw.security import (
    ACCESS_TOKEN_TTL_SECONDS,
    hash_password,
    sign_session,
    verify_password,
    verify_session,
)


class SecurityTests(unittest.TestCase):
    def test_password_hash_does_not_store_plaintext_and_verifies(self):
        hashed = hash_password("teacher-secret")

        self.assertNotIn("teacher-secret", hashed)
        self.assertTrue(verify_password("teacher-secret", hashed))
        self.assertFalse(verify_password("wrong", hashed))

    def test_token_contains_only_user_id_and_expiry(self):
        token = sign_session(
            {"id": 1, "username": "teacher_a", "role": "teacher", "class_id": 1},
            "server-only-secret",
        )

        payload = verify_session(token, "server-only-secret")
        self.assertEqual(set(payload), {"user_id", "exp"})
        self.assertEqual(payload["user_id"], 1)
        self.assertLessEqual(payload["exp"] - time.time(), ACCESS_TOKEN_TTL_SECONDS)
        self.assertIsNone(verify_session(token + "tampered", "server-only-secret"))
        self.assertIsNone(verify_session("malformed", "server-only-secret"))

    def test_token_expires(self):
        with patch("campusclaw.security.time.time", return_value=100):
            token = sign_session({"id": 1}, "server-only-secret", ttl_seconds=10)
            self.assertEqual(verify_session(token, "server-only-secret")["user_id"], 1)
        with patch("campusclaw.security.time.time", return_value=110):
            self.assertIsNone(verify_session(token, "server-only-secret"))


if __name__ == "__main__":
    unittest.main()
