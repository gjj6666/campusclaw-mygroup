from __future__ import annotations

import sqlite3
from typing import Any

from .db import row_to_dict
from .security import hash_password, verify_password


ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"


def create_user(
    conn: sqlite3.Connection,
    *,
    username: str,
    password: str,
    role: str,
    class_id: int,
) -> int:
    if role not in {ROLE_TEACHER, ROLE_STUDENT}:
        raise ValueError("unsupported role")
    cursor = conn.execute(
        """
        INSERT INTO users (username, password_hash, role, class_id)
        VALUES (?, ?, ?, ?)
        """,
        (username, hash_password(password), role, class_id),
    )
    conn.commit()
    return int(cursor.lastrowid)


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, username, password_hash, role, class_id FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "class_id": row["class_id"],
    }


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id AS user_id, username, role, class_id FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return row_to_dict(row)


def get_authorized_material(
    conn: sqlite3.Connection,
    *,
    material_id: int,
    class_id: int,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT m.id, m.title, m.filename, m.class_id, m.status, m.subject, k.content
        FROM materials m
        JOIN knowledge_entries k ON k.material_id = m.id AND k.class_id = m.class_id
        WHERE m.id = ? AND m.class_id = ? AND m.status = 'available'
        """,
        (material_id, class_id),
    ).fetchone()
    return row_to_dict(row)


def list_materials_for_class(conn: sqlite3.Connection, *, class_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT m.id, m.title, m.filename, m.class_id, m.status, m.subject, k.id AS knowledge_entry_id
        FROM materials m
        JOIN knowledge_entries k ON k.material_id = m.id AND k.class_id = m.class_id
        WHERE m.class_id = ? AND m.status = 'available'
        ORDER BY m.id
        """,
        (class_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def upload_material(
    conn: sqlite3.Connection,
    *,
    user: dict[str, Any],
    filename: str,
    content: bytes,
    subject: str = '通用',
) -> dict[str, Any]:
    if user["role"] != ROLE_TEACHER:
        raise PermissionError("students cannot upload materials")
    if not filename or not content:
        raise ValueError("filename and content are required")
    if not isinstance(subject, str) or not 1 <= len(subject.strip()) <= 64:
        raise ValueError('学科必须为1至64字')
    parsed_content = parse_material(content)
    if parsed_content is None:
        raise ValueError("material parsing failed")

    title = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    try:
        cursor = conn.execute(
            """
            INSERT INTO materials (title, filename, class_id, teacher_id, status, subject)
            VALUES (?, ?, ?, ?, 'available', ?)
            """,
            (title, title, user["class_id"], user["user_id"], subject.strip()),
        )
        material_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO knowledge_entries (material_id, class_id, title, content)
            VALUES (?, ?, ?, ?)
            """,
            (material_id, user["class_id"], title, parsed_content),
        )
        conn.commit()
    except sqlite3.DatabaseError:
        conn.rollback()
        raise
    return {
        "id": material_id,
        "title": title,
        "class_id": user["class_id"],
        "status": "available",
        "subject": subject.strip(),
    }


def parse_material(content: bytes) -> str | None:
    try:
        text = content.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    if not text:
        return None
    return text
