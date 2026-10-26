from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    a=c.agent(); conv=c.conversation(a)
    assert c.row('conversations',conv['id'])['agent_id'] == a['id']
    missing=c.request('/api/conversations','POST',{'agent_id':99999},'student')
    for body,who in (({},'student'),({'agent_id':a['id']},'other')):
        assert c.request('/api/conversations','POST',body,who) == missing
    c.request('/api/agents/'+str(a['id']),'PUT',{'enabled':False})
    assert c.request('/api/conversations','POST',{'agent_id':a['id']},'student') == missing
    assert c.app.conn.execute('SELECT count(*) FROM conversations').fetchone()[0] == 1


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
