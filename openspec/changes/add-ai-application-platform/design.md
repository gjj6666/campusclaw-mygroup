## Context

动机见 proposal.md。已有 agents、skills、agent_skills、agent_materials、conversations 及 SSE；技能支持 knowledge_search 和已发现的 MCP 引用。当前 tutor 页面只有智能体选择器和教师配置表单；GUIDANCE_EXAMPLE 是需手工保存的单个示例，skill-file 读取文件后填入文本框，未形成独立技能库。角色仅为 prompt 文本，无模板存储。已有接口测试依赖未启动任何应用时 agents/skills 为空，不能在所有登录或 GET 请求中无条件灌入默认业务数据。

## Goals / Non-Goals

**Goals:** 在现有模型和会话引擎之上补齐平台入口；以可复用的内置配置获得多个实际用途；模板确定性渲染；技能上传保留原校验；权限与数据兼容不变。

**Non-Goals:** 不引入个人注册/租户体系、独立商城、脚本插件执行、任意模板表达式、ZIP 技能包或新的远程部署服务。多个应用复用现有模型，采用不同角色与技能实现差异，不要求配置多个模型供应商。内置应用不默认绑定 MCP 凭证或替教师启用外部服务。

## Decisions

1. **目录与应用模型。** 新增只读内置内容模块，稳定 key 为 course-qa、guided-solving、study-plan；GET /api/apps 返回内置卡片和本班自定义启用 agents。POST /api/apps/{key}/launch 在事务中按需创建班内默认 agent、所需可信技能及用户会话，返回既有 conversation 结构；不在 GET 和登录时写入业务内容。当前路由只匹配数字参数，新增 key 路由需采用精确受限 key 正则，保持既有数字 id 范围检查。自定义应用继续使用已有 POST /api/conversations。

2. **稳定映射和并发。** 增加 builtin_app_bindings(class_id,builtin_key,agent_id)，唯一 (class_id,builtin_key)，并使用复合外键保证 agent 属于同班。首次启动采用短事务与唯一约束处理并发；系统仅按服务端白名单创建可信配置，学生不能附带 prompt、skill 内容或 class_id。已建立应用再次启动读取教师当前配置，停用时拒绝新建会话。默认课程答疑不随意绑定全班资料，教师仍通过已有 agent_materials 显式选择资料。

3. **模板与渲染。** 系统内置模板由源码维护，新增 prompt_templates 保存本班自定义 name、description、content；内置和自定义引用采用 {source:builtin,key:...} 与 {source:custom,id:...} 区分。新增 GET /api/prompt-templates、POST /api/prompt-templates、GET/PUT/DELETE /api/prompt-templates/{id}、POST /api/prompt-templates/render。仅教师可访问模板管理及预览；服务端使用固定占位符解析，只接受 subject/audience/goal，不使用 eval、format 属性遍历或模板引擎。前端展示识别出的变量，预览成功后填入 agent-prompt，教师通过既有 agent 保存接口显式提交；结果是文本快照，模板修改删除不影响旧角色。

4. **技能库与上传。** GET /api/skill-library 返回三个内置技能预览；POST /api/skills/install 接受 builtin_key，复制至本班并登记 builtin_skill_bindings 映射。已安装返回现有副本，同名非库技能返回冲突，不覆盖用户文本。首次内置应用启动仅使用同一白名单安装服务，不开放任意学生技能写入。POST /api/skills/import 接受 filename 与 content，服务端校验扩展名、UTF-8 字节数、字符数和既有 parse_skill/McpStore.resolve；浏览器以严格 UTF-8 解码、展示预览，教师确认后提交。32 KiB 是原始文件字节上限，8000 字沿用现有正文限制；旧 POST/PUT /api/skills 继续可用。JSON 内容上传复用现有传输，避免新增 multipart 解析依赖。

5. **统一页面。** 在 /tutor 增加应用中心卡片与清晰导航，保留现有会话区和教师管理，不迁移用户数据。内置应用点击 launch 后复用 openConversation；模板选择、变量、预览置于角色编辑旁；内置技能预览/安装和文件上传置于技能中心，成功后刷新可绑定技能。用户内容一律 textContent，不用 innerHTML；学生能查看应用但看不到教师写入口。登录页、材料页的链接说明同步改为应用平台。

6. **验证与兼容。** 沿用 endpoint 注解生成并导出 OpenAPI；新增目录/模板/技能接口测试和真实同仓 MCP 参与的五项能力链路。模板表达式和上传内容均不执行代码。模型/Qdrant 替身用来稳定验证路由和消息构造，Compose 真实验证单独记录。第 6 课当前尚有模型 TLS 故障和未完成的真实模型验收，本变更不能抹去该限制或勾选其待办。

## Risks / Trade-offs

- [内置数据覆盖用户修改] → 通过稳定 key 与映射标识，只创建缺失项；同名冲突显式返回，不用名称推断所有权。
- [学生启动成为配置写入旁路] → launch 只接受已知 builtin key，不接受任意配置；校验班级和启用状态，并发创建唯一。
- [模板注入/变量二次展开] → 固定变量名、纯文本一次替换、限制长度；渲染不执行表达式。
- [文件扩展名和编码伪装] → 客户端严格解码、服务端再次检查 filename/content 字节与技能格式，不读取路径和执行代码。
- [内置技能删除或改名后被重新安装覆盖] → 映射按 id 追踪；主动删除后允许显式安装或系统按需重建，命名冲突时明确拒绝，禁止覆盖手工技能。
- [实际模型仍不可达] → 显示原有失败事件，将真实模型结果与 MCP/替身证据分别记录，不降低验收标准。

## Migration Plan

1. 实施前记录未提交工作、备份数据库并运行现有 77 项单元测试、24 个接口脚本及 SSE 基线。
2. 增量创建模板及内置映射表，保持 agents/skills/历史数据不变，外键检查与重复初始化通过后部署。
3. 用户首次点击应用才按需建默认配置；教师已有配置不自动变更，旧链接继续可访问。
4. 验证三个内置应用、模板快照、自定义上传、班内检索及真实 MCP，再更新文档和 HTML 报告。
5. 回滚代码时可保留新增表，旧 agents/skills 和 conversations 仍使用兼容结构；恢复备份仅在迁移确实破坏兼容时使用，避免丢失新会话。
