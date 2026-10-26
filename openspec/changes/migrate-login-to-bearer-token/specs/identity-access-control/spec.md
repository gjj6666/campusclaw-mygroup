## Purpose

本能力规定教师和学生通过账号密码取得限时访问令牌，并以 Bearer 方式访问班级材料；服务端以可信身份执行角色和班级授权，浏览器与接口调用方遵循相同的认证边界。

## ADDED Requirements

### Requirement: 账号密码换取访问令牌

系统 SHALL 在 `POST /api/login` 收到正确账号密码后返回 JSON，包含 `access_token`、`token_type`（值为 `Bearer`）、`expires_in`（秒）和不含密码的用户信息。系统 MUST 为令牌设置到期时间，且不得在响应中设置登录 Cookie 或泄露服务端密钥。

#### Scenario: 正确凭据取得令牌
- **WHEN** 教师或学生以 JSON 提交正确账号密码
- **THEN** 系统返回可用于 Bearer 认证的访问令牌、有效期和该用户的基本信息，且不设置 `campusclaw_session` Cookie

#### Scenario: 错误凭据不能取得令牌
- **WHEN** 用户提交不存在的账号或错误密码
- **THEN** 系统返回未授权响应，且响应中没有访问令牌或登录 Cookie

#### Scenario: 缺少签名密钥
- **WHEN** 必需的服务端令牌签名密钥未配置
- **THEN** 系统拒绝签发令牌，并返回配置不可用响应

### Requirement: Bearer 令牌认证与失效处理

受保护的数据读取及写入请求 MUST 从 `Authorization: Bearer <access_token>` 认证用户。系统 MUST 验证令牌完整性和到期时间，并以服务端可信用户记录确定角色及班级。缺失、格式错误、被篡改、过期或对应用户已不存在的令牌 MUST 被拒绝。只携带旧登录 Cookie 不得获得授权。

#### Scenario: 有效令牌访问本班数据
- **WHEN** 用户携带有效 Bearer 令牌请求材料列表或详情
- **THEN** 系统按该用户当前的服务端角色和班级授权，并仅返回其有权访问的材料

#### Scenario: 无效或过期令牌
- **WHEN** 请求携带被篡改、过期、格式错误或所属用户已删除的 Bearer 令牌
- **THEN** 系统返回未授权响应，且不返回受保护数据或执行写入

#### Scenario: 旧 Cookie 不再授权
- **WHEN** 请求仅携带旧版 `campusclaw_session` Cookie 而没有有效 Bearer 令牌
- **THEN** 系统返回未授权响应，且不返回受保护数据或执行写入

#### Scenario: 身份属性变更
- **WHEN** 用户的角色或班级在令牌签发后由服务端修改
- **THEN** 后续请求按服务端当前记录授权，令牌中的旧身份属性不得覆盖当前记录

### Requirement: 浏览器使用 Bearer 登录

浏览器登录流程 SHALL 获取访问令牌，并在当前标签页的后续材料读取和上传请求中以 Bearer 头携带。浏览器 MUST 避免把令牌放入 URL、页面 HTML、持久化本地存储或普通 Cookie。未认证、令牌过期或被拒绝时，浏览器 MUST 引导到登录页；未验证身份前的页面响应不得包含受保护业务数据。

#### Scenario: 浏览器登录后访问材料
- **WHEN** 用户在登录页提交正确账号密码并进入材料页面
- **THEN** 浏览器使用返回的令牌请求材料数据，并展示服务端授权的本班材料

#### Scenario: 浏览器上传材料
- **WHEN** 已登录教师提交上传表单
- **THEN** 浏览器以 Bearer 头提交上传请求，并展示上传结果或明确错误

#### Scenario: 浏览器令牌失效
- **WHEN** 浏览器没有令牌，或材料请求因令牌失效收到未授权响应
- **THEN** 浏览器清除当前令牌并引导到登录页，不展示受保护业务数据
