from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    m=c.material(); path='/materials/'+str(m['id'])
    status,data=c.request(path,auth='student')
    assert status == 200 and data['material']['subject'] == c.row('materials',m['id'])['subject']
    content=c.app.conn.execute('SELECT content FROM knowledge_entries WHERE material_id=?',(m['id'],)).fetchone()[0]
    assert data['material']['content'] == content
    assert c.request(path,auth='other') == c.request('/materials/999999',auth='other')


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
