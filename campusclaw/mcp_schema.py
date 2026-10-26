"""Idempotent schema and transactional upgrade from week-five skills."""
SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS mcp_servers (
 id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id),
 name TEXT NOT NULL, base_url TEXT NOT NULL, auth_token TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'disconnected' CHECK(status IN ('connected','disconnected')),
 version INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(class_id,name), UNIQUE(id,class_id)
);
CREATE TABLE IF NOT EXISTS mcp_tools (
 server_id INTEGER NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
 name TEXT NOT NULL, description TEXT NOT NULL, input_schema TEXT NOT NULL,
 PRIMARY KEY(server_id,name)
);
CREATE TABLE IF NOT EXISTS mcp_audits (
 id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id),
 user_id INTEGER NOT NULL, conversation_id INTEGER NOT NULL,
 tool_ref TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('ok','error','denied')),
 detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(user_id,class_id) REFERENCES users(id,class_id),
 FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);
CREATE INDEX IF NOT EXISTS idx_mcp_audits_class ON mcp_audits(class_id,id);
"""


def migrate(conn):
    conn.executescript(SCHEMA)
    if conn.execute("SELECT 1 FROM schema_migrations WHERE name='week06_mcp'").fetchone():
        return
    original = conn.execute("SELECT sql FROM sqlite_master WHERE name='skills'").fetchone()[0]
    old_check = "CHECK(tool IN ('','knowledge_search'))"
    conn.commit()
    # Foreign keys are disabled only for the table swap, outside the transaction;
    # dependent tables retain their references to the final table named skills.
    conn.execute('PRAGMA foreign_keys=OFF')
    try:
        conn.execute('BEGIN IMMEDIATE')
        if old_check in original:
            replacement = original.replace('CREATE TABLE skills', 'CREATE TABLE skills_mcp_upgrade', 1)
            replacement = replacement.replace(old_check, 'CHECK(length(tool)<=129)')
            conn.execute(replacement)
            conn.execute('INSERT INTO skills_mcp_upgrade SELECT * FROM skills')
            conn.execute('DROP TABLE skills')
            conn.execute('ALTER TABLE skills_mcp_upgrade RENAME TO skills')
        if conn.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('技能迁移外键检查失败')
        conn.execute("INSERT INTO schema_migrations(name) VALUES('week06_mcp')")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute('PRAGMA foreign_keys=ON')
