## Purpose

让教师和学生在发出问题时直接选择或上传技能与资料，并在维持班级隔离、会话归属及 MCP 鉴权的前提下，将所选上下文用于当前问题、展示引用并保留可核查的历史记录。

## ADDED Requirements

### Requirement: Per-question context selection
系统 MUST 支持发送消息时携带可选 context。skill 字段缺省表示沿用应用自动路由，null 表示本轮不使用技能，引用对象表示直接使用一个指定技能；materials 字段缺省表示沿用应用资料绑定，空数组表示本轮不使用资料，引用数组表示本轮精确选择。引用包含 source（shared 或 upload）及 id。显式技能不依赖触发词匹配；资料最多三份，重复引用或格式错误 MUST 返回可读的 400。

#### Scenario: Explicit selection
- **WHEN** 用户选择本班已启用的共享技能及可用共享资料后提问
- **THEN** 系统使用指定技能及指定资料范围，不修改应用长期绑定；显式资料选择不受应用学科筛选限制

#### Scenario: Backward compatibility
- **WHEN** 旧客户端发送未携带 context 的消息
- **THEN** 系统保留应用绑定、自动技能路由与原有资料检索行为

### Requirement: Private conversation uploads for both roles
系统 MUST 允许教师和学生在本人会话内上传 UTF-8 .md/.txt 技能或资料。每个文件最多 32 KiB；技能正文最多 8000 字符，资料正文最多 12000 字符；单轮私有资料合计最多 18000 字符，超限明确拒绝且不得静默截断。技能沿用现有技能文件格式校验。上传内容 MUST 保存在独立的私有附件存储，不自动创建班级共享技能、知识条目或向量。

#### Scenario: Student uploads and uses content
- **WHEN** 学生在本人会话上传合法技能或资料
- **THEN** 系统返回附件标识，允许预览和选择，并在本轮问题使用该内容

#### Scenario: Invalid file
- **WHEN** 用户上传非支持后缀、非法 UTF-8、空文件、超限内容或格式非法的技能
- **THEN** 系统返回可读错误，不创建可用附件且保留输入框问题草稿

### Requirement: Context authorization and isolation
系统 MUST 从鉴权会话取得用户与班级。共享引用仅允许本班启用技能及已就绪资料；私有附件仅允许上传者在原会话读取、列出和使用。跨班、跨用户、跨会话和不存在的资源 MUST 一致返回 404。格式、禁用或未就绪状态错误 MUST 返回 400。上下文校验 MUST 在模型请求和工具调用前完成。原共享管理接口 MUST 保留教师限定。

#### Scenario: Forged attachment reference
- **WHEN** 同班另一用户、另一班用户或上传者在其他会话提交附件标识
- **THEN** 系统返回 404，且不调用模型或 MCP

#### Scenario: Student modifies shared resources
- **WHEN** 学生调用原共享技能或资料写接口
- **THEN** 系统继续返回 403

### Requirement: Prompt placement and MCP checks
系统 MUST 将私有上传技能作为用户级指示、资料和 MCP 结果作为带来源标识的数据加入本轮用户消息，不提升为系统指令。教师共享技能保持原有可信配置语义。上传技能引用 MCP 时 MUST 在上传时校验本班服务器及发现缓存，调用时再次校验连接状态、工具存在性与会话身份；拒绝调用 MUST 在 tool_calls 和审计中显示 denied，令牌不得进入附件、前端或响应。

#### Scenario: Tool disconnected after upload
- **WHEN** 已上传技能引用的 MCP 服务器在本轮调用前断开
- **THEN** 系统不发送远端 tools/call，并记录和展示 denied

#### Scenario: Uploaded instructions attempt role override
- **WHEN** 用户上传技能包含要求忽略教师规则的文本
- **THEN** 提示构造仍将其置于用户层，保留固定系统规则，且所有数据访问继续由服务端鉴权

### Requirement: Citations and context snapshots
系统 MUST 将私有资料全文与共享资料检索结果纳入统一连续编号的 S 来源，保留来源类型、名称、资源标识及受保护访问链接。SSE meta 与历史消息 MUST 包含本轮上下文选择快照；旧消息缺少快照时正常显示。历史不得包含 MCP 密钥。

#### Scenario: Review a completed question
- **WHEN** 用户刷新页面并打开历史会话
- **THEN** 能看到该轮选中的技能、资料和可访问引用；私有来源链接仍检查原会话归属

#### Scenario: Next question
- **WHEN** 一轮发送成功后用户继续提问且未重新选择
- **THEN** 编辑器恢复应用默认选择，不自动绑定上一轮显式附件；既有有限聊天历史行为继续生效
