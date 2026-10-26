"""Dual-role uploads, private context, SSE, actual MCP and denial."""
import json
from apitest.mcp_support import DemoMcp


def run(c):
    agent = c.agent()
    conv = c.conversation(agent); base = f"/api/conversations/{conv['id']}"
    status, data = c.request(base + '/attachments', 'POST', dict(kind='material', filename='private.md', content='私人事实：三角形的内角和为180度。'), 'student')
    assert status == 201
    material = data['attachment']; mref = dict(source='upload', id=material['id'])
    for auth in ('teacher', 'peer', 'other'):
        assert c.request(base + '/attachments', auth=auth) == (404, {'error': 'not_found'})
        assert c.request(base + f"/attachments/{material['id']}", auth=auth) == (404, {'error': 'not_found'})
    other_conv = c.conversation(agent)
    assert c.request(f"/api/conversations/{other_conv['id']}/messages", 'POST', {'question': '问题如何处理', 'context': {'materials': [mref]}}, 'student')[0] == 404
    for data in ({'kind': 'material', 'filename': 'bad.pdf', 'content': 'text'}, {'kind': 'material', 'filename': 'bad.txt', 'content': 'x' * 12001}):
        assert c.request(base + '/attachments', 'POST', data, 'student')[0] == 400
    teacher_conv = c.request('/api/conversations', 'POST', {'agent_id': agent['id']})[1]['conversation']
    assert c.request(f"/api/conversations/{teacher_conv['id']}/attachments", 'POST', dict(kind='material', filename='teacher.txt', content='教师私有资料'))[0] == 201
    assert c.request('/api/skills', 'POST', {'content': 'bad'}, 'student')[0] == 403
    with DemoMcp() as remote:
        status, data = c.request('/api/mcp/servers', 'POST', {'name': 'attachment-tools', 'base_url': remote.url, 'auth_token': remote.token})
        server = f"/api/mcp/servers/{data['server']['id']}"
        assert c.request(server + '/connect', 'POST')[0] == 200
        content = '名称：私人提示\n适用条件：不会命中的关键词\n启用：是\n工具：formula_hint@attachment-tools\n\nPRIVATE_SKILL_MARKER 按步骤提示。'
        status, data = c.request(base + '/attachments', 'POST', dict(kind='skill', filename='skill.md', content=content), 'student')
        assert status == 201
        ref = dict(source='upload', id=data['attachment']['id'])
        for expected in ('ok', 'denied'):
            if expected == 'denied': assert c.request(server + '/disconnect', 'POST')[0] == 200
            status, frames = c.request(base + '/messages', 'POST', dict(question='如何计算三角形内角和？', context=dict(skill=ref, materials=[mref])), 'student')
            assert status == 200 and frames[-1][0] == 'done'
            meta = frames[0][1]
            assert meta['tool_calls'][0]['status'] == expected
            assert meta['context']['skill']['source'] == 'upload'
            assert meta['sources'][0]['kind'] == 'attachment'
            messages = c.model.requests[-1]['messages']
            assert 'PRIVATE_SKILL_MARKER' not in messages[0]['content']
            assert 'PRIVATE_SKILL_MARKER' in messages[-1]['content']
            assert remote.token not in json.dumps(frames)
        assert {a['status'] for a in c.request('/api/mcp/audits')[1]['audits']} == {'ok', 'denied'}
    history = c.request(base + '/messages', auth='student')[1]['messages']
    assert history[0]['context']['materials'][0]['id'] == material['id']
    assert c.request(base + '/context', auth='student')[1]['attachments']
    before = len(c.model.requests)
    assert c.request(base + '/messages', 'POST', dict(question='一个问题', context=dict(materials=[mref, mref])), 'student')[0] == 400
    assert len(c.model.requests) == before
    status, frames = c.request(base + '/messages', 'POST', dict(question='继续一个普通问题', context=dict(skill=None, materials=[])), 'student')
    assert status == 200 and frames[-1][0] == 'done' and not frames[0][1]['sources']
    assert c.row('agents', agent['id'])['prompt'] == ''
    c.evidence.append({'upload_roles': ['教师', '学生'], 'privacy': '本人原会话', 'MCP': ['ok', 'denied'], 'history_context': True})
