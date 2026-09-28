from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from .security import hash_password


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('teacher', 'student')),
    class_id INTEGER NOT NULL REFERENCES classes(id)
);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    teacher_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL CHECK (status IN ('available', 'failed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_entries (
    id INTEGER PRIMARY KEY,
    material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(database_path: str) -> sqlite3.Connection:
    if database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def seed_demo_data(
    conn: sqlite3.Connection,
    *,
    teacher_password: str | None = None,
    student_password: str | None = None,
) -> None:
    actual_teacher_password = teacher_password or os.environ.get("DEMO_TEACHER_PASSWORD")
    actual_student_password = student_password or os.environ.get("DEMO_STUDENT_PASSWORD")
    if not actual_teacher_password or not actual_student_password:
        return

    conn.execute("INSERT OR IGNORE INTO classes (id, name) VALUES (?, ?)", (1, "A 班"))
    conn.execute("INSERT OR IGNORE INTO classes (id, name) VALUES (?, ?)", (2, "B 班"))
    users = [
        ("teacher_a", actual_teacher_password, "teacher", 1),
        ("student_a", actual_student_password, "student", 1),
        ("teacher_b", actual_teacher_password, "teacher", 2),
        ("student_b", actual_student_password, "student", 2),
    ]
    for username, password, role, class_id in users:
        if not conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, class_id)
                VALUES (?, ?, ?, ?)
                """,
                (username, hash_password(password), role, class_id),
            )
    conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)
