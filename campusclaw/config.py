from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    """Load local server settings without overriding the process environment."""
    dotenv = path or Path(__file__).resolve().parent.parent / ".env"
    if not dotenv.is_file():
        return
    for line in dotenv.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.isidentifier() or not key.isascii():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Config:
    secret_key: str | None
    database_path: str
    max_upload_bytes: int
    seed_demo_users: bool
    teacher_password: str | None
    student_password: str | None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "course-embedding"
    embedding_dim: int = 2048
    chat_base_url: str | None = None
    chat_api_key: str | None = None
    chat_model: str = "course-chat"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "campusclaw_course_embedding_v1"
    chunk_size: int = 500
    chunk_overlap: int = 80
    min_vector_score: float = 0.65
    search_limit: int = 10

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        return cls(
            secret_key=os.environ.get("APP_SECRET_KEY"),
            database_path=os.environ.get("DATABASE_PATH", "data/campusclaw.db"),
            max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", "1048576")),
            seed_demo_users=os.environ.get("SEED_DEMO_USERS", "true").lower() == "true",
            teacher_password=os.environ.get("DEMO_TEACHER_PASSWORD"),
            student_password=os.environ.get("DEMO_STUDENT_PASSWORD"),
            embedding_base_url=os.environ.get("EMBEDDING_BASE_URL"),
            embedding_api_key=os.environ.get("EMBEDDING_API_KEY"),
            embedding_model=os.environ.get("EMBEDDING_MODEL", "course-embedding"),
            embedding_dim=int(os.environ.get("EMBEDDING_DIM", "2048")),
            chat_base_url=os.environ.get("CHAT_BASE_URL") or os.environ.get("EMBEDDING_BASE_URL"),
            chat_api_key=os.environ.get("CHAT_API_KEY") or os.environ.get("EMBEDDING_API_KEY"),
            chat_model=os.environ.get("CHAT_MODEL", "course-chat"),
            qdrant_url=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"),
            qdrant_collection=os.environ.get("QDRANT_COLLECTION", "campusclaw_course_embedding_v1"),
            chunk_size=int(os.environ.get("CHUNK_SIZE", "500")),
            chunk_overlap=int(os.environ.get("CHUNK_OVERLAP", "80")),
            min_vector_score=float(os.environ.get("MIN_VECTOR_SCORE", "0.65")),
            search_limit=int(os.environ.get("SEARCH_LIMIT", "10")),
        )

    def validate_rag(self) -> list[str]:
        errors: list[str] = []
        if not self.embedding_base_url or not self.embedding_base_url.rstrip("/").endswith("/v1"):
            errors.append("EMBEDDING_BASE_URL")
        if not self.embedding_api_key:
            errors.append("EMBEDDING_API_KEY")
        if not self.chat_base_url or not self.chat_base_url.rstrip("/").endswith("/v1"):
            errors.append("CHAT_BASE_URL")
        if not self.chat_api_key:
            errors.append("CHAT_API_KEY")
        if self.embedding_dim <= 0:
            errors.append("EMBEDDING_DIM")
        if self.chunk_size <= 0 or self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            errors.append("CHUNK_SIZE/CHUNK_OVERLAP")
        if not -1.0 <= self.min_vector_score <= 1.0:
            errors.append("MIN_VECTOR_SCORE")
        if self.search_limit <= 0 or self.search_limit > 100:
            errors.append("SEARCH_LIMIT")
        return errors

    @property
    def is_healthy_config(self) -> bool:
        return bool(self.secret_key and self.secret_key.strip())

    @property
    def missing_config(self) -> list[str]:
        missing: list[str] = []
        if not self.is_healthy_config:
            missing.append("APP_SECRET_KEY")
        return missing
