"""Additive platform schema; no existing configuration is seeded or overwritten."""
SCHEMA = """
CREATE TABLE IF NOT EXISTS prompt_templates (
 id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id),
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 64),
 description TEXT NOT NULL DEFAULT '' CHECK(length(description)<=500),
 content TEXT NOT NULL CHECK(length(content) BETWEEN 1 AND 2000),
 UNIQUE(class_id,name)
);
CREATE TABLE IF NOT EXISTS builtin_app_bindings (
 class_id INTEGER NOT NULL REFERENCES classes(id), builtin_key TEXT NOT NULL,
 agent_id INTEGER NOT NULL, PRIMARY KEY(class_id,builtin_key), UNIQUE(agent_id),
 FOREIGN KEY(agent_id,class_id) REFERENCES agents(id,class_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS builtin_skill_bindings (
 class_id INTEGER NOT NULL REFERENCES classes(id), builtin_key TEXT NOT NULL,
 skill_id INTEGER NOT NULL, PRIMARY KEY(class_id,builtin_key), UNIQUE(skill_id),
 FOREIGN KEY(skill_id,class_id) REFERENCES skills(id,class_id) ON DELETE CASCADE
);
"""
