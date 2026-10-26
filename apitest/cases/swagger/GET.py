from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    status, page = c.request('/swagger', auth=None)
    assert status == 200 and 'SwaggerUIBundle' in page and '/openapi.json' in page
    assert c.app.conn.execute('SELECT count(*) FROM conversations').fetchone()[0] == 0
    c.evidence.append('文档公开可读；不创建业务记录')


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
