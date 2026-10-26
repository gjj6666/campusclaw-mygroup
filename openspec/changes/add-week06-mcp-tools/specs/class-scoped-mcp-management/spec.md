## Purpose

为教师提供本班 MCP 服务器登记与连接发现能力，确保远端凭证始终由 CampusClaw 服务端持有，并使工具缓存、连接状态和班级权限共同决定工具的可用性。

## ADDED Requirements

### Requirement: 教师登记与班级隔离
系统 SHALL 提供 POST/GET /api/mcp/servers 登记及列举本班服务器，仅教师可访问 MCP 管理接口。登记接受 name、base_url、auth_token，名称 MUST 匹配 ^[a-z][a-z0-9_-]*$ 且班内唯一；Base URL MUST 为无用户信息、查询及片段的 http/https 地址。令牌 MUST 仅存于服务端，响应仅返回 has_token 等脱敏信息。班级 MUST 取自登录会话，客户端提交 class_id MUST 不改变归属；无效 Bearer 返回 401，非教师返回 403，跨班编号与不存在编号统一返回 404。

#### Scenario: 本班登记
- **WHEN** 教师提交 campus-tools、http://mcp-demo:8090 与令牌
- **THEN** 创建本班 disconnected 服务器，响应和列表不包含 auth_token 及其值

#### Scenario: 越权管理
- **WHEN** 学生访问登记、列表、连接、工具或断开接口，或教师操作他班服务器编号
- **THEN** 学生得到 403，跨班教师得到与不存在编号一致的 404，且不向远端发请求

### Requirement: 原子连接发现与断开
系统 SHALL 提供 POST /api/mcp/servers/{id}/connect、POST /api/mcp/servers/{id}/disconnect 与 GET /api/mcp/servers/{id}/tools。连接 MUST 先 initialize 再 tools/list，完整验证工具名称和 schema 后才发布缓存并标记 connected；失败 MUST 清空缓存、标记断开并返回明确脱敏错误。断开 MUST 清空工具缓存，使后续保存或执行立即重新校验失败。MCP 不可用 MUST 不影响健康检查、检索与无 MCP 技能的流式对话。

#### Scenario: 成功连接后断开
- **WHEN** 教师连接自建 MCP 并查询工具，然后断开
- **THEN** 连接后可见 formula_hint、unit_convert；断开后工具列表为空且状态为 disconnected

#### Scenario: 握手或发现失败
- **WHEN** 服务拒绝令牌、超时、返回非法协议或发现无效工具
- **THEN** 返回明确的连接错误，不保留旧缓存或部分缓存，普通检索及对话保持可用
