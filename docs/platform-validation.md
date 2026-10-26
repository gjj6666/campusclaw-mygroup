# AI 应用平台使用与验收

在原 CampusClaw 上增量实现五项能力，继续保留单仓主应用、Qdrant 与同仓 MCP 服务、教师/学生角色和班级隔离。

| 功能要求 | 页面入口 | 实际行为 |
| --- | --- | --- |
| 内置多个 AI 应用 | 应用中心 | 课程答疑、解题引导、学习计划，一键创建自己的会话；展示本班自定义应用 |
| 提示词模板 | 教师配置 → 提示词模板库 | 三个内置模板、本班模板 CRUD、变量预览、应用到角色 |
| 知识库检索 | 知识库、应用配置 → 本班材料绑定 | 沿用关键词/向量/混合检索，回答显示绑定资料出处 |
| 内置及上传 Skill | 教师配置 → 技能中心 | 解题引导、知识整理、学习计划可安装；UTF-8 .md/.txt 可上传、预览和保存 |
| 外部工具与 MCP | 本班 MCP 工具 | 沿用真实发现、工具绑定、鉴权调用、ok/error/denied 与审计 |

## 启动

在项目目录执行 `docker compose up -d --build`。已有 `.env` 继续有效，需包含主应用密钥、网关配置、演示账号密码和 MCP_AUTH_TOKEN。密钥不要提交 Git，不要复制到截图或报告。

打开 `http://127.0.0.1:8000/login`，登录后直接进入 `/tutor` 应用中心。演示教师为 teacher_a，学生为 student_a，密码分别取 `.env` 的 DEMO_TEACHER_PASSWORD 与 DEMO_STUDENT_PASSWORD；旧材料页 `/materials` 和 Swagger `/swagger` 继续可用。

## 手工测试

1. **多个应用：** 学生登录后应看到三个内置应用，点击“开始使用”。系统为该用户创建独立会话并填入示例问题。班内默认角色和技能只在首次启动时建立；重复启动不会复制配置或覆盖教师修改。教师停用后不能新建该应用会话。学生不会看到模板、技能或 MCP 的教师管理入口。
2. **模板：** 教师选择“内置 · 解题引导”，填写 subject（学科）、audience（受众）、goal（目标），点击预览，再应用到角色输入框并保存智能体。需要自己的模板时改名后“保存为本班模板”。修改已有模板正文后先保存再预览。后续修改或删除模板不改变已经保存的角色快照。
3. **内置技能：** 展开内置技能，预览后安装到本班，再到应用配置勾选绑定并保存。重复安装返回本班现有副本，不覆盖编辑内容；手工技能占用同名时明确拒绝，请先给手工技能改名。
4. **上传技能：** 选择 `docs/examples/skill-unit-hint.md`，页面显示文件名、字节数与正文预览。确认后保存，再勾选绑定到应用。输入“请检查解题计算中的单位”，应命中该技能。文件必须为 UTF-8 .md/.txt，最多 32 KiB、8000 字；非法内容拒绝且不落部分数据。编辑框也保留手工创建和更新功能。
5. **知识库：** 教师上传材料，确认索引 ready，在应用中绑定该材料并保存。学生提问后应获得资料出处，点击引用能读取本班原文；他班资料和会话不能读取。
6. **MCP：** 连接 campus-tools，发现 formula_hint / unit_convert，上传或编辑一个工具字段为 `formula_hint@campus-tools` 的技能并绑定应用。提问命中后观察工具状态和教师审计。断开后再次命中为 denied；普通无 MCP 应用独立工作。详细步骤见 `docs/week06-validation.md`。

角色模板变量只生成文本，不执行表达式或二次展开；变量值 1–300 字，渲染结果最多 2000 字。应用角色仍通过已有智能体保存接口持久化，必须显式保存才生效。知识库绑定与应用的学科字段需在应用配置中单独设置。

## Swagger 和接口

教师登录后打开 `/swagger`，点击“使用当前登录鉴权”；新增接口由 endpoint 注解生成，静态副本为 `docs/openapi.json`。

