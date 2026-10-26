## Why

第 5 课已有班级隔离的检索、技能及流式对话，但技能工具只允许 knowledge_search，尚不能接入真实远端工具。第 6 课需要打通自建 MCP、教师发现与绑定、学生鉴权调用及审计，继续保留现有主路径。

## What Changes

- 同仓新增 mcp-server，以 Compose 服务 mcp-demo 启动，提供健康检查、Bearer 保护的 JSON-RPC 与 formula_hint、unit_convert 两个工具。
- 教师登记本班服务器，连接时握手并发现缓存工具，断开时清空缓存；密钥只由服务端持有，前端仅提供输入且不回显。
- 技能工具支持单个 工具名@服务器名，保存与执行均校验班级、连接状态和缓存；保留 knowledge_search 和无工具技能。
- 命中技能后真实调用 MCP，结果作为用户消息中的数据；SSE meta 增加 tool_calls，记录 ok、error、denied。
- 增加本班审计、教师管理界面、OpenAPI 注解、接口测试及脱敏验收说明。

## Capabilities

### New Capabilities

- `mcp-demo-server`: 同仓 MCP 服务、协议、工具与部署安全。
- `class-scoped-mcp-management`: 教师登记、服务端令牌、连接发现与断开。
- `mcp-skill-execution`: 扩展技能绑定校验、会话调用及流式状态。
- `mcp-audit-verification`: 班级审计、管理界面、Swagger 与验收证据。

### Modified Capabilities

无。当前 openspec/specs 尚无正式规约；第 5 课的 tutor-agent-skills 等位于未归档变更中。本变更明确扩展其中“工具只接受 knowledge_search”的限制，实施时需协调该限制，不能把两个冲突约束同时当作最终契约。

## Impact

影响 campusclaw/skills.py、tutor.py、tutor_schema.py、db.py、orchestration.py、api.py、openapi.py、tutor_page.py 与 static/tutor.js；新增 MCP 客户端、存储及独立服务器模块。需要保留旧数据库数据与关联关系的迁移，更新 Compose、环境变量示例、Docker 排除规则、apitest 和 README。沿用 Python 标准库与现有 SQLite、HTTP、Swagger 生成方式。

课程参考站点及课件本轮均无法读取；以用户提供清单作为当前可验证依据，正式验收前需重新核对课件补充要求。工作区现有未提交变更保持原样。
