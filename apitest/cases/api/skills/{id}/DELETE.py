from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    s = c.skill(); a=c.agent(skill_ids=[s['id']])
    status,data=c.request('/api/skills/'+str(s['id']),'DELETE')
    assert status == 200 and data['deleted'] == s['id'] and c.row('skills',s['id']) is None
    assert c.app.conn.execute('SELECT count(*) FROM agent_skills WHERE agent_id=?',(a['id'],)).fetchone()[0] == 0


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
