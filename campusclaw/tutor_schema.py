"""Additive, idempotent week-five schema."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
 id INTEGER PRIMARY KEY,
 class_id INTEGER NOT NULL REFERENCES classes(id),
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 64),
 prompt TEXT NOT NULL DEFAULT '' CHECK(length(prompt)<=2000),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 subject TEXT NOT NULL DEFAULT '通用',
 UNIQUE(id,class_id)
);
CREATE TABLE IF NOT EXISTS skills (
 id INTEGER PRIMARY KEY,
 class_id INTEGER NOT NULL REFERENCES classes(id),
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 64),
 conditions TEXT NOT NULL CHECK(length(conditions) BETWEEN 1 AND 500),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 tool TEXT NOT NULL DEFAULT '' CHECK(tool IN ('','knowledge_search')),
 body TEXT NOT NULL CHECK(length(body)>0),
 content TEXT NOT NULL CHECK(length(content)<=8000),
 UNIQUE(class_id,name), UNIQUE(id,class_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_material_class_identity ON materials(id,class_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_class_identity ON users(id,class_id);
CREATE TABLE IF NOT EXISTS agent_skills (
 agent_id INTEGER NOT NULL,
 skill_id INTEGER NOT NULL,
 class_id INTEGER NOT NULL,
 PRIMARY KEY(agent_id,skill_id),
 FOREIGN KEY(agent_id,class_id) REFERENCES agents(id,class_id) ON DELETE CASCADE,
 FOREIGN KEY(skill_id,class_id) REFERENCES skills(id,class_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS agent_materials (
 agent_id INTEGER NOT NULL,
 material_id INTEGER NOT NULL,
 class_id INTEGER NOT NULL,
 PRIMARY KEY(agent_id,material_id),
 FOREIGN KEY(agent_id,class_id) REFERENCES agents(id,class_id) ON DELETE CASCADE,
 FOREIGN KEY(material_id,class_id) REFERENCES materials(id,class_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS conversations (
 id INTEGER PRIMARY KEY,
 owner_id INTEGER NOT NULL,
 class_id INTEGER NOT NULL,
 agent_id INTEGER NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(owner_id,class_id) REFERENCES users(id,class_id),
 FOREIGN KEY(agent_id,class_id) REFERENCES agents(id,class_id)
);
CREATE INDEX IF NOT EXISTS idx_conversations_owner ON conversations(owner_id,class_id);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY,
 conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 turn_id TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('user','assistant')),
 content TEXT NOT NULL DEFAULT '',
 sources TEXT NOT NULL DEFAULT '[]',
 status TEXT NOT NULL CHECK(status IN ('generating','completed','failed','partial')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id,id);
"""
