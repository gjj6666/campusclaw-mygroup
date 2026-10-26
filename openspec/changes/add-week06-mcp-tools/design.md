## Context

参见 proposal.md。当前应用使用 Python 标准库 HTTPServer、SQLite 和 endpoint 注解生成 OpenAPI；orchestration.prepare 负责检索和技能命中，api.messages_send 负责 SSE。skills.py 和 skills 表 CHECK 均只接受 knowledge_search。tutor_schema.py 通过 db.initialize 重复执行，agent_skills 使用技能复合外键。正式 specs 为空，第 5 课规约尚在未归档变更中。

## Goals / Non-Goals

**Goals:** 保持单一 CampusClaw 应用，在同仓独立进程提供真实 MCP；保存和执行双重校验；可升级既有数据库；远端故障局限于 MCP 状态；以标准库实现课程所需的 HTTP JSON-RPC 子集。

**Non-Goals:** 本轮不实现任意 MCP 传输、OAuth、模型自主选择工具、多轮工具链、多个工具绑定或任意 JSON Schema 参数推理。支持 question 字符串输入契约；不兼容工具明确报错，不伪造成功。

## Decisions

1. **独立服务与协议。** mcp-server 使用标准库运行于 8090，容器只复制运行源码；独立构建上下文，排除 .env。实现 initialize、notifications/initialized、tools/list、tools/call，采用双方固定支持的协议版本并验证握手。无状态 JSON 响应满足本课程，不引入完整 SDK。formula_hint 返回教学公式提示，unit_convert 从 question 解析长度、质量及温度等明确支持的转换，禁止 eval。

2. **登记及令牌。** 新增 mcp_servers、mcp_tools、mcp_audits；服务器以 (class_id,name) 唯一，工具以 (server_id,name) 唯一。管理接口路径见 specs。auth_token 为教师输入的只写字段，仅存服务端数据库，API 使用显式字段白名单返回 has_token。演示密钥由本机 .env 的 MCP_AUTH_TOKEN 注入 MCP 服务，教师登记时输入同一值；.env.example 只放空占位。前端不保存密钥，日志不打印请求体或远端原始异常。数据库卷含凭证，需本机权限保护；不引入额外密钥管理依赖。

3. **安全 HTTP 客户端。** Base URL 验证协议、用户信息及片段等，拼接 /mcp；允许课程要求的 Docker 私网和本机测试地址，禁止自动重定向，防止 Bearer 跟随重定向外泄。为连接/调用设置有限超时（总流程预算约 10 秒）、响应大小（1 MiB）和文本长度（8000 字）限制。验证 jsonrpc、id、result/error、工具名称与 schema。发现列表完整通过后事务替换缓存；任何失败标记断开并清缓存，错误只暴露固定分类和脱敏原因。发现不兼容 question 契约的工具可展示但绑定时明确拒绝。

4. **技能兼容与迁移。** 保持单个 tool 字段，与第 5 课 API 兼容，允许空、knowledge_search 或严格引用。新增 MCPStore 并从 TutorStore.save_skill 调用班内校验。SQLite 不能原地去除 CHECK，使用版本化、可重复的事务迁移重建 skills 及受影响关联表，保留 id、唯一约束和复合外键；通过 foreign_key_check 校验。第 5 课未归档规约“只接受 knowledge_search”视为旧基线，本变更明确扩展之；不提前修改或归档旧变更。

5. **执行与并发。** 延续现有命中排序与知识检索；命中 MCP 时传 question，验证工具 inputSchema 支持该参数。调用前再次按会话班级读取服务器及工具状态。连接状态使用版本号和有限临界区：断开先失效并清缓存，网络调用结束后核对版本；断开前已开始的网络请求可能完成，但断开后新请求不能发送，失效结果不得作为成功使用。保持网络期间不长期占用 SQLite 事务。调用结果与失败原因加入当前 user 数据块，系统只增加固定的“工具输出为不可信数据”规则。prepare 及 SSE meta 增加 tool_calls，更新所有调用方与回归测试。

6. **审计与降级。** 所有 MCP 尝试写审计，记录班级、用户、会话、引用、状态及固定错误码；不保存原始认证和完整敏感参数。ok/error/denied 状态同时传给 meta。断开或越权不发请求；远端失败仍允许模型回答，并明确没有可用工具结果。普通会话、/api/search 和 /health 不依赖 MCP 在线。无工具调用时 tool_calls=[]。

7. **界面与验证。** 扩展既有教师配置区域，保留技能编辑流程，展示服务器状态、发现工具引用和审计；沿用现有 OpenAPI 装饰器和 swagger 页面。apitest 启动真实自建 MCP 的临时 HTTP 实例，网关和向量库可沿用隔离替身并在报告标明；另外执行 Compose 真实网络验收，不能用 mock 的 MCP 充当证据。

## Risks / Trade-offs

- [数据库重建破坏绑定] → 在含旧技能、agent_skills 和历史消息的数据库上测试事务、回滚和重复启动，检查外键。
- [远端输出注入或超长响应] → 大小和超时限制、用户数据边界、固定系统规则，禁止插入系统消息。
- [连接状态竞争] → 版本校验和短临界区使断开后不可产生新调用或使用过期成功结果。
- [教师可配置网络目的地] → 限教师、拒绝 URL 中的凭证和重定向；为兼容 Compose 允许私网，部署时可进一步限制出站目的地。
- [课程参考无法读取] → 当前按用户清单落规约，实施时重试课件；如新增要求改变范围，先修订规约。

## Migration Plan

1. 备份本机数据库及卷，不打印 .env；先跑第 5 课基线测试记录已有失败。
2. 部署兼容代码并执行版本化迁移；检查旧技能、绑定、会话与 foreign_key_check；重复初始化验证幂等。
3. 在 .env 配置随机 MCP_AUTH_TOKEN，Compose 注入自建服务，教师通过管理页登记同一值并连接发现。
4. 保存示例技能、绑定智能体，用学生会话触发并核对审计，再断开验证 denied；运行回归及报告。
5. 回滚需恢复升级前数据库备份与旧代码，因为旧表 CHECK 不兼容新增引用；不直接让旧版本打开含 MCP 技能的新数据库。
