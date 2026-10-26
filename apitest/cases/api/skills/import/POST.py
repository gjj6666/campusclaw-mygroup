from campusclaw.skills import GUIDANCE_EXAMPLE


def run(c):
    assert c.request('/api/skill-library', auth='student')[0] == 403
    assert len(c.request('/api/skill-library')[1]['skills']) == 3
    for path, body in (('/api/skills/install', {'builtin_key': 'study-plan'}),
                       ('/api/skills/import', {'filename': 'x.md', 'content': GUIDANCE_EXAMPLE})):
        assert c.request(path, 'POST', body, 'student')[0] == 403
    status, installed = c.request('/api/skills/install', 'POST', {'builtin_key': 'study-plan'})
    assert status == 200
    assert c.request('/api/skills/install', 'POST', {'builtin_key': 'study-plan'})[1] == installed
    for body in ({'filename': 'x.py', 'content': GUIDANCE_EXAMPLE}, {'filename': '../x.md', 'content': GUIDANCE_EXAMPLE},
                 {'filename': 'x.md', 'content': 'missing fields'}, {'filename': 'x.md', 'content': '\ud800'}):
        assert c.request('/api/skills/import', 'POST', body)[0] == 400
    status, result = c.request('/api/skills/import', 'POST', {'filename': 'lesson.md', 'content': GUIDANCE_EXAMPLE})
    assert status == 201 and result['skill']['name'] == '解题引导'
    assert c.request('/api/skills/install', 'POST', {'builtin_key': 'guided-solving'})[0] == 409
    assert c.app.conn.execute('SELECT count(*) FROM skills').fetchone()[0] == 2
