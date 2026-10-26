from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    conv=c.conversation(); path='/api/conversations/'+str(conv['id'])
    assert c.request(path,auth='student')[1]['conversation']['owner_id'] == c.row('conversations',conv['id'])['owner_id']
    for who in ('peer','other'):
        assert c.request(path,auth=who) == c.request('/api/conversations/999999',auth=who)


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
