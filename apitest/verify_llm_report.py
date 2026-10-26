"""Reproduce sanitized LLM request evidence without modifying application behavior.

Isolated app/DB; deterministic embedding/vector and HTTP model fixtures.
MCP calls use the real Compose demo. --live additionally probes configured LLM.
Never persist credentials, provider URLs, or personal data.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import urllib.request
from dataclasses import replace
from http.server import BaseHTTPRequestHandler
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apitest import support
from campusclaw.config import Config
from campusclaw.gateway import ChatClient, EmbeddingClient
from campusclaw.mcp_client import McpClient


class RecordingModel(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(payload)
        source = '[S1]' in payload['messages'][-1]['content']
        pieces = ['请先列出已知量。', '再考虑合力、质量与加速度的关系。']
        if source:
            pieces.append('[S1]')
        frames = [{'choices': [{'delta': {'content': s}, 'finish_reason': None}]} for s in pieces]
        frames.append({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})
        wire = ''.join('data: '+json.dumps(f, ensure_ascii=False)+'\n\n' for f in frames)+'data: [DONE]\n\n'
        self.server.traces.append(dict(method='POST', path=self.path,
            headers={'Content-Type':self.headers.get('Content-Type'),
                     'Accept':self.headers.get('Accept'), 'Authorization':'Bearer [REDACTED]'},
            request=payload, response_status=200, response_content_type='text/event-stream',
            response_wire=wire, assembled_answer=''.join(pieces)))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        self.wfile.write(wire.encode('utf-8'))
        self.wfile.flush()


def run(live=False):
    result = dict(repository='https://github.com/gjj6666/campusclaw-mygroup',
        environment={'app':'isolated production handlers / temporary DB',
          'model':'deterministic local HTTP fixture (not a real LLM)',
          'embedding_vectors':'deterministic test doubles',
          'mcp':'real Compose HTTP service at localhost:8090'}, cases=[])
    with patch.object(support, 'ModelHandler', RecordingModel):
        c = support.Context()
    c.app.config = replace(c.config, max_upload_bytes=100000)
    c.model.traces = []
    rpc_traces = []
    original_rpc = McpClient.rpc

    def rpc(client, method, params=None, **kwargs):
        value = original_rpc(client, method, params, **kwargs)
        rpc_traces.append({'method':method,'params':params or {}, 'result':value})
        return value

    def checked(path, method='GET', data=None, role='teacher', expected=200):
        status, value = c.request(path, method, data, role)
        assert status == expected, (path,status,value)
        return value

    def send(label, conv, question, context=None):
        start = len(c.model.traces)
        data = {'question':question}
        if context is not None:
            data['context'] = context
        frames = checked(f"/api/conversations/{conv['id']}/messages", 'POST', data, 'student')
        assert frames[-1][0] == 'done', frames
        assert len(c.model.traces) == start+1
        case = dict(id=label, app_request=data, app_events=frames, llm=c.model.traces[-1])
        result['cases'].append(case)
        return case

    try:
        result['catalog'] = checked('/api/apps')['apps']
        assert sum(x['source']=='builtin' for x in result['catalog']) == 3
        template = checked('/api/prompt-templates')['templates'][0]
        values = {'subject':'物理','audience':'高一学生','goal':'理解牛顿第二定律'}
        rendered = checked('/api/prompt-templates/render','POST',
            {'source':'builtin','key':template['key'],'variables':values})['prompt']
        agent = c.agent(name='验证助手', prompt=rendered)
        conv = c.conversation(agent)
        plain = send('T01_template',conv,'牛顿第二定律是什么？')
        assert rendered in plain['llm']['request']['messages'][0]['content']
        assert '{{' not in plain['llm']['request']['messages'][0]['content']
        result['template'] = dict(raw=template['content'],variables=values,rendered=rendered)
        second = send('T02_history',conv,'继续说明力与加速度的关系。')
        assert [m['role'] for m in second['llm']['request']['messages']] == ['system','user','assistant','user']

        content = '\n\n'.join(f'第{i}段：牛顿第二定律描述合力、质量和加速度。F=ma。'+('测量质量和加速度，检查方向与单位。'*15) for i in range(8))+'\nKB_TAIL_NOT_SENT'
        material = c.material(content)
        unbound = c.material('UNBOUND_MATERIAL_NOT_SENT：这份资料没有绑定。牛顿第二定律。')
        checked(f"/api/agents/{agent['id']}",'PUT',{'material_ids':[material['id']]})
        kb = send('T03_knowledge',c.conversation(agent),'牛顿第二定律中合力与加速度有什么关系？')
        meta = kb['app_events'][0][1]
        chunks = c.app.conn.execute('SELECT COUNT(*) FROM knowledge_chunks WHERE material_id=?',(material['id'],)).fetchone()[0]
        message = kb['llm']['request']['messages'][-1]['content']
        assert 0 < len(meta['sources']) <= 4 < chunks
        assert 'KB_TAIL_NOT_SENT' not in message and 'UNBOUND_MATERIAL_NOT_SENT' not in message
        assert content not in message
        kb['checks'] = {'document_chars':len(content),'indexed_chunks':chunks,
            'sent_chunks':len(meta['sources']),'sent_source_chars':sum(len(s['content']) for s in meta['sources']),
            'entire_document_sent':False,'unbound_material_sent':False}
        result['knowledge_fixture'] = {'bound_material_id':material['id'],'unbound_material_id':unbound['id'],'content':content}

        skill_text = '名称：物理引导验证\n适用条件：牛顿 合力 加速度\n启用：是\n工具：knowledge_search\n\n先要求学生列出质量和加速度。逐句解释合力，不直接给最终结果。SKILL_BODY_END'
        uploaded = checked('/api/skills/import','POST',{'filename':'physics.md','content':skill_text}, expected=201)['skill']
        checked('/api/skills/install','POST',{'builtin_key':'guided-solving'})
        checked(f"/api/agents/{agent['id']}",'PUT',{'skill_ids':[uploaded['id']],'material_ids':[]})
        skill_case = send('T04_shared_skill',c.conversation(agent),'牛顿第二定律如何解题？')
        system = skill_case['llm']['request']['messages'][0]['content']
        assert uploaded['body'] in system and skill_text not in system
        assert '名称：物理引导验证' not in system
        result['skill_fixture'] = {'file':skill_text,'parsed_body':uploaded['body']}
        miss = send('T05_skill_not_matched',c.conversation(agent),'请谈谈诗歌意象。')
        assert 'SKILL_BODY_END' not in miss['llm']['request']['messages'][0]['content']

        private_conv = c.conversation(agent)
        private = checked(f"/api/conversations/{private_conv['id']}/attachments",'POST',
            {'kind':'skill','filename':'private.md','content':skill_text},'student',201)['attachment']
        private_material = checked('/api/personal-materials','POST',
            {'filename':'personal.md','content':'PERSONAL_BEGIN 这是本人手动加入的完整笔记。PERSONAL_END','subject':'物理'},'student',201)['material']
        private_case = send('T06_private_context',private_conv,'按我的笔记和技能说明牛顿第二定律。',
            {'skill':{'source':'upload','id':private['id']},'materials':[{'source':'personal','id':private_material['id']}]})
        pm = private_case['llm']['request']['messages']
        assert uploaded['body'] not in pm[0]['content'] and uploaded['body'] in pm[-1]['content']
        assert 'PERSONAL_BEGIN' in pm[-1]['content'] and 'PERSONAL_END' in pm[-1]['content']

        Config.from_env()
        token = os.environ.get('MCP_AUTH_TOKEN')
        if not token:
            raise RuntimeError('Local MCP_AUTH_TOKEN required; never printed')
        with patch.object(McpClient, 'rpc', rpc):
            server = checked('/api/mcp/servers','POST',
                {'name':'report-tools','base_url':'http://127.0.0.1:8090','auth_token':token},expected=201)['server']
            connected = checked(f"/api/mcp/servers/{server['id']}/connect",'POST',{})
            result['mcp_discovery'] = connected
            tool_skill = c.skill('名称：MCP公式验证\n适用条件：牛顿 合力 公式\n启用：是\n工具：formula_hint@report-tools\n\n先参考公式工具的数据，再引导学生列式。')
            checked(f"/api/agents/{agent['id']}",'PUT',{'skill_ids':[tool_skill['id']],'material_ids':[]})
            tool_conv = c.conversation(agent)
            tool = send('T07_mcp_ok',tool_conv,'牛顿第二定律的公式是什么？')
            req = tool['llm']['request']
            assert set(req)=={'model','messages','stream'} and 'tools' not in req and 'tool_choice' not in req
            assert 'formula_hint@report-tools' in req['messages'][-1]['content']
            assert tool['app_events'][0][1]['tool_calls'][0]['status']=='ok'
            checked(f"/api/mcp/servers/{server['id']}/disconnect",'POST',{})
            denied = send('T08_mcp_denied',tool_conv,'继续用牛顿公式引导我。')
            assert denied['app_events'][0][1]['tool_calls'][0]['status']=='denied'
            assert '"status": "denied"' in denied['llm']['request']['messages'][-1]['content']
            result['mcp_audits'] = checked('/api/mcp/audits')['audits']
        result['mcp_rpc'] = rpc_traces
        result['http_evidence'] = c.evidence

        if live:
            config = Config.from_env()
            original = urllib.request.urlopen
            result['real_llm_cases'] = []
            for case in result['cases']:
                trace = {'case':case['id'],'environment':'configured real provider; keys and URL not recorded',
                         'response_chunks':[],'response_wire':''}
                class ObservedResponse:
                    def __init__(self,response):
                        self.response=response
                    def __enter__(self):
                        self.response.__enter__()
                        return self
                    def __exit__(self,*args):
                        return self.response.__exit__(*args)
                    def __iter__(self):
                        for line in self.response:
                            trace['response_wire']+=line.decode('utf-8',errors='replace')
                            yield line
                def record(request,*args,**kwargs):
                    trace['request'] = json.loads(request.data)
                    trace['headers'] = {'Content-Type':request.get_header('Content-type'),
                        'Accept':request.get_header('Accept'),'Authorization':'Bearer [REDACTED]'}
                    trace['path_suffix']='/chat/completions'
                    response=original(request,*args,**kwargs)
                    trace['response_status']=response.status
                    return ObservedResponse(response)
                try:
                    with patch.object(urllib.request,'urlopen',record):
                        client = ChatClient(config.chat_base_url,config.chat_api_key,config.chat_model)
                        for part in client.stream(case['llm']['request']['messages']):
                            trace['response_chunks'].append(part)
                    trace['status']='completed'
                    trace['assembled_answer']=''.join(trace['response_chunks'])
                except Exception as exc:
                    trace['status']='failed'
                    trace['error_type']=type(exc).__name__
                    trace['cause_type']=type(exc.__cause__).__name__
                    cause=exc.__cause__
                    trace['reason_type']=type(getattr(cause,'reason',None)).__name__
                result['real_llm_cases'].append(trace)
                print('Real provider replay:',case['id'],trace['status'],flush=True)
            result['real_llm'] = result['real_llm_cases'][0]
            try:
                vector = EmbeddingClient(config.embedding_base_url,config.embedding_api_key,
                    config.embedding_model,config.embedding_dim).embed('牛顿第二定律 F=ma')
                result['real_embedding']={'status':'completed','dimension':len(vector)}
            except Exception as exc:
                result['real_embedding']={'status':'failed','error_type':type(exc).__name__,
                    'cause_type':type(exc.__cause__).__name__}
            from apitest.run_all import live_case
            live_context=support.Context(live=True)
            try:
                live_case(live_context)
                result['real_integration']={'status':'passed','evidence':live_context.evidence}
            except Exception as exc:
                result['real_integration']={'status':'failed','error_type':type(exc).__name__,
                    'evidence':live_context.evidence}
            finally:
                live_context.close()
        result['assertions']='passed'
        return result
    finally:
        c.close()


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--live',action='store_true')
    p.add_argument('--output',default='docs/verification/llm-traces.json')
    args=p.parse_args()
    result=run(args.live)
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS: 8 sanitized conversation traces; real MCP; '+str(target))
    if 'real_llm' in result:
        print('Real LLM:',result['real_llm']['status'],'; embedding:',result['real_embedding']['status'])
