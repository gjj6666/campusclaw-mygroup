from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    status,data=c.request('/openapi.json',auth=None)
    assert status == 200 and data['openapi'] == '3.0.3'
    assert data['paths']['/api/login']['post']['security'] == []
    assert '403' in data['paths']['/api/agents']['post']['responses']
    for path in ('/api/apps', '/api/apps/{key}/launch', '/api/prompt-templates', '/api/prompt-templates/render',
                 '/api/skill-library', '/api/skills/install', '/api/skills/import'):
        assert path in data['paths']
    launch = data['paths']['/api/apps/{key}/launch']['post']
    assert launch['parameters'][0]['schema']['type'] == 'string'
    assert '403' in data['paths']['/api/prompt-templates/render']['post']['responses']
    for path in ('/api/conversations/{id}/context', '/api/conversations/{id}/attachments',
                 '/api/conversations/{id}/attachments/{attachment_id}'):
        assert path in data['paths']
    upload = data['paths']['/api/conversations/{id}/attachments']['post']
    assert '403' not in upload['responses'] and '404' in upload['responses']
    send = data['paths']['/api/conversations/{id}/messages']['post']
    assert 'context' in send['requestBody']['content']['application/json']['schema']['properties']
    assert 'context' in send['x-sse-events']['meta']['properties']
    for path in ('/api/me','/api/personal-materials','/api/personal-materials/{id}',
                 '/api/library/materials','/api/admin/students','/api/admin/materials',
                 '/api/admin/materials/{id}/reindex','/api/admin/index-policy','/api/admin/index-policy/preview'):
        assert path in data['paths']
    assert 'put' in data['paths']['/api/mcp/servers/{id}'] and 'delete' in data['paths']['/api/mcp/servers/{id}']
    material_ref=send['requestBody']['content']['application/json']['schema']['properties']['context']['properties']['materials']['items']
    assert 'personal' in material_ref['properties']['source']['enum']
    assert c.app.conn.execute('SELECT count(*) FROM agents').fetchone()[0] == 0


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
