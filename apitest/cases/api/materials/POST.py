from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    m=c.material()
    row=c.row('materials',m['id'])
    assert row['subject'] == m['subject'] == '物理' and row['class_id'] == 1
    assert m['index_status'] == 'ready'
    assert c.request('/api/materials','POST',{'filename':'bad.txt','content':'bad'},'student')[0] == 403
    assert c.app.conn.execute('SELECT count(*) FROM materials').fetchone()[0] == 1


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
