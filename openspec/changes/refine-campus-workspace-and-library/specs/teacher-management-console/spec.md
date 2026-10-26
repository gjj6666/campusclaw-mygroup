## Purpose

提供与学习对话分离的教师管理台，通过按职责分栏维护本班共享内容、助手和工具，保留既有模板、技能和鉴权能力，减少长页面表单干扰并提供可核查的操作状态。

## ADDED Requirements

### Requirement: Teacher console and role boundaries
系统 MUST 提供独立 /admin 管理入口，包含学生、资料、智能体、技能、MCP 分栏；教师默认登录进入管理台并可切换到学习工作区，学生默认进入工作区。学生名单 MUST 仅返回本班学生的标识与用户名，不包含口令、令牌或私人内容。教师专属数据接口对学生 MUST 返回403，跨班资源操作统一404。

#### Scenario: View students
- **WHEN** 教师打开学生分栏
- **THEN** 看到本班学生名单和人数，不能借此查看私人会话、附件或个人资料；本次不提供账号创建或密码重置

### Requirement: Focused shared resource editors
管理台 MUST 将本班资料上传/筛选/索引状态、智能体启停及角色/绑定、提示词模板、技能上传/新建/预览/启停/删除组织在对应分栏。资料和技能上传 MUST 支持真实 .md/.txt 文件选择、严格 UTF-8 解码和保存反馈。未保存编辑切换对象前 MUST 提供保留或放弃的选择，操作失败保留编辑内容。现有模板变量预览和应用功能 MUST 保留。

#### Scenario: Edit an assistant
- **WHEN** 教师切换至智能体分栏并编辑名称、角色、绑定或启用状态
- **THEN** 保存后明确反馈生效状态，可在学习工作区使用；选择模板不会在保存前修改持久配置

#### Scenario: Manage a shared skill
- **WHEN** 教师上传技能并执行预览、保存和停用
- **THEN** 系统展示解析名称、适用条件与工具引用，保存继续校验本班 MCP，停用技能不再可被显式选择

### Requirement: Edit and remove MCP servers
教师 MUST 能编辑已登记服务器的 Base URL 和令牌，名称作为稳定引用不可修改；编辑时令牌留空表示保持原值，所有响应 MUST 不含密钥。配置实际变动后 MUST 清空工具缓存、断开并要求重新连接发现。教师移除服务器后 MUST 不再列出或允许调用，保留既有审计；引用它的技能再次保存须拒绝，已存在技能运行时记录 denied。

#### Scenario: Change server URL
- **WHEN** 教师修改已连接服务器的 URL 并保存，令牌留空
- **THEN** 令牌保留，服务器断开，工具缓存清空，重新连接前不可成功调用

#### Scenario: Remove a referenced server
- **WHEN** 教师确认移除服务器后调用仍引用它的旧技能
- **THEN** 系统不发出远端调用，SSE 与审计显示 denied，旧审计仍可查看

### Requirement: Discovery and failure feedback
MCP 分栏 MUST 展示连接状态、错误、发现工具的引用及是否可绑定，并保留最近调用审计。连接、配置变化和移除与进行中调用发生竞争时 MUST 不把失效结果报告为 ok。管理失败 MUST 不影响学习工作区、普通对话及资料浏览。

#### Scenario: Remote server unavailable
- **WHEN** 教师连接不可达服务器
- **THEN** 分栏显示明确错误及断开状态，其他应用和资料仍可操作
