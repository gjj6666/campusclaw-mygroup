def run(c):
    root = '/api/prompt-templates'
    assert c.request(root, auth=None)[0] == 401
    assert c.request(root, auth='student')[0] == 403
    templates = c.request(root)[1]['templates']
    assert len(templates) == 3 and all(item['source'] == 'builtin' for item in templates)
    body = {'name': '本班模板', 'description': '物理引导', 'content': '你是{{subject}}老师，目标{{goal}}', 'class_id': 2}
    assert c.request(root, 'POST', body, 'student')[0] == 403
    status, data = c.request(root, 'POST', body)
    assert status == 201
    template = data['template']; path = f"{root}/{template['id']}"
    assert c.request(path, auth='other') == c.request(root + '/999999', auth='other') == (404, {'error': 'not_found'})
    assert c.request(root, 'POST', body)[0] == 400
    for verb in ('PUT', 'DELETE'):
        assert c.request(path, verb, {}, 'student')[0] == 403
    render = {'source': 'custom', 'id': template['id'], 'variables': {'subject': '物理', 'goal': '受力分析'}}
    status, data = c.request(root + '/render', 'POST', render)
    assert status == 200 and data['prompt'] == '你是物理老师，目标受力分析'
    agent = c.agent(prompt=data['prompt'])
    assert c.request(root + '/render', 'POST', {**render, 'variables': {} })[0] == 400
    assert c.request(path, 'PUT', {'content': '{{subject.__class__}}'})[0] == 400
    assert c.request(path, 'PUT', {'content': '新角色'})[0] == 200
    assert c.row('agents', agent['id'])['prompt'] == '你是物理老师，目标受力分析'
    assert c.request(path, 'DELETE')[0] == 200
    assert c.request(path)[0] == 404
