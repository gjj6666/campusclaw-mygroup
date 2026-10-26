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

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY,
    knowledge_entry_id INTEGER NOT NULL REFERENCES knowledge_entries(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    ordinal INTEGER NOT NULL,
    char_start INTEGER NOT NULL CHECK (char_start >= 0),
    char_end INTEGER NOT NULL CHECK (char_end > char_start),
    content TEXT NOT NULL CHECK (length(content) > 0),
    index_status TEXT NOT NULL CHECK (index_status IN ('pending', 'ready', 'failed')),
    index_version TEXT NOT NULL,
    UNIQUE (material_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_chunks_class_status ON knowledge_chunks(class_id, index_status);

CREATE TRIGGER IF NOT EXISTS validate_chunk_source_insert
BEFORE INSERT ON knowledge_chunks
WHEN NOT EXISTS (
    SELECT 1 FROM knowledge_entries k
    JOIN materials m ON m.id = k.material_id
    WHERE k.id = NEW.knowledge_entry_id
      AND m.id = NEW.material_id
      AND m.class_id = NEW.class_id
      AND k.class_id = NEW.class_id
)
BEGIN
    SELECT RAISE(ABORT, 'chunk source mismatch');
END;

CREATE TRIGGER IF NOT EXISTS validate_chunk_source_update
BEFORE UPDATE OF knowledge_entry_id, material_id, class_id ON knowledge_chunks
WHEN NOT EXISTS (
    SELECT 1 FROM knowledge_entries k
    JOIN materials m ON m.id = k.material_id
    WHERE k.id = NEW.knowledge_entry_id
      AND m.id = NEW.material_id
      AND m.class_id = NEW.class_id
      AND k.class_id = NEW.class_id
)
BEGIN
    SELECT RAISE(ABORT, 'chunk source mismatch');
END;

CREATE TABLE IF NOT EXISTS chunk_terms (
    chunk_id INTEGER NOT NULL REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    frequency INTEGER NOT NULL CHECK (frequency > 0),
    PRIMARY KEY (chunk_id, term)
);

CREATE INDEX IF NOT EXISTS idx_chunk_terms_term ON chunk_terms(term);
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
    from .tutor_schema import SCHEMA as tutor_schema
    if 'subject' not in {row['name'] for row in conn.execute('PRAGMA table_info(materials)')}:
        conn.execute("ALTER TABLE materials ADD COLUMN subject TEXT NOT NULL DEFAULT '通用'")
    conn.executescript(tutor_schema)
    from .mcp_schema import migrate
    migrate(conn)
    from .platform_schema import SCHEMA as platform_schema
    conn.executescript(platform_schema)
    from .attachments import migrate as migrate_attachments
    migrate_attachments(conn)
    from .workspace_schema import migrate as migrate_workspace
    migrate_workspace(conn)
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
