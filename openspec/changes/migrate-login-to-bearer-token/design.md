## Context

动机见 `proposal.md`；行为契约见 `specs/identity-access-control/spec.md`。目前 `campusclaw/security.py` 已实现 HMAC 签名和到期校验，`campusclaw/web.py` 却仅从 Cookie 读取令牌。`POST /api/login` 的 JSON 响应只返回用户对象，HTML 表单靠 `Set-Cookie` 后重定向。`/materials` 同时承担 HTML 页面与 JSON 列表，`/upload` 和上传表单依赖浏览器自动携带 Cookie。用户、角色和班级已存在于 SQLite 中。

## Goals / Non-Goals

**Goals:**

- 沿用现有账号密码及签名能力，将令牌交付和消费改为 Bearer 协议。
- 为浏览器页面提供无需 Cookie、无需在 URL 暴露令牌的完整使用路径。
- 保持服务端角色和班级判断；令牌发出后用户资料变更仍能在后续请求中生效。

**Non-Goals:**

- 不引入第三方身份服务、JWT 依赖、刷新令牌或长期登录。
- 不改用户密码哈希、班级数据模型和材料入库语义。

## Decisions

1. 复用现有 HMAC 签名令牌格式，将有效期设为一小时，令牌只承载用户 ID 和到期时间。登录响应返回 `access_token`、`token_type: Bearer`、`expires_in: 3600` 和现有最小用户对象，并加 `Cache-Control: no-store`。验证时严格解析单个 Bearer 凭据、验签和校验到期，再按用户 ID 从数据库读取当前用户名、角色及班级。这样角色变更、转班和删除用户可在下一次请求体现。备选方案是令牌直接携带角色和班级并信任其直到过期；实现更少，但会保留过时权限。

2. API 的认证入口统一为 `Authorization` 头，不再读取 `campusclaw_session`。没有有效令牌的 JSON 数据请求返回 401；已有的跨班级及学生上传拒绝继续返回 403。旧 Cookie 即刻失效，部署说明要求现有用户重新登录。备选方案是暂时并行接受 Cookie 和 Bearer；这会让迁移后的授权来源不唯一，也难以验证用户要求的 Bearer 路径。

3. 登录页改为 JavaScript 提交 JSON；浏览器将令牌保存到 `sessionStorage`，仅在同一标签页内用于 `fetch` 的 `Authorization` 头。材料页和上传页的初始 HTML 是不含用户、班级或材料数据的页面外壳；脚本在请求数据前检查令牌，无令牌或收到 401 即清除并转到 `/login`。材料列表继续调用 `/materials` 的 JSON 表示，详情继续调用 `/materials/{id}`；上传调用 `/api/materials`。HTML 外壳不缓存敏感数据，DOM 渲染使用安全文本赋值。备选方案是持久化到 `localStorage`；它会扩大令牌在浏览器中的驻留时间。普通 HTML 导航无法自行携带 Bearer 头，所以保留服务端渲染用户数据不可行。

4. 表单路径改为脚本请求；`POST /api/login` 统一 JSON 响应，不再为表单提交设置 Cookie 或直接重定向。关闭 JavaScript 的浏览器无法完成登录，页面需显示明确提示。备选方案是保留 Cookie 表单登录；会与 Bearer-only 目标冲突。

## Risks / Trade-offs

- [Risk] `sessionStorage` 可被同源脚本读取，跨站脚本漏洞可能窃取令牌。→ Mitigation：避免动态 HTML 注入，敏感响应禁缓存；对远程部署要求 HTTPS，继续检查任何用户内容的页面渲染。
- [Risk] 签名令牌不能在到期前逐个撤销。→ Mitigation：缩短有效期至一小时，服务端每次查用户以立即拒绝已删除账号；后续若需主动撤销，可另立规约引入令牌版本或撤销表。
- [Risk] 页面首次加载先取得 HTML 外壳，客户端随后才能判断是否登录。→ Mitigation：外壳不含受保护内容，脚本验证前不渲染业务数据；无令牌立即跳转登录页。
- [Risk] 现有 Cookie 客户端和依赖 `/api/login` 重定向的表单会中断。→ Mitigation：发布明确的 Bearer 调用示例，更新自动化测试及 README，并要求重新登录。

## Migration Plan

1. 先更新令牌验证与服务端身份解析，再更新登录响应和所有受保护路由；同一版本中完成页面脚本迁移，避免半套协议上线。
2. 更新 HTTP 级测试，覆盖签发、错误凭据、过期和篡改、旧 Cookie 拒绝、用户权限变化及班级隔离，再运行完整测试集。
3. 更新 README 的 API 调用、浏览器行为和重新登录说明。部署后原有 Cookie 不再授权，用户重新输入账号密码。
4. 如需回滚，恢复上一版本应用，保留原有用户和材料数据库；本变更不需要数据库迁移。旧 Cookie 是否仍有效取决于其原始到期时间和签名密钥，回滚前应评估这一点。
