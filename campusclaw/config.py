from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    secret_key: str | None
    database_path: str
    max_upload_bytes: int
    seed_demo_users: bool
    teacher_password: str | None
    student_password: str | None

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            secret_key=os.environ.get("APP_SECRET_KEY"),
            database_path=os.environ.get("DATABASE_PATH", "data/campusclaw.db"),
            max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", "1048576")),
            seed_demo_users=os.environ.get("SEED_DEMO_USERS", "true").lower() == "true",
            teacher_password=os.environ.get("DEMO_TEACHER_PASSWORD"),
            student_password=os.environ.get("DEMO_STUDENT_PASSWORD"),
        )

    @property
    def is_healthy_config(self) -> bool:
        return bool(self.secret_key and self.secret_key.strip())

    @property
    def missing_config(self) -> list[str]:
        missing: list[str] = []
        if not self.is_healthy_config:
            missing.append("APP_SECRET_KEY")
        return missing
