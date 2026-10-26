"""Additive workspace migration; private files never become shared records."""
import json
import uuid


def migrate(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS personal_materials (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, class_id INTEGER NOT NULL,
      title TEXT NOT NULL, filename TEXT NOT NULL, subject TEXT NOT NULL, content TEXT NOT NULL,
      origin_kind TEXT NOT NULL, origin_id INTEGER, origin_conversation_id INTEGER,
      content_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(owner_id,class_id) REFERENCES users(id,class_id));
    CREATE INDEX IF NOT EXISTS idx_personal_owner ON personal_materials(owner_id,class_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_copy ON personal_materials(
      owner_id,class_id,origin_kind,origin_id,content_hash) WHERE origin_kind<>'upload';
    CREATE TABLE IF NOT EXISTS class_index_policies (
      class_id INTEGER PRIMARY KEY REFERENCES classes(id), policy TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS material_index_states (
      material_id INTEGER PRIMARY KEY REFERENCES materials(id) ON DELETE CASCADE,
      policy TEXT NOT NULL DEFAULT '{}', active_version TEXT NOT NULL,
      embedding_signature TEXT NOT NULL, status TEXT NOT NULL, last_error TEXT NOT NULL DEFAULT '');
    ''')
    if 'state_nonce' not in {r['name'] for r in conn.execute('PRAGMA table_info(mcp_servers)')}:
        conn.execute("ALTER TABLE mcp_servers ADD COLUMN state_nonce TEXT NOT NULL DEFAULT ''")
    for row in conn.execute("SELECT id FROM mcp_servers WHERE state_nonce='' ").fetchall():
        conn.execute('UPDATE mcp_servers SET state_nonce=? WHERE id=?', (uuid.uuid4().hex, row['id']))
    # Existing chunk versions remain authoritative until an explicit reindex.
    for row in conn.execute('SELECT material_id,index_version,MIN(index_status) AS state,COUNT(DISTINCT index_version) AS versions '
                            'FROM knowledge_chunks GROUP BY material_id').fetchall():
        version = row['index_version']
        parts = version.rsplit(':', 4)
        signature, policy = '', {}
        if len(parts) == 5:
            model, dim, size, overlap, _ = parts
            try:
                signature = model + ':' + dim
                policy = dict(mode='auto', size=int(size), overlap=int(overlap), separator='paragraph', trim=True)
            except ValueError:
                pass
        conn.execute('INSERT OR IGNORE INTO material_index_states(material_id,policy,active_version,embedding_signature,status) '
                     'VALUES(?,?,?,?,?)', (row['material_id'], json.dumps(policy), version, signature,
                     'ready' if row['state'] == 'ready' and row['versions'] == 1 else 'failed'))
