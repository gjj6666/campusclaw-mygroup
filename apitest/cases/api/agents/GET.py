from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    a = c.agent()
    status, data = c.request('/api/agents', auth='student')
    assert status == 200 and [x['id'] for x in data['agents']] == [a['id']]
    assert data['agents'][0]['prompt'] == c.row('agents', a['id'])['prompt']
    assert c.request('/api/agents', auth='other')[1]['agents'] == []


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
