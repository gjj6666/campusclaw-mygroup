from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    s = c.skill()
    status,data=c.request('/api/skills/'+str(s['id']),'PUT',{'content':s['content'].replace('启用：是','启用：否')})
    assert status == 200 and data['skill']['enabled'] is False
    assert c.row('skills',s['id'])['enabled'] == 0
    assert c.request('/api/skills/'+str(s['id']),'PUT',{'content':s['content']},'student')[0] == 403


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
