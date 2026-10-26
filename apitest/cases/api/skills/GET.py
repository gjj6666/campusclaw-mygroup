from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    s = c.skill()
    status, data = c.request('/api/skills',auth='student')
    assert status == 200 and data['skills'][0]['content'] == c.row('skills',s['id'])['content']
    assert c.request('/api/skills',auth='other')[1]['skills'] == []


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
