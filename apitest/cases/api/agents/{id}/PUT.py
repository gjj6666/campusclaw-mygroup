from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    a = c.agent()
    path = '/api/agents/'+str(a['id'])
    status, data = c.request(path,'PUT',{'prompt':' ','enabled':False})
    assert status == 200 and data['agent']['prompt'] == '' and data['agent']['effective_prompt']
    assert c.row('agents',a['id'])['enabled'] == 0
    assert c.request(path,'PUT',{'name':'bad','material_ids':[999]})[0] == 404
    assert c.row('agents',a['id'])['name'] == a['name']
    assert c.request(path,'PUT',{'prompt':'x'*2001})[0] == 400


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
