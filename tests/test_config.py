import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from campusclaw.config import Config, load_dotenv


class ConfigTests(unittest.TestCase):
    def test_dotenv_preserves_existing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("EXISTING=from-file\nNEW_VALUE='from file'\n", encoding="utf-8")
            with patch.dict(os.environ, {"EXISTING": "from-process"}, clear=True):
                load_dotenv(path)
                self.assertEqual(os.environ["EXISTING"], "from-process")
                self.assertEqual(os.environ["NEW_VALUE"], "from file")

    def test_rag_validation_rejects_bad_values_without_echoing_secret(self):
        config = Config(
            secret_key="test-secret",
            database_path=":memory:",
            max_upload_bytes=1024,
            seed_demo_users=False,
            teacher_password=None,
            student_password=None,
            embedding_base_url="https://example.test/v1",
            embedding_api_key="private-test-key",
            chat_base_url="https://example.test/v1",
            chat_api_key="private-test-key",
            chunk_size=10,
            chunk_overlap=10,
        )
        errors = config.validate_rag()
        self.assertIn("CHUNK_SIZE/CHUNK_OVERLAP", errors)
        self.assertNotIn("private-test-key", str(errors))


if __name__ == "__main__":
    unittest.main()
