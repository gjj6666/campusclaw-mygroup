from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    a = c.agent()
    status, data = c.request('/api/agents/'+str(a['id']))
    assert status == 200 and data['agent']['name'] == c.row('agents',a['id'])['name']
    assert c.request('/api/agents/'+str(a['id']), auth='other') == c.request('/api/agents/999999', auth='other')


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
