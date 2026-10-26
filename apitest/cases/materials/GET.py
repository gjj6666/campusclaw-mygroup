from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    m=c.material()
    status,data=c.request('/materials',auth='student')
    assert status == 200 and data['materials'][0]['title'] == c.row('materials',m['id'])['title']
    assert c.request('/materials',auth='other')[1]['materials'] == []


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
