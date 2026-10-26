## Why

当前登录成功后仅通过 Cookie 传递签名会话，接口客户端无法取得并以 Bearer token 调用受保护接口。项目需要明确的 token 登录契约，使浏览器和接口调用方使用同一套基于 `Authorization` 头的身份校验方式。

## What Changes

- 账号密码校验成功后，`POST /api/login` 返回有期限的访问 token、类型、有效期和必要的用户信息；错误凭据不签发 token。
- 受保护接口从 `Authorization: Bearer <token>` 识别身份，并由服务端可信身份确定角色和班级。
- **BREAKING**：停止依赖 `campusclaw_session` Cookie 完成接口认证；只携带旧 Cookie 的请求不再获得授权。
- 浏览器登录页通过接口获取 token，后续材料查看和上传请求携带 Bearer token；token 过期或无效时回到登录页。受保护数据不得在未验证 token 的页面响应中泄露。
- 更新测试和使用文档，明确 token 获取、携带、过期及迁移行为。

## Capabilities

### New Capabilities

- `identity-access-control`：在现有未归档的身份规约基础上补充 Bearer token 签发、验证、浏览器使用及旧 Cookie 迁移要求。当前主规格目录尚无已归档能力，此路径沿用 `add-secure-login-class-materials` 中的同名能力。

### Modified Capabilities

- 无；主规格目录目前没有已归档的身份能力。

## Impact

- 涉及 `campusclaw/web.py` 的登录、路由守卫和页面交互，`campusclaw/security.py` 的令牌验证，必要时涉及配置和用户身份查询。
- 涉及 `POST /api/login`、材料读取及上传接口的认证契约；现有 HTML 页面需要改为由浏览器持 token 调用接口。
- 涉及 `tests/test_web.py`、`tests/test_security.py` 与 README 中的登录示例。
- 与活动变更 `add-secure-login-class-materials` 的账号密码及服务端授权要求保持一致；本变更仅迁移 token 传输与消费方式，不改变密码哈希、角色和班级隔离规则。
