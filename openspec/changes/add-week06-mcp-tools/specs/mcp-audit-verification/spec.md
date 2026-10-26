## Purpose

使教师能通过班内管理界面、调用审计及可试调文档追踪 MCP 接入效果，并以独立服务和主机端到端测试提供脱敏证据，证明成功、失败与断开行为符合课程要求。

## ADDED Requirements

### Requirement: 班内调用审计
系统 SHALL 为每次会话 MCP 调用尝试记录 tool@server、状态、用户、班级、会话与时间，覆盖 ok、error、denied。GET /api/mcp/audits MUST 仅教师可用且只返回本班记录；审计及错误 MUST 不包含令牌或原始认证头。

#### Scenario: 审计成功与拒绝
- **WHEN** 学生先成功调用，再在断开后触发同一技能
- **THEN** 本班教师能看到相应 ok 与 denied 记录、用户与时间，他班教师看不到记录，学生查询返回 403

### Requirement: 管理界面与接口文档
教师界面 SHALL 提供服务器登记、连接、断开、已发现工具及审计列表，显示连接失败原因和完整工具引用。令牌输入 MUST 使用密码字段且提交后清空、不放入浏览器持久存储。系统 SHALL 通过现有 OpenAPI 注解生成 MCP 接口及扩展技能与 SSE schema，Swagger MUST 能在 Bearer 鉴权下试调登记、连接、工具与技能保存。

#### Scenario: 浏览器完成配置
- **WHEN** 教师登录后登记并连接自建服务器，复制发现的引用保存技能
- **THEN** 页面展示真实工具和结果，刷新后没有令牌回显，Swagger 中可查询相同接口及错误说明

### Requirement: 可复现验收
项目 SHALL 在 apitest/ 增加登记、连接、工具、断开、角色和班级越权测试，以及真实 MCP HTTP 服务参与的“连接→技能→学生会话→ok 审计”用例。run_all.py MUST 生成不含密钥且被 Git 忽略的 HTML 报告。验收说明 MUST 覆盖独立 health、tools/list、tools/call，Compose 内互通、断开拒绝和密钥不进入 Git、前端与镜像；MCP 用替身的测试 MUST 不冒充真实 MCP 验收。

#### Scenario: 端到端与回归报告
- **WHEN** 执行接口测试和 Compose 验收
- **THEN** 可定位成功调用及断开拒绝的脱敏证据，同时第 3–5 课鉴权、检索、技能和流式回归通过；未能执行的环境验证明确列出
