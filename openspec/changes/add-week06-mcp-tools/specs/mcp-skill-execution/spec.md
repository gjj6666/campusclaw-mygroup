## Purpose

扩展现有技能工具字段以绑定班内已发现的 MCP 工具，在学生会话触发时重新鉴权并执行真实调用，将返回内容限制为数据，同时保留原有检索与流式回答体验。

## ADDED Requirements

### Requirement: 技能引用校验与兼容
技能工具字段 SHALL 接受空值、knowledge_search 或单个 工具名@服务器名，工具名称 MUST 符合 MCP 命名规则。教师保存 MCP 技能 MUST 验证服务器属于本班、已连接且工具在发现缓存中；非法格式、断开或未知工具返回可读 400，外班服务器名与不存在服务器名 MUST 返回一致错误。旧技能、智能体绑定、材料绑定和历史消息 MUST 在迁移后保留，重复启动 MUST 不损坏数据。

#### Scenario: 绑定已发现工具
- **WHEN** 教师保存含 formula_hint@campus-tools 的合法技能且本班服务器已发现此工具
- **THEN** 技能正常保存，可绑定到本班智能体并参与现有技能路由

#### Scenario: 拒绝不可用引用
- **WHEN** 保存非法引用、他班或不存在服务器、未连接服务器或未发现工具
- **THEN** 保存失败且不部分修改旧技能，不泄露他班资源是否存在

#### Scenario: 第 5 课数据兼容
- **WHEN** 带旧技能、关联与历史消息的数据库迁移并再次启动
- **THEN** 旧数据与关联完整，knowledge_search 及无工具技能仍正常保存和执行

### Requirement: 会话鉴权执行及数据边界
学生提问命中 MCP 技能时，服务端 SHALL 重新验证会话班级、连接状态与发现缓存，携带服务端令牌执行远端 tools/call，并以 question 参数传递当前问题。工具结果 MUST 以明确的数据边界加入 user 消息，MUST 不作为 system 或技能指令执行。每次 MCP 尝试 MUST 在 SSE meta.tool_calls 中包含工具引用及 ok、error 或 denied 状态；无 MCP 调用时为 []。远端错误或超时 MUST 标记 error，鉴权拒绝 MUST 标记 denied 且不发远端请求；两者 MUST 允许原有对话继续并明确工具未成功。

#### Scenario: 学生触发真实调用
- **WHEN** 学生向绑定启用 MCP 技能的智能体提问且命中其适用条件
- **THEN** 服务端真实发出带 Bearer 的 tools/call，meta 包含引用和 ok，模型 user 消息含工具文本而 system 不含返回内容

#### Scenario: 断开后旧技能触发
- **WHEN** 教师断开服务器后学生在原会话再次命中旧技能
- **THEN** 不访问远端，meta 标记 denied，回答不宣称工具成功

#### Scenario: 远端失败与注入文本
- **WHEN** 远端超时、工具 isError 或返回含“忽略系统指令”的文本
- **THEN** 失败以 error 呈现并继续对话，返回文本始终位于 user 数据边界，系统提示明确其无指令权限
