from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    m = c.material()
    status, data = c.request('/api/search?q=%E7%89%9B%E9%A1%BF&mode=keyword&class_id=2', auth='student')
    assert status == 200 and data['results']
    source = data['results'][0]
    row = c.row('knowledge_chunks', source['id'])
    assert row['material_id'] == m['id'] and row['content'] == source['content']
    assert c.request('/api/search?q=%E7%89%9B%E9%A1%BF&mode=keyword', auth='other')[1]['results'] == []
    assert c.request('/api/search?q=alpha', auth=None)[0] == 401
    c.evidence.append('来源正文/材料与数据库一致；跨班词命中为空')


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
