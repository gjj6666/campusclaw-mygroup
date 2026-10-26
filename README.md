# CampusClaw My Group
本仓库用于学期项目开发。
项目采用 OpenSpec 进行需求与变更管理。

## 个人项目提交

仓库地址：https://github.com/gjj6666/campusclaw-mygroup

项目报告：[项目与LLM链路验证报告（PDF）](output/pdf/CampusClaw_项目与LLM链路验证报告.pdf)。
验证说明及复现命令见 [LLM链路验证](docs/verification/README.md)，完整脱敏请求和实际返回见 [验证证据JSON](docs/verification/llm-traces.json)。

## AI 应用平台

学生登录进入 `/tutor` 学习工作区，教师进入 `/admin` 分栏管理台。学习区采用主导航、助手/会话列表与内容区布局，资料库支持分类、搜索、列表/网格及安全 Markdown 阅读。教师和学生可上传本人个人资料、从共享资料保存副本，并在本人本班不同会话中选择使用；原会话附件仍限原会话。界面支持暖色深浅主题，提问时添加技能、资料与 MCP 鉴权审计继续保留。新增分段预览、逐份索引重建及 MCP 编辑移除。错题本、智能批改、自主学习暂不实现。

操作、接口、权限、备份与测试见 [工作区验收说明](docs/workspace-validation.md)；原有提问上下文契约见 [提问附件验收](docs/question-context-validation.md)。

