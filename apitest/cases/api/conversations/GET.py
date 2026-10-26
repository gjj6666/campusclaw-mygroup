from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    conv=c.conversation()
    status,data=c.request('/api/conversations',auth='student')
    assert status == 200 and data['conversations'][0]['owner_id'] == c.row('conversations',conv['id'])['owner_id']
    assert c.request('/api/conversations',auth='peer')[1]['conversations'] == []


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
