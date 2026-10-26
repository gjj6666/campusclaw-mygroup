## Context

动机见 proposal.md。当前应用用 `ThreadingHTTPServer`，路由集中在 `web.py`，SQLite 连接为跨线程共享；RAG 支持关键词、向量、混合检索，Qdrant 仅按班级和索引版本过滤；对话网关仅支持一次性 `complete`。材料无学科字段，尚无会话或技能表、Swagger 和 apitest。主规约尚未归档，现有在途第4课规约要求 `/api/ask` 无依据不生成，新会话使用独立入口避免冲突。

## Goals / Non-Goals

**Goals:** 保持现有栈和接口兼容，自存储向上逐层验证，明确消息失败状态及班级授权，把文档声明和路由实现连接到同一个处理器。

**Non-Goals:** 不更换框架、不增加数据库/检索/模型运行依赖，不新增仓库，不执行部署，不以模型或自动测试伪造同伴复核。

## Decisions

1. 存储：新增 `agents`、`conversations`、`messages` 三张主表、`agent_skills` 和 `agent_materials` 两张绑定表及 `skills` 表。技能必须单独存储，五张核心表不能代替技能表。主表保留班级外键，会话保存 owner 和 agent；消息保存 role、content、sources、status、turn 标识和时间。绑定使用复合唯一键及班级一致性约束。所有 DDL 使用 IF NOT EXISTS；材料学科列经 PRAGMA 检查后增量添加，旧材料默认“通用”。不重建已有表。并发采用按请求连接与短事务、同会话生成互斥，网络等待不持有数据库事务；不依赖当前共享连接来保证并发安全。

2. API：`GET/POST /api/agents`、`GET/PUT /api/agents/{id}`；`GET/POST /api/skills`、`GET/PUT/DELETE /api/skills/{id}`；`GET/POST /api/conversations`、`GET /api/conversations/{id}`、`GET/POST /api/conversations/{id}/messages`。智能体写入体包含 name、prompt、enabled、subject、skill_ids、material_ids；技能写入体使用 content 文件文本；会话创建为 agent_id，发消息为 question。统一 401 登录失败、403 非教师、400 参数/同名、404 不可访问或不存在、409 同会话生成中、503 依赖故障；已开始流式后用 error 帧表达失败。新增资源 404 固定 `{ "error": "not_found" }`，旧材料接口跨班及不存在当前均为相同 403，保持兼容。材料上传可选 subject，不传默认通用。

3. 技能解析：用标准库逐行解析中文字段，兼容中英文冒号，第一空行划分头部和正文，字段严格拒绝重复及未知项。适用条件按中文/英文词项与问题重合打分，正分才匹配，最高分优先、并列按 ID；工具字段仅声明 knowledge_search，检索仍为每轮必需步骤，不执行任意工具。提供教师可一键保存的解题引导示例，不向生产数据库自动注入技能。

4. 范围检索：为现有 search 增加可选材料 ID 白名单，在关键词 SQL 和 Qdrant filter 中均应用范围，再做 SQLite 来源授权复核；不可先取全班 top-k 再排除未绑定材料，否则有效绑定资料会被挤出。绑定范围取前4条，随后按 subject 筛选且不补取，重新赋 `[S1]` 编号。通用智能体不筛学科，具体学科严格匹配材料学科。`/api/search` 默认参数保持原行为。

5. 编排：读取会话归属、当前智能体和绑定，检索证据，创建用户消息及 generating 助手占位；历史读取当前轮之前最新6条已完成消息，逆序恢复时间顺序，每条取500字。系统消息放角色及最多一条技能；历史单列，当前用户消息放问题及资料。无资料提示禁止伪造来源，并正常回答。成功终止时检验有效编号、有依据时至少一个引用、无依据时没有编号；失败保存 partial/failed 状态，错误不进入下一轮完成历史。模型输出已经展示的部分可能无法撤回，因此界面必须明确失败状态。

6. 流式：新增网关 `stream`，实际发送 `stream: true`，解析 SSE 跨行数据、增量 choices.delta.content 与结束标志，设超时和大小限制；禁止 complete 后人工切片冒充流式。客户端 meta 包含 conversation_id、message_id、skill、sources，delta 为 text，done 为 message_id/status，error 为 code/message。以 UTF-8 SSE 帧写入和 flush，设置 Cache-Control: no-cache、X-Accel-Buffering: no；连接关闭作为 HTTP 结束边界。写库成功先于 done。断连释放锁并记录状态。

7. 文档：标准库装饰器收集方法、路径、参数/Schema、安全和响应声明，同时用于路由登记，生成 OpenAPI 3 文档并检查重复/缺失声明。不维护一份脱离处理器的静态 JSON。Swagger 页面加载固定版本 Swagger UI 浏览器资源（不增加 Python 依赖），从本地 openapi.json 读取，支持 Bearer Authorize 和主要 JSON 接口试调；流式接口描述四种事件，逐段观察使用会话页面或抓包。资源加载失败时展示说明。

8. 页面：在材料页添加教师配置与会话入口，复用 sessionStorage 和 authorizedFetch。fetch ReadableStream 配合 TextDecoder 的 stream 模式、帧缓冲与空行解帧，不假设一次 read 等于一帧。使用 textContent 渲染模型/技能/资料文本；引用用认证 fetch 拉取，不能只靠无头链接访问受保护材料。

9. 验证：按 URL 每方法脚本，共用标准库 HTTP、SSE 和只读数据库断言辅助。默认启动隔离临时 SQLite 与真实 HTTP 服务，网关/Qdrant 使用可控替身以验证调用参数与流顺序；另外提供显式 live 模式连接现有配置执行实际检索和流式连通性，报告区分两类。真实模式不得修改非测试资源。HTML 使用 html.escape，运行失败仍产报告并非零退出。报告目录 Git 忽略；同伴验证另存真实脱敏证据，不以本地角色切换代替。

## Risks / Trade-offs

- 网关可能不支持流式或代理缓冲 → 真网关连通性与抓包检查，多次 delta 必须在生成完成前到达，部署说明列出 proxy_buffering off。
- 当前 SQLite 共享连接并发事务 → 增量迁移为请求级连接、短事务和同会话互斥，验证中断后不残留 generating。
- 提示词不能绝对保证模型不直接答题 → 检查真实示例输出，保留技能正文和选中技能证据，不声称纯单测能保证全部模型行为。
- 参考原型及 openapi.json 当前不可访问 → 以用户给出的完整清单为验收依据，不声称完全复制其未读取的字段。
- 同伴账号和操作无法自动获得 → 提供可执行步骤与待填写记录，四项必须由实际同伴完成后才打勾。

## Migration Plan

先确认本规约，再按 tasks 分层实施。迁移前备份本机 SQLite（数据不提交），连续初始化验证不重建数据；新增表与学科默认值向后兼容。回滚恢复旧代码即可继续旧登录、材料、检索与问答，保留新增表供后续恢复，不自动删除会话。完成本地与实际网关检查后交付同伴复核步骤，最终同步/归档另行按 OpenSpec 流程执行。
