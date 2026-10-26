from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    m = c.material()
    status, data = c.request('/api/ask', 'POST', {'question':'牛顿第一定律'}, 'student')
    assert status == 200 and '[S1]' in data['answer'] and data['sources'][0]['material_id'] == m['id']
    assert c.row('knowledge_chunks', data['sources'][0]['id'])['content'] == data['sources'][0]['content']
    empty = c.request('/api/ask', 'POST', {'question':'牛顿第一定律'}, 'other')[1]
    assert empty == {'status':'no_evidence','answer':'','sources':[]}
    c.evidence.append('旧单次问答有依据引用；无依据仍为空且不生成')


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
