from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    s = c.skill()
    path='/api/skills/'+str(s['id'])
    assert c.request(path)[1]['skill']['conditions'] == c.row('skills',s['id'])['conditions']
    assert c.request(path,auth='other') == c.request('/api/skills/999999',auth='other')


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
