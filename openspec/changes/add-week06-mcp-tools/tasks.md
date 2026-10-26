## 1. 实施基线

- [x] 1.1 确认本变更规约获用户确认，记录现有未提交工作并运行第 5 课测试基线；以测试输出区分已有失败，禁止覆盖现有工作。
- [x] 1.2 重新读取课件和参考 OpenAPI，核对补充要求；交付差异说明，如涉及行为变化先修订规约，无法访问则明确记录验证限制。

## 2. 自建 MCP 服务

- [x] 2.1 新建 mcp-server/，实现 /health、Bearer 校验、JSON-RPC 与初始化通知；独立 HTTP 测试验证 health=200、无效令牌=401、标准错误码和请求 id。
- [x] 2.2 实现 formula_hint 与 unit_convert 的 question 输入、schema 和文本输出；验证发现两工具、公式提示、100 cm→1 m 及非法参数。
- [x] 2.3 添加独立 Dockerfile、排除文件、Compose mcp-demo 服务与 .env.example 空占位；验证 Compose 配置与 app 容器访问 http://mcp-demo:8090/health，不输出渲染后的密钥。

## 3. 数据与主机接入

- [x] 3.1 增加服务器、工具缓存、审计及版本字段，并迁移 skills 工具约束；旧数据库夹具验证技能 id、绑定、消息、foreign_key_check 和重复初始化均保留。
- [x] 3.2 实现 MCP HTTP 客户端的握手、通知、发现和调用；真实服务器测试验证 Bearer、id、协议错误、超时、大小限制与拒绝重定向。
- [x] 3.3 实现服务器登记、班内读取、连接原子发布缓存、失败清缓存和断开失效；存储测试验证重连失败、断开竞争、班内唯一及响应不含密钥。
- [x] 3.4 增加 MCP 管理 API 与本班审计 API；HTTP 测试验证教师成功、学生 403、无效 Bearer 401、跨班与不存在编号一致 404、提交 class_id 无法改变归属。

## 4. 技能与流式调用

- [x] 4.1 扩展技能解析与保存校验，保留单工具及旧格式；验证非法命名、他班/未知服务器、断开、缓存缺失和不兼容 question schema 拒绝保存且原技能不变。
- [x] 4.2 在现有技能路由中真实调用 MCP，重验会话班级、连接版本和工具缓存；验证命中触发、未命中不触发、断开后不发请求及越权 denied。
- [x] 4.3 将结果作为有边界的 user 数据，增加 meta.tool_calls 并落审计；验证 ok/error/denied、无调用为空数组、提示注入文本不进 system、远端失败继续流式回答。

## 5. 界面与文档

- [x] 5.1 扩展教师管理页的登记、连接、断开、发现工具和审计展示；浏览器验证可完成配置，令牌密码输入提交后清空且不进入持久存储，失败有可读提示。
- [x] 5.2 添加 MCP OpenAPI 注解并更新技能及 SSE schema，生成文档；验证 /openapi.json 与 Swagger 可试调 connect、tools、技能保存及审计，响应 schema 无令牌字段。
- [x] 5.3 更新 README 与验收说明，列出同仓结构、Base URL、.env 配置、独立请求及回滚步骤；核对示例均无真实密钥且与实际接口一致。

## 6. 测试与验收证据

- [x] 6.1 在 apitest/ 增加管理生命周期和鉴权用例，临时启动真实自建 MCP；验证连接→formula_hint 技能→智能体→学生会话→ok 审计，以及断开后 denied 和拒绝保存。
- [x] 6.2 运行 python -m unittest discover -s tests、既有 SSE 测试与 python apitest/run_all.py；生成脱敏 HTML 报告并验证报告被 Git 忽略，回归失败处理或明确归因。
- [ ] 6.3 在 Compose 中执行独立 MCP health/list/call 和完整主机链路，记录脱敏证据；断开后同技能不能成功，正常检索和无 MCP 会话仍可用。
- [x] 6.4 检查 Git、镜像构建内容和前端无 MCP 令牌，验证本机登记令牌与服务环境一致但不打印值；交付验证结论，对未执行的环境检查明确说明。

## 实施验证记录

已完成 18/19 项。6.3 已验证 Compose 独立 health/list/call、容器服务名互通、学生 SSE meta 的 ok/denied、审计、断开拒绝和关键词检索；真实模型网关出现 SSLEOFError，未完成真实模型的完整流式回答及无 MCP 会话在线验证，因此保持未勾选。隔离测试使用真实 MCP 与模型替身，完整 SSE 链路通过。详见 docs/week06-validation.md 和被忽略的 apitest/reports/week06-compose.json。