- GET `/api/apps`：目录读取，不产生默认业务数据。
- POST `/api/apps/{key}/launch`：key 为 course-qa / guided-solving / study-plan，请求体 `{}`，返回新 conversation；拒绝客户端附带自定义配置。
- GET/POST `/api/prompt-templates`，GET/PUT/DELETE `/api/prompt-templates/{id}`：内置与班内模板管理，写入只作用于班内自定义模板。
- POST `/api/prompt-templates/render`：`source=builtin` 配 `key`，或 `source=custom` 配 `id`，并提交对应 `variables`。
- GET `/api/skill-library`：内置技能预览和班内 installed_id。
- POST `/api/skills/install`：`{"builtin_key":"study-plan"}`，重复安装返回现有副本，同名冲突 409。
- POST `/api/skills/import`：`{"filename":"skill.md","content":"技能文件全文"}`；复用现有技能语法和 MCP 保存校验。

模板及技能管理仅教师可用；班级取自登录身份。跨班编号与不存在编号统一 404，无登录 401，非教师管理请求 403。新启动接口按需复制服务端可信白名单内容，学生不能通过该接口上传任意提示词或技能。

## 自动化测试

```powershell
python -m unittest discover -s tests
node tests/test_sse.cjs
python apitest/run_all.py
python apitest/verify_mcp_compose.py --platform
python apitest/check_mcp_secrets.py
```

模型故障时可执行 `python apitest/verify_mcp_compose.py --platform --allow-model-unavailable`，保留 MCP 与平台控制面的脱敏证据，仍明确输出真实模型是否完成，不代表完整真实模型验收通过。

`run_all.py` 使用临时库、真实本机 HTTP 应用与同仓 MCP 服务，模型和向量库为隔离替身。新增整链路用例实际完成“选择应用→渲染并应用模板→上传绑定技能→检索本班材料→MCP 调用→ok 审计→断开 denied→普通应用继续回答”，并检查模板快照与出处。HTML 报告位于 `apitest/reports/report.html`，已被 Git 忽略。非法 UTF-8 测试输入在报告中安全替换，不影响报告生成。

Compose 平台脚本保留三个内置应用及“平台综合验收应用”演示配置，并将证据写至被忽略的 `apitest/reports/platform-compose.json`。不随意绑定全班资料；实际有资料的混合检索还依赖嵌入网关可用。

## 本次验证记录（2026-10-21）

- 基线 77 项单元测试、24 个接口脚本及 SSE 测试通过；最终 84 项单元测试、28 个接口脚本与 SSE 测试通过。登录页文案和默认入口调整后，12 项 Web 测试再次通过。
- 验证了并发首次启动只有一套班内配置、独立会话、教师编辑保留、重复迁移及外键、内置技能副本重装、模板快照、非法表达式与上传校验、角色和班级越权。
- 浏览器完成内置应用启动、模板预览和角色保存、实际 Markdown 文件上传与绑定、完整流式展示、模板更新删除后角色保留；学生界面隐藏教师管理入口。
- 已检查默认桌面和 390×844 窄屏布局，窄屏没有水平溢出，视口测试结束恢复默认。截图位于 `apitest/reports/platform-desktop.png` 与 `platform-mobile.png`。
- Swagger 实际试调内置模板渲染返回 200、内置应用启动返回 201；目录、技能安装上传与模板 CRUD 也通过 HTTP 接口测试。
- Compose 三个服务正常，内置应用启动、模板渲染、上传技能、真实 MCP 的 SSE meta ok/denied 和审计通过。实际模型网关仍出现 SSLEOFError，真实完整流式回答失败，真实带资料混合检索尚未完成；保留本变更任务 6.3 及第 6 课原有待验收项，不作成功宣称。

## 数据与回滚

实施前已将数据库备份至 Docker 数据卷 `/app/data/backups/before-ai-platform.db`。新增 prompt_templates、builtin_app_bindings、builtin_skill_bindings 三表，不重写既有 agents/skills 或会话。内置模板和技能原件随源码维护，本班副本由稳定映射关联；删除本班技能后映射级联清理，重新安装不覆盖其他同名技能。

旧版本可以忽略新增表，既有会话结构保持兼容。回滚通常只需恢复旧代码；若恢复数据库备份会丢失备份后的新会话，应仅在需要时执行。本变更尚未归档。
