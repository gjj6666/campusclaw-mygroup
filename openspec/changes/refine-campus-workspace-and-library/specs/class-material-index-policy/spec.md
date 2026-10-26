## Purpose

让教师在资料管理中配置本班共享资料的分段方式、查看预览并有选择地重建索引，以可见状态控制索引更新，并在策略不同和外部依赖失败时维持检索隔离与原文引用准确性。

## ADDED Requirements

### Requirement: Class-scoped chunk policy
教师 MUST 能读取并保存本班自动/自定义分段策略。自动模式保留部署配置默认值（当前500字、重叠80字）；自定义模式支持空行、换行或句末分隔，最大片段长度100–2000字、整数重叠比例0–40%，及片段两端空白清理开关。非法范围返回400，学生配置请求返回403。修改策略 MUST 仅影响后续上传和显式重建，不自动处理旧资料或改变其他班策略。

#### Scenario: Save a new policy
- **WHEN** 教师将本班策略保存为按换行分段、800字、10%重叠
- **THEN** 本班新上传共享资料使用该策略；已有资料仍保留已应用版本并显示是否需要重建

### Requirement: Deterministic preview and source positions
教师 MUST 能预览指定文本在所选策略下的片段数量、内容、序号与原文位置，不写入知识库或调用嵌入服务。正式索引 MUST 与相同文本及策略的预览一致。所有可引用片段 MUST 保持“原文位置截取得到片段正文”，清理不得改写原文内部字符。

#### Scenario: Preview mixed text
- **WHEN** 教师预览含中文标点、长段落和空行的材料
- **THEN** 返回确定性的有序片段、有效位置和非空正文，任意片段可精确从保存的原文回溯

### Requirement: Explicit authorized rebuild
教师 MUST 能对指定本班共享资料按当前策略重建索引，即使策略未变也能重试。系统 MUST 显示 ready、pending、failed 或尚未索引状态，已应用策略与当前策略不同时另示“待按新策略重建”。同一材料同时重建返回409；跨班与不存在材料统一404。外部失败 MUST 显示失败并允许重试，不返回成功或伪造 ready。

#### Scenario: Retry indexing failure
- **WHEN** 重建过程遇到嵌入或向量库失败
- **THEN** 管理台显示 failed、保留原文和重试入口，失败片段不进入检索结果

### Requirement: Version-safe retrieval and compatibility
系统 MUST 支持不同班及不同材料保留各自已应用策略版本；检索只返回资料当前生效且 ready、嵌入配置兼容的片段，不混用旧代或其他班索引。改变分段策略不得使未重建旧资料无故消失。未设置新策略时 MUST 兼容原资料、原索引与引用。个人资料与会话附件不受共享分段策略影响。

#### Scenario: Search across policy versions
- **WHEN** 本班一份资料已重建而另一份保留原策略
- **THEN** 两份 ready 资料仍可在其授权范围检索，来源各自回溯正确原文；已被替换的旧片段不能返回
