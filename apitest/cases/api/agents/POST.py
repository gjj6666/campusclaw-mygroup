from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    skill, material = c.skill(), c.material()
    a = c.agent(prompt='耐心指导', skill_ids=[skill['id']], material_ids=[material['id']])
    row = c.row('agents', a['id'])
    assert row['prompt'] == a['prompt'] == '耐心指导'
    assert c.app.conn.execute('SELECT skill_id FROM agent_skills WHERE agent_id=?',(a['id'],)).fetchone()[0] == skill['id']
    before = c.app.conn.execute('SELECT count(*) FROM agents').fetchone()[0]
    assert c.request('/api/agents','POST',{'name':'bad'},'student')[0] == 403
    assert c.request('/api/agents','POST',{'name':'x'*65})[0] == 400
    assert c.app.conn.execute('SELECT count(*) FROM agents').fetchone()[0] == before


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
