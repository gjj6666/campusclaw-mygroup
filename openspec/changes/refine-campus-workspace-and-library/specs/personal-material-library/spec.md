## Purpose

在统一资料库中分类浏览本班共享资料，并让教师和学生管理仅本人可见的个人资料副本，以显式选择方式跨本人本班会话复用，同时保持原会话附件及共享资源的权限边界。

## ADDED Requirements

### Requirement: Classified browsing and safe reading
资料库 MUST 区分本班共享资料与我的个人资料，按学科分组并显示数量，支持标题筛选、列表/网格切换、空状态及原文预览。Markdown MUST 安全渲染标题、段落、列表和代码，纯文本正常换行；上传文本中的 HTML、脚本与危险链接不得执行，外部图片不得自动加载。

#### Scenario: Find a class material
- **WHEN** 用户选择学科并输入标题关键词
- **THEN** 只显示本班匹配资料，切换列表/网格保留筛选，点击后在阅读区显示同一资料原文

### Requirement: Private reusable material creation
教师和学生 MUST 均可上传 UTF-8 .md/.txt 到个人库、将本班可访问共享资料保存个人副本，或将本人原会话的资料附件显式复制到个人库。个人资料 MUST 为不可变副本，不修改原共享资料或原附件。每份最多 32 KiB、12000 字，学科最多64字、文件名最多200字；空白、非法编码和超限内容返回可读 400，不截断。

#### Scenario: Promote a conversation file
- **WHEN** 用户对本人原会话资料执行“存入个人资料库”
- **THEN** 系统创建本人本班个人副本，原附件仍仅在原会话可用；未显式保存的旧附件不出现在个人库

#### Scenario: Copy a class material
- **WHEN** 用户将可访问共享资料保存为个人副本
- **THEN** 个人库保留当时正文和学科；源资料超过个人文件限制时明确拒绝；对相同来源与相同内容重复保存返回已有副本

### Requirement: Personal material isolation
个人资料的列出、详情、来源复制及提问引用 MUST 从鉴权会话取用户和班级。仅上传者或保存者本人在原班级可见；同班教师、同学、其他班用户及不存在资源 MUST 一致返回 404。个人库不得出现在共享搜索、共享索引或其他人的选择器中。

#### Scenario: Forged private reference
- **WHEN** 其他用户直接访问个人资料标识或将它用于自己的会话
- **THEN** 系统返回 404，且不调用模型、工具或嵌入服务

### Requirement: Cross-conversation question selection
消息 context.materials MUST 支持 {source:personal,id}，允许本人在本班不同会话中使用个人资料；source:upload 仍需原会话归属。个人与会话资料全文 MUST 作为用户级数据进入问题，合计最多18000字；共享、个人和会话资料总数最多三份，不允许重复引用。个人来源 MUST 参与连续 S 引用、受保护预览与历史快照；MCP 与技能授权规则保持不变。

#### Scenario: Reuse in another conversation
- **WHEN** 本人新建另一个本班会话并选择个人资料
- **THEN** 资料可随问题使用并产生可访问引用，不需要复制为新的会话附件，不自动成为应用长期绑定

#### Scenario: Reject unsupported skill origin
- **WHEN** 客户端将 personal 来源用于 context.skill
- **THEN** 系统返回 400；本次个人库只提供资料复用，不扩大私有技能范围
