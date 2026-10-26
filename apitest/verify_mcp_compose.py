"""Real Compose + gateway verification. Reads .env; writes only selected evidence."""
import json
import argparse
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from campusclaw.config import load_dotenv
from campusclaw.skills import GUIDANCE_EXAMPLE
from campusclaw.mcp_client import McpClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-model-unavailable', action='store_true', help='记录模型失败，仍验收真实 MCP 链路；不宣称模型通过')
    parser.add_argument('--platform', action='store_true', help='同时验证三个内置应用、模板预览和技能上传')
    args = parser.parse_args()
    load_dotenv()
    base = os.environ.get('CAMPUSCLAW_TEST_URL', 'http://127.0.0.1:8000')
    evidence = []
    model_completed = True
    direct = McpClient('http://127.0.0.1:8090', os.environ['MCP_AUTH_TOKEN'])
    with urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=3) as response:
        assert response.status == 200
    discovered = direct.discover()
    conversion = direct.call('unit_convert', '100 cm to m')
    assert '= 1 m' in conversion
    assert direct.call('formula_hint', '牛顿第二定律的力和加速度')
    evidence.append({'stage': '独立 MCP health/list/call', 'tools': [tool['name'] for tool in discovered], 'conversion': conversion})

    def request(path, method='GET', body=None, token=None):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(base + path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            response = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())
        with response:
            if response.headers.get('Content-Type', '').startswith('text/event-stream'):
                frames, event = [], ''
                for line in response:
                    value = line.decode().strip()
                    if value.startswith('event: '): event = value[7:]
                    if value.startswith('data: '): frames.append((event, json.loads(value[6:])))
                return response.status, frames
            return response.status, json.loads(response.read())

    def login(username, password):
        status, result = request('/api/login', 'POST', {'username': username, 'password': password})
        assert status == 200, '演示账号登录失败；核对现有数据库与 .env 的演示密码'
        return result['access_token']

    teacher = login('teacher_a', os.environ['DEMO_TEACHER_PASSWORD'])
    student = login('student_a', os.environ['DEMO_STUDENT_PASSWORD'])
    role = ''
    if args.platform:
        status, result = request('/api/apps', token=student)
        assert status == 200 and len([app for app in result['apps'] if app['source'] == 'builtin']) == 3
        for key in ('course-qa', 'guided-solving', 'study-plan'):
            status, result = request(f'/api/apps/{key}/launch', 'POST', {}, student)
            assert status == 201
            evidence.append({'stage': '内置应用启动', 'key': key, 'conversation_id': result['conversation']['id']})
        assert len(request('/api/skill-library', token=teacher)[1]['skills']) == 3
        status, result = request('/api/prompt-templates/render', 'POST',
                                 {'source': 'builtin', 'key': 'guided-solving',
                                  'variables': {'subject': '物理', 'audience': '本班学生', 'goal': '理解受力分析'}}, teacher)
        assert status == 200 and '{{' not in result['prompt']
        role = result['prompt']
        evidence.append({'stage': '内置模板渲染', 'prompt': role})
    servers = request('/api/mcp/servers', token=teacher)[1]['servers']
    server = next((item for item in servers if item['name'] == 'campus-tools'), None)
    if server is None:
        status, result = request('/api/mcp/servers', 'POST', {'name': 'campus-tools', 'base_url': 'http://mcp-demo:8090',
                                                           'auth_token': os.environ['MCP_AUTH_TOKEN']}, teacher)
        assert status == 201
        server = result['server']
    assert server['base_url'] == 'http://mcp-demo:8090'
    path = f"/api/mcp/servers/{server['id']}"
    assert request(path + '/connect', 'POST', token=teacher)[0] == 200
    tools = request(path + '/tools', token=teacher)[1]['tools']
    assert {tool['name'] for tool in tools} == {'formula_hint', 'unit_convert'}
    evidence.append({'stage': 'Compose 实际发现', 'base_url': server['base_url'], 'tools': [t['reference'] for t in tools]})
    skill_name = '平台演示工具技能' if args.platform else '第6课公式提示'
    content = GUIDANCE_EXAMPLE.replace('名称：解题引导', '名称：' + skill_name).replace('knowledge_search', 'formula_hint@campus-tools')
    skills = request('/api/skills', token=teacher)[1]['skills']
    old = next((s for s in skills if s['name'] == skill_name), None)
    endpoint = f"/api/skills/{old['id']}" if old else '/api/skills/import' if args.platform else '/api/skills'
    status, result = request(endpoint, 'PUT' if old else 'POST',
                             {'content': content, **({'filename': 'platform-tools.md'} if not old and args.platform else {})}, teacher)
    assert status in (200, 201)
    skill = result['skill']
    agents = request('/api/agents', token=teacher)[1]['agents']
    agent_name = '平台综合验收应用' if args.platform else '第6课 MCP 助教'
    old_agent = next((a for a in agents if a['name'] == agent_name), None)
    endpoint = f"/api/agents/{old_agent['id']}" if old_agent else '/api/agents'
    status, result = request(endpoint, 'PUT' if old_agent else 'POST',
                             {'name': agent_name, 'skill_ids': [skill['id']], 'material_ids': [], 'subject': '通用',
                              **({'prompt': role} if args.platform else {})}, teacher)
    assert status in (200, 201)
    agent = result['agent']
    status, result = request('/api/conversations', 'POST', {'agent_id': agent['id']}, student)
    assert status == 201
    conv = result['conversation']['id']
    for expected in ('ok', 'denied'):
        if expected == 'denied':
            assert request(path + '/disconnect', 'POST', token=teacher)[0] == 200
            assert request(path + '/tools', token=teacher)[1]['tools'] == []
            assert request(f"/api/skills/{skill['id']}", 'PUT', {'content': content}, teacher)[0] == 400
        status, frames = request(f'/api/conversations/{conv}/messages', 'POST', {'question': '牛顿第二定律解题：如何根据质量和加速度分析力？'}, student)
        assert status == 200 and frames[0][0] == 'meta', '真实流式没有 meta'
        assert frames[0][1]['tool_calls'][0]['status'] == expected
        evidence.append({'stage': '学生真实流式', 'expected': expected, 'meta': frames[0][1],
                         'events': [event for event, _ in frames],
                         'answer': ''.join(data['text'] for event, data in frames if event == 'delta')})
        model_completed = model_completed and frames[-1][0] == 'done'
    audits = request('/api/mcp/audits', token=teacher)[1]['audits']
    selected = [row for row in audits if row['conversation_id'] == conv]
    assert {row['status'] for row in selected} == {'ok', 'denied'}
    evidence.append({'stage': '审计', 'audits': selected})
    assert request('/health')[0] == 200
    assert request('/api/search?q=newton&mode=keyword', token=student)[0] == 200
    if args.platform:
        status, data = request('/api/search?q=newton&mode=keyword', token=student)
        evidence.append({'stage': '知识库关键词接口', 'status': status, 'results_count': len(data['results']),
                         'note': '无命中不等于真实有资料检索通过；完整带资料链路另见隔离接口报告'})
    # Leave a usable discovered server and sample skill for the teacher to inspect.
    assert request(path + '/connect', 'POST', token=teacher)[0] == 200
    target = Path('apitest/reports/platform-compose.json' if args.platform else 'apitest/reports/week06-compose.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS real Compose MCP, SSE meta, disconnect denied, audit; report:', target)
    print('Real model completed:', model_completed)
    if not args.allow_model_unavailable:
        assert model_completed, '真实模型生成未完成；查看报告，MCP 结果与模型状态分别记录'


if __name__ == '__main__':
    main()
