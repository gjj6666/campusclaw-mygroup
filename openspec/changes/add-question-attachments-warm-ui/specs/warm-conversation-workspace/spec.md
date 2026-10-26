## Purpose

提供以提问和对话为中心的暖色工作区，让用户在输入问题时即可发现、选择、预览和上传技能与资料，同时保持教师管理能力、移动端可用性和清晰的操作反馈。

## ADDED Requirements

### Requirement: Composer context controls
提问编辑器 MUST 提供“技能”“资料”“上传”入口和可移除的已选标签，展示自动技能或显式技能状态。共享内容和本会话上传内容 MUST 可区分并支持预览；移除标签只取消本轮选择。教师与学生 MUST 均可使用会话上传入口。

#### Scenario: Compose with uploaded file
- **WHEN** 用户在输入框旁上传合法资料
- **THEN** 文件加入本轮资料选择，显示名称、上传状态与移除操作，无需进入教师配置区

#### Scenario: Failed send or conversation switch
- **WHEN** 发送失败或用户切换会话
- **THEN** 失败保留当前问题及选择以便重试；切换会话不将原会话附件选择带入新会话

### Requirement: Conversation-first layout
工作区 MUST 将聊天记录和提问编辑器作为主要区域，应用切换和会话列表位于紧凑导航；教师管理、共享技能、知识库和 MCP 配置 MUST 通过清晰的次级入口访问，并继续按角色控制展示。

#### Scenario: Student opens workspace
- **WHEN** 学生登录并打开工作区
- **THEN** 能直接选择应用、开启会话并提问，看到会话附件入口但不出现教师共享管理入口

### Requirement: Consistent warm visual theme
系统 MUST 在登录、对话、管理和资料页面统一采用米白背景、暖橙主色、深棕正文及暖灰边框。常规文字对比度 MUST 至少 4.5:1；错误、禁用、选中、加载和键盘焦点状态 MUST 可区分。

#### Scenario: Navigate across pages
- **WHEN** 用户从登录进入对话并打开资料或管理入口
- **THEN** 页面沿用同一套暖色变量、按钮、卡片、输入框与状态视觉

### Requirement: Accessible responsive interaction
选择器、上传、预览、移除和发送 MUST 可通过键盘操作，并有可读标签和状态提示。390 像素宽度下 MUST 不出现页面级横向滚动，编辑器和上下文标签保持可用。文件名及预览文本 MUST 按文本渲染，不能执行 HTML。

#### Scenario: Mobile question
- **WHEN** 用户在 390 像素宽度选择技能、添加三份资料并输入问题
- **THEN** 标签换行，操作可触达，聊天与输入区域不被配置面板遮挡
