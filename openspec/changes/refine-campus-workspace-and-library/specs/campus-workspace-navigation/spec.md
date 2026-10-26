## Purpose

将 CampusClaw 的应用、会话和资料阅读组织为清晰的学习工作区，参考用户提供的布局并延续暖色风格，使桌面和移动设备均能直接找到助手、发问、使用上下文和回看历史。

## ADDED Requirements

### Requirement: Workspace regions and module scope
系统 MUST 提供全局导航、当前模块的次级列表及主内容区。全局导航包含智能体、资料库和按角色显示的教师管理入口，底部显示身份、主题切换与退出。系统 MUST 不显示错题本、智能批改、自主学习的功能入口或可点击占位项。

#### Scenario: Student navigation
- **WHEN** 学生在智能体和资料库之间切换
- **THEN** 全局导航保持一致，次级列表与主内容同步切换，教师管理入口不可见

### Requirement: Assistant welcome and composer
系统 MUST 在无消息时展示当前助手名称、简介和快捷问题；快捷问题仅填入输入框，由用户发送。无会话时首次发送 MUST 先为所选助手创建本人会话。进入已有会话 MUST 显示真实记录。提问框 MUST 保留技能/资料选择、双角色上传、可移除标签、进度和失败草稿，并新增个人资料选择。

#### Scenario: Start from a suggestion
- **WHEN** 用户选择一个快捷问题
- **THEN** 输入框填入可编辑问题，不立即调用模型；用户发送后才创建所需会话并生成回答

#### Scenario: Preserve question context
- **WHEN** 用户携带技能和个人资料发问
- **THEN** 上下文仅作用于当前问题，成功后恢复默认，失败保留草稿；切换会话清理旧草稿与原文预览

### Requirement: Useful recent conversations
系统 MUST 仅列出本人本班会话，显示由首条用户问题生成的简短标题、助手名称与最近活动时间，按最近活动排序；空会话显示“新对话”。服务端 MUST 返回这些摘要，不要求前端逐个读取完整消息。

#### Scenario: Return to a previous question
- **WHEN** 用户刷新后查看最近对话
- **THEN** 可通过问题标题识别会话并恢复消息，列表不包含其他用户或班级的对话

### Requirement: Warm themes and responsive access
系统 MUST 默认使用米白与暖砖红主题，支持可记忆的深浅主题切换，并统一登录、工作区、资料阅读与教师管理台。正文对比度 MUST 至少 4.5:1。移动端 MUST 可折叠导航，390 像素宽度无页面横向溢出；主要控件须有键盘焦点和可读名称。

#### Scenario: Persistent theme
- **WHEN** 用户切换主题并刷新或进入另一页面
- **THEN** 页面恢复所选主题，按钮、输入框、弹窗和错误状态均可辨认

#### Scenario: Mobile composition
- **WHEN** 用户在 390 像素宽度展开导航、选择三份资料并提问
- **THEN** 导航可关闭、标签换行，发送按钮可触达，编辑器不被固定面板遮挡
