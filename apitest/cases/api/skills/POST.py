from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

from campusclaw.skills import GUIDANCE_EXAMPLE

def run(c):
    s = c.skill()
    assert c.row('skills',s['id'])['body'] == s['body'] and '最终答案' in s['body']
    assert c.request('/api/skills','POST',{'content':GUIDANCE_EXAMPLE})[0] == 400
    for content in (GUIDANCE_EXAMPLE.replace('knowledge_search','shell'),'名称：重复\n'+GUIDANCE_EXAMPLE,GUIDANCE_EXAMPLE.split('\n\n')[0]):
        status, data = c.request('/api/skills','POST',{'content':content})
        assert status == 400 and data['message']
    assert c.app.conn.execute('SELECT count(*) FROM skills').fetchone()[0] == 1


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