运行 `docker compose up -d --build` 后访问 [应用中心](http://127.0.0.1:8000/tutor)。完整操作、五项能力验收与网关限制见 [平台使用与验收](docs/platform-validation.md)，上传样例见 [自定义单位分析技能](docs/examples/skill-unit-hint.md)。

```powershell
python -m unittest discover -s tests
node tests/test_sse.cjs
python apitest/run_all.py
python apitest/verify_mcp_compose.py --platform
```

## 第5课：提示词、技能与流式解题助手

已确认增量变更 `add-week05-streaming-tutor`。保持第4课配置和接口，新增会话、智能体、技能、绑定材料检索与真实网关流式调用；不新增Python依赖。

启动仍用 `python main.py` 或 `docker compose up --build`。先填写本机 `.env` 的现有网关、Qdrant与登录配置，登录后打开 `/tutor`。首次启动幂等增量建表，材料学科默认“通用”，不重建旧表；升级前自行备份本机SQLite。

教师按顺序操作：载入并保存解题引导示例 → 上传带学科的材料并确认索引ready → 保存智能体名称、提示词、学科及技能/材料绑定。提示词留空使用默认助教角色。学生选择本班已启用智能体新建会话，提交2–500字问题；fetch携带Bearer自行解帧逐段显示，点击引用以认证请求读取原文。

技能文本示例（总长度最多8000字，名称1–64字、适用条件1–500字）：

```text
名称：解题引导
适用条件：解题 题目 求解 计算 方程 数学 物理
启用：是
工具：knowledge_search

只引导，不直接给最终答案。先请学生列出已知条件和思路，
每次给一个小提示或下一步问题，逐步检查推理。
```

必填名称/适用条件/启用，工具可选，可为knowledge_search或工具名@服务器名；字段不许重复，空行以下必须有正文。“启用：否”及解绑在原会话下一次提问立即生效。路由只在绑定且启用技能中评分，至多选一个；无匹配技能可直接回答。智能体停用后禁止新建，旧会话仍可提问。

会话先在绑定材料范围取前4条，再按学科过滤且不补取；通用智能体不排除学科。最近6条完成消息进入历史，每条上下文最多500字，原文完整保存。无依据时**新会话仍回答且来源为空**；第4课 `/api/ask` 仍为空回答、空来源且不生成。未完成轮次不进入下一轮历史。

| URL | 方法 | 权限与用途 |
| --- | --- | --- |
| `/api/agents` | GET / POST | 登录读取本班；教师创建角色及两类绑定 |
| `/api/agents/{id}` | GET / PUT | 登录读取本班；教师更新配置/绑定 |
| `/api/skills` | GET / POST | 登录读取本班；教师提交技能文件content |
| `/api/skills/{id}` | GET / PUT / DELETE | 登录读取本班；教师更新、删除 |
| `/api/conversations` | GET / POST | 本人本班列表；agent_id选择已启用智能体 |
| `/api/conversations/{id}` | GET | 本人本班会话详情 |
| `/api/conversations/{id}/messages` | GET / POST | 读完整消息；question提问并流式落库 |
| `/swagger`、`/openapi.json` | GET | 公开文档；处理器注解与路由同源 |

所有业务请求使用 `Authorization: Bearer <token>`。Swagger先试调登录，再在Authorize中只粘贴token值；可直接试调检索、技能、智能体、会话接口。Swagger使用固定版本浏览器CDN资源，加载失败仍可打开OpenAPI JSON。流式接口为SSE：meta先给来源和技能，delta只含新增text，成功落库后done；中途失败error且无成功done。同会话同时生成返回409，跨班/他人/不存在的新资源返回相同404，学生写配置403。

反向代理需关闭缓冲，例如Nginx对应路径配置 `proxy_buffering off;`，服务端已发送 `X-Accel-Buffering: no` 并逐帧flush。不能用完整回答切片冒充真实流式。

接口与客户端验证：

```powershell
python -m unittest discover -v
node tests/test_sse.cjs
python apitest/run_all.py
python apitest/run_all.py --live --report apitest/reports/live.html
openspec validate add-week05-streaming-tutor --strict
```

`apitest/cases/`按URL和方法组织，一个接口方法一份脚本。默认运行真实本地HTTP服务、临时SQLite与受控网关/Qdrant替身，断言返回内容及数据库一致；HTML报告放 `apitest/reports/`，失败返回非零退出。live模式读取.env，使用临时数据库和专用测试集合验证实际网关与Qdrant，结束清理测试集合，不使用真实业务数据库。两种报告明确区分，均不提交Git。Node仅用于客户端验证，不是应用运行依赖。

自验结果见 [验证记录](docs/week05-validation.md)；实际同伴四项仍需按 [交叉验证记录](docs/week05-peer-verification.md) 执行并补齐脱敏证据。

暂时没有网关或Qdrant时，可用 `python apitest/demo_server.py` 查看隔离演示（按控制台给出的本机地址打开，测试账号teacher/student，密码local-test-password）。它使用临时数据库与替身，不替代真实环境验收；`--failure` 可复现流式失败页面。按回车关闭演示并清理临时数据。

## 当前实施变更

基础功能来自 OpenSpec 变更 `add-secure-login-class-materials`；登录令牌迁移按 `migrate-login-to-bearer-token` 实施；本班检索与简答按 `add-class-scoped-rag-qa` 实施。

## 功能范围

- 教师和学生使用账号密码换取一小时有效的访问令牌；受保护接口只接受 `Authorization: Bearer <token>`。
- 浏览器将令牌保存在当前标签页的 `sessionStorage`，后续材料读取和上传均携带 Bearer 头；无令牌或失效时跳转到 `/login`。
- 旧版 `campusclaw_session` Cookie 不再授权，升级后需要重新登录。
- 密码以 PBKDF2-HMAC-SHA256 哈希存储，数据库不保存明文密码。
- 访问令牌由服务端 `APP_SECRET_KEY` 签名，密钥只从服务端环境变量读取。
- 班级是材料和知识库的数据边界；列表、详情和上传入库都以服务端当前用户记录中的班级为准。
- 教师可通过 `POST /api/materials` 上传材料，上传成功后写入知识库并出现在本班材料列表。
- 学生调用班级共享资料上传接口 `/api/materials` 会收到权限不足响应；本人会话附件上传允许教师和学生使用，不创建班级共享材料或知识条目。
- 应用提供 `GET /health` 健康检查。
- 教师上传后将材料切成保留原文位置的片段，调用 `course-embedding` 获取 2048 维向量，将正文和词项存入 SQLite、向量存入 Qdrant。仅完整索引成功的片段可检索。
- 教师和学生可用本班关键词、向量、混合检索；回答先检索本班证据，只有命中时才调用 `course-chat`，回答中引用可回溯的片段。

## 本地测试

```powershell
python -m unittest discover -v
```

## 直接启动与验证 token 登录

在项目目录的 PowerShell 中设置本地演示配置，再启动服务。下面的密码仅用于本地演示；已有账号的密码不会因重新设置环境变量而改变。端口为 `8000`。

```powershell
$env:APP_SECRET_KEY = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$env:DATABASE_PATH = 'data/token-login-demo.db'
$env:SEED_DEMO_USERS = 'true'
$env:DEMO_TEACHER_PASSWORD = 'teacher-pass'
$env:DEMO_STUDENT_PASSWORD = 'student-pass'
python main.py
```

另开一个 PowerShell 窗口验证健康检查和登录：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
$body = @{username='teacher_a'; password='teacher-pass'} | ConvertTo-Json
$response = Invoke-WebRequest http://127.0.0.1:8000/api/login -Method Post -ContentType 'application/json' -Body $body
$login = $response.Content | ConvertFrom-Json
$login | Select-Object token_type, expires_in, user
$response.Headers['Set-Cookie']  # 应为空
$token = $login.access_token
Invoke-RestMethod http://127.0.0.1:8000/materials -Headers @{Authorization="Bearer $token"; Accept='application/json'}
```

登录响应包含 `access_token`、`token_type: Bearer`、`expires_in: 3600` 和 `user`，没有登录 Cookie。最后一个请求应返回当前班级的材料；不携带令牌、使用过期令牌，或只携带旧 Cookie 时，受保护 JSON 接口返回 HTTP 401：

```powershell
try { Invoke-WebRequest http://127.0.0.1:8000/materials -Headers @{Accept='application/json'} } catch { [int]$_.Exception.Response.StatusCode }
try { Invoke-WebRequest http://127.0.0.1:8000/materials -Headers @{Accept='application/json'; Cookie='campusclaw_session=old'} } catch { [int]$_.Exception.Response.StatusCode }
```

也可打开 `http://127.0.0.1:8000/login`，用 `teacher_a / teacher-pass` 登录，查看本班材料并上传。浏览器开发者工具的 Network 面板中，登录响应能看到 `access_token`，后续材料与上传请求的 Request Headers 中能看到 `Authorization: Bearer ...`。不要把真实令牌贴到截图或公开日志中。

## Docker Compose 启动

复制示例环境变量文件并填写服务端密钥和可选测试账号密码：

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

`.env` 至少需要：

```text
APP_SECRET_KEY=一段足够长的服务端随机密钥
```

如需自动创建演示账号，设置：

```text
SEED_DEMO_USERS=true
DEMO_TEACHER_PASSWORD=教师演示密码
DEMO_STUDENT_PASSWORD=学生演示密码
```

启动：

```powershell
docker compose up --build
```

Compose 同时启动带持久卷的 Qdrant。开发环境网关配置写入被 Git 忽略的 `.env`：`EMBEDDING_BASE_URL` 只写到 `/v1`，程序分别追加 `/embeddings` 和 `/chat/completions`；`EMBEDDING_MODEL=course-embedding`、`CHAT_MODEL=course-chat`、`EMBEDDING_DIM=2048`。维度只用于本地校验与向量集合建库，嵌入请求只提交 `model` 和 `input`。`EMBEDDING_API_KEY` 仅供服务端使用，不会送给浏览器。直接运行 `python main.py` 时，需另行启动 Qdrant 并设置 `QDRANT_URL`（默认 `http://127.0.0.1:6333`）。

已有材料可幂等补建索引，重复运行不会创建重复片段：

```powershell
python main.py backfill
```

先按上文获取 `$token`，再验证检索和问答。没有命中时 `/api/ask` 返回空回答与空出处，且不调用生成模型：

```powershell
$headers = @{Authorization="Bearer $token"}
$lesson = @{filename='rag-lesson.txt'; content='牛顿第一定律：若物体不受外力，其运动状态保持不变。'} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/materials -Method Post -Headers $headers -ContentType 'application/json' -Body $lesson
Invoke-RestMethod 'http://127.0.0.1:8000/api/search?q=%E7%89%9B%E9%A1%BF%E7%AC%AC%E4%B8%80%E5%AE%9A%E5%BE%8B&mode=keyword' -Headers $headers
$question = @{question='牛顿第一定律说了什么？'} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/ask -Method Post -Headers $headers -ContentType 'application/json' -Body $question
```

上传响应的 `material.index_status` 为 `ready` 才可检索；若为 `failed`，检查网关与 Qdrant，再运行回填命令。检索结果包含 `material_id`、`char_start`、`char_end` 和受 Bearer 保护的 `/materials/{id}` 来源地址。

健康检查：

```powershell
Invoke-RestMethod http://localhost:8000/health
```

演示账号在启用 `SEED_DEMO_USERS=true` 后创建：

- `teacher_a` / `DEMO_TEACHER_PASSWORD`，A 班教师
- `student_a` / `DEMO_STUDENT_PASSWORD`，A 班学生
- `teacher_b` / `DEMO_TEACHER_PASSWORD`，B 班教师
- `student_b` / `DEMO_STUDENT_PASSWORD`，B 班学生

`.env` 不应提交到仓库；真实密钥不得写入前端资源或仓库明文配置。远程部署应通过 HTTPS 传输 Bearer 令牌。


## 第 6 课：MCP 与工具接入

Compose 新增同仓 `mcp-server/`，启动前在本机 `.env` 设置 `MCP_AUTH_TOKEN`。教师在 `/tutor` 登记 `campus-tools`、`http://mcp-demo:8090` 和相同令牌，连接后发现 `formula_hint` 与 `unit_convert`；技能的“工具”字段可填写 `formula_hint@campus-tools`。学生命中技能后真实调用，SSE `meta.tool_calls` 显示 ok/error/denied，教师可在页面查看本班审计。

接口、密钥约束、迁移及验收步骤见 [第6课验收说明](docs/week06-validation.md)，Swagger 位于 `/swagger`，生成文档见 [OpenAPI](docs/openapi.json)。
