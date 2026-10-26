from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    conv=c.conversation(); path='/api/conversations/'+str(conv['id'])+'/messages'
    c.request(path,'POST',{'question':'如何解题'},'student')
    status,data=c.request(path,auth='student')
    assert status == 200 and len(data['messages']) == 2
    for m in data['messages']:
        assert c.row('messages',m['id'])['content'] == m['content'] and m['status'] == 'completed'
    assert c.request(path,auth='peer') == c.request('/api/conversations/999999/messages',auth='peer')


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
