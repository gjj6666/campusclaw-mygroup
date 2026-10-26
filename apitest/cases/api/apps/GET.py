def run(c):
    assert c.request('/api/apps', auth=None)[0] == 401
    status, data = c.request('/api/apps', auth='student')
    assert status == 200 and len(data['apps']) == 3
    assert c.app.conn.execute('SELECT count(*) FROM agents').fetchone()[0] == 0
    assert c.request('/api/apps/missing/launch', 'POST', {}, 'student')[0] == 404
    assert c.request('/api/apps/course-qa/launch', 'POST', {'class_id': 2}, 'student')[0] == 400
    conversations = []
    for key in ('course-qa', 'guided-solving', 'study-plan'):
        status, data = c.request(f'/api/apps/{key}/launch', 'POST', {}, 'student')
        assert status == 201 and data['conversation']['class_id'] == 1
        conversations.append(data['conversation'])
    first = conversations[0]
    assert c.request(f"/api/conversations/{first['id']}", auth='peer')[0] == 404
    status, repeated = c.request('/api/apps/course-qa/launch', 'POST', {}, 'peer')
    assert status == 201 and repeated['conversation']['agent_id'] == first['agent_id']
    assert repeated['conversation']['owner_id'] != first['owner_id']
    assert c.request('/api/apps/course-qa/launch', 'POST', {}, 'other')[1]['conversation']['agent_id'] != first['agent_id']
    status, data = c.request(f"/api/agents/{first['agent_id']}", 'PUT', {'enabled': False, 'prompt': '教师角色快照'})
    assert status == 200
    assert c.request('/api/apps/course-qa/launch', 'POST', {}, 'student')[0] == 404
    custom = c.agent(name='本班自定义应用')
    assert any(item.get('agent_id') == custom['id'] for item in c.request('/api/apps')[1]['apps'])
    assert not any(item.get('agent_id') == custom['id'] for item in c.request('/api/apps', auth='other')[1]['apps'])
