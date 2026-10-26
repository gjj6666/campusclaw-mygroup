from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    s,m=c.skill(),c.material(); a=c.agent(skill_ids=[s['id']],material_ids=[m['id']],subject='物理')
    conv=c.conversation(a); path='/api/conversations/'+str(conv['id'])+'/messages'
    status,frames=c.request(path,'POST',{'question':'牛顿第一定律如何解题','class_id':2},'student')
    assert status == 200 and frames[0][0] == 'meta' and frames[-1][0] == 'done'
    meta=frames[0][1]; assert meta['skill']['id'] == s['id'] and meta['sources'][0]['material_id'] == m['id']
    parts=[d['text'] for e,d in frames if e=='delta']; assert len(parts)>1
    row=c.row('messages',meta['message_id']); assert row['content']==''.join(parts) and row['status']=='completed'
    assert c.model.requests[-1]['stream'] is True
    c.request('/api/skills/'+str(s['id']),'PUT',{'content':s['content'].replace('启用：是','启用：否')})
    frames=c.request(path,'POST',{'question':'牛顿第一定律如何解题'},'student')[1]
    assert frames[0][1]['skill'] is None
    assert c.request(path,'POST',{'question':'x'},'student')[0] == 400
    c.evidence.append('多次真实HTTP增量与数据库正文一致；技能禁用原会话立即生效')


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
