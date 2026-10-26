"""Reusable private files plus teacher policy and administration HTTP contract."""
from apitest.mcp_support import DemoMcp


def run(c):
    agent=c.agent();conv=c.conversation(agent);other=c.conversation(agent)
    status,data=c.request('/api/personal-materials','POST',dict(filename='private.md',content='# 我的笔记\n三角形内角和为180度。',subject='数学'),'student')
    assert status==201
    identity=data['material']['id'];ref=dict(source='personal',id=identity)
    for auth in ('teacher','peer','other'):
        assert c.request(f'/api/personal-materials/{identity}',auth=auth)==(404,{'error':'not_found'})
        assert c.request('/api/personal-materials',auth=auth)[1]['materials']==[]
    status,frames=c.request(f"/api/conversations/{other['id']}/messages",'POST',dict(question='请根据笔记解释内角和',context=dict(skill=None,materials=[ref])),'student')
    assert status==200 and frames[-1][0]=='done'
    assert frames[0][1]['sources'][0]['kind']=='personal'
    assert c.request('/api/conversations',auth='student')[1]['conversations'][0]['title']=='请根据笔记解释内角和'
    status,data=c.request(f"/api/conversations/{conv['id']}/attachments",'POST',dict(kind='material',filename='old.txt',content='旧会话资料'),'student')
    attachment=data['attachment']['id']
    source=dict(source=dict(kind='attachment',id=attachment,conversation_id=conv['id']))
    copy=c.request('/api/personal-materials','POST',source,'student')[1]['material']
    assert c.request('/api/personal-materials','POST',source,'student')[1]['material']['id']==copy['id']
    assert c.request(f"/api/conversations/{other['id']}/attachments/{attachment}",auth='student')[0]==404
    for path in ('/api/admin/students','/api/admin/materials','/api/admin/index-policy'):
        assert c.request(path,auth='student')[0]==403
        assert c.request(path)[0]==200
    assert all(set(row)=={'id','username'} for row in c.request('/api/admin/students')[1]['students'])
    material=c.material('alpha '+('paragraph line。\n'*90))
    assert c.request(f"/api/library/materials/{material['id']}",auth='other')[0]==404
    assert c.request('/api/admin/index-policy','PUT',dict(mode='custom',size=100,ratio=10,separator='newline',trim=True))[0]==200
    before=c.app.conn.execute('SELECT COUNT(*) FROM knowledge_chunks').fetchone()[0]
    status,preview=c.request('/api/admin/index-policy/preview','POST',dict(material_id=material['id']))
    assert status==200 and preview['total']>1
    assert c.app.conn.execute('SELECT COUNT(*) FROM knowledge_chunks').fetchone()[0]==before
    assert c.request('/api/admin/materials')[1]['materials'][0]['needs_reindex']
    assert c.request(f"/api/admin/materials/{material['id']}/reindex",'POST',auth='other')[0]==404
    status,result=c.request(f"/api/admin/materials/{material['id']}/reindex",'POST')
    assert status==200 and result['index_status']=='ready'
    assert not c.request('/api/admin/materials')[1]['materials'][0]['needs_reindex']
    with DemoMcp() as remote:
        s=c.request('/api/mcp/servers','POST',dict(name='editable',base_url=remote.url,auth_token=remote.token))[1]['server'];path=f"/api/mcp/servers/{s['id']}"
        assert c.request(path+'/connect','POST')[0]==200
        assert c.request(path,'PUT',dict(auth_token=''))[1]['server']['status']=='connected'
        assert c.request(path,'PUT',dict(name='bad'))[0]==400
        assert c.request(path,'PUT',dict(base_url=remote.url+'/new'))[1]['server']['status']=='disconnected'
        assert c.request(path+'/tools')[1]['tools']==[]
        assert c.request(path,'PUT',dict(base_url=remote.url),auth='other')[0]==404
        assert c.request(path,'DELETE',auth='student')[0]==403
        assert c.request(path,'DELETE')[0]==200
        assert c.request('/api/mcp/servers')[1]['servers']==[]
    c.evidence.append(dict(personal='本人跨会话可复用',old_attachments='原会话边界保留',policy='预览无写入，重建真实ready',students='只读脱敏'))
