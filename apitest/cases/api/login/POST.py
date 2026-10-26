from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(next(parent for parent in Path(__file__).resolve().parents if (parent / 'campusclaw').is_dir())))

def run(c):
    status, data = c.request('/api/login', 'POST', {'username':'student','password':c.password}, auth=None)
    assert status == 200 and data['token_type'] == 'Bearer' and data['expires_in'] == 3600
    row = c.row('users', data['user']['id'])
    assert row['class_id'] == data['user']['class_id'] and row['role'] == 'student'
    assert row['password_hash'] != c.password and 'password_hash' not in data['user']
    assert c.request('/api/login', 'POST', {'username':'student','password':'wrong'}, auth=None)[0] == 401
    c.evidence.append('登录字段与数据库账号一致；错误密码无令牌')


if __name__ == '__main__':
    from apitest.support import Context
    context = Context()
    try:
        run(context)
        print('PASS ' + Path(__file__).name)
    finally:
        context.close()
