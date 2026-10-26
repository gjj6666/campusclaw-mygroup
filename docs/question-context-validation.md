# 提问附件与暖色工作区验收

入口：运行 `docker compose up -d --build` 后打开 http://127.0.0.1:8000/tutor 。教师、学生均可在新建或选择本人会话后使用提问框旁的“技能”“资料”“上传文件”。

## 操作步骤

1. 登录，选择学习助手并新建会话。
2. 点击“技能”选择本班共享技能，或选择上传类型“技能”后上传文件；文件格式示例见 `docs/examples/skill-unit-hint.md`。头部必须包含名称、适用条件、启用，空行后为正文。
3. 点击“资料”选择已就绪共享资料，或选择上传类型“资料”上传自己的文本文件。点击选择器中的“预览”检查内容。
4. 已选内容显示为输入框下方的标签，点击 × 仅取消本轮选择；每轮一个显式技能、最多三份资料。
5. 输入问题并发送。回答来源可点击查看；历史记录保留该轮技能与资料名称。成功后恢复应用默认选择，失败保留草稿，可直接重试。
6. 切换会话，确认原会话附件不会带入。返回原会话，可在选择器中再次添加该会话的上传文件。

## 范围与限制

- 仅支持 UTF-8 `.md/.txt`，每个文件最多 32 KiB。技能沿用原文件格式，最多 8000 字；资料最多 12000 字，单轮私有资料合计最多 18000 字。超限明确拒绝，不静默截断。
- 上传记录仅上传者在原会话可见；教师不能读取学生私有附件。学生不能修改班级共享技能或知识库。取消标签不删除上传记录。
- 显式技能直接作用于本轮，无需命中触发词；上传技能放在用户消息层，不替换教师角色。MCP 引用在上传及调用时校验，断开后显示 denied 并记录审计。
- 未显式选择的字段沿用应用默认绑定和技能自动匹配；显式资料替换默认范围，空列表关闭本轮资料，skill:null 关闭本轮技能。上轮显式选择不自动继承，但原有有限聊天历史仍会提供最近对话文本。
- 共享资料沿用 RAG；小型私有资料直接作为本轮数据，上传本身无需嵌入网关。

## 接口

Swagger 位于 `/swagger`，点击“使用当前登录鉴权”或 Authorize 输入 Bearer。

- `GET /api/conversations/{id}/context`：可选共享内容、原会话附件及默认资料。
- `GET/POST /api/conversations/{id}/attachments`：列出或上传；上传 JSON 为 `{ "kind": "material", "filename": "note.md", "content": "资料正文" }`。
- `GET /api/conversations/{id}/attachments/{attachment_id}`：受保护的原文预览。
- `POST /api/conversations/{id}/messages`：支持可选 context，例如 `{ "question": "请根据资料解释", "context": { "skill": null, "materials": [{ "source": "upload", "id": 1 }] } }`。

`source` 只允许 shared/upload。上下文格式错误返回 400；跨班、跨用户、跨会话和缺失资源统一 404；共享写接口继续对学生返回 403。SSE `meta.context` 和历史 `messages[].context` 为选择快照，`meta.tool_calls` 保留工具状态。

## 自动验收

```powershell
python -m unittest discover -s tests -q
node --test tests/test_sse.cjs
python apitest/run_all.py
```

报告：`apitest/reports/report.html`，由 Git 忽略。新增附件用例使用隔离模型和真实同仓 MCP，覆盖双角色上传、隔离、提示角色、SSE、历史、MCP ok/denied、重复拒绝与无上下文兼容。测试替身成功不代表真实模型网关成功。

运行库部署前备份：容器 `/app/data/backups/before-question-attachments.db`。迁移仅新增附件表及消息 context 列。

## 本机验收结果（2026-10-21）

- 88 项单元测试、29 项接口用例、SSE 解帧测试通过。接口中的模型与向量为隔离替身，MCP 为同仓真实 HTTP 服务。
- 浏览器教师/学生上传与发送成功（隔离模型）、来源预览、历史快照、成功恢复默认、切换会话清理通过；真实 Compose 学生上传与选择通过，真实模型返回生成失败，草稿和上下文保留。
- 390 像素宽度选择三份资料无页面横向溢出，标签换行。主正文/背景对比度 10.89:1，次要文字 5.75:1，主按钮 5.56:1。
- 截图保存在忽略提交的 `apitest/reports/question-desktop.png`、`question-mobile.png`。三个 Compose 服务健康，镜像、Git 可见文件和运行时 MCP 令牌一致性检查通过。
- 真实网关此前存在 TLS EOF 问题，本次真实模型仍未完成回答；真实模型端到端验收保持待完成。未降低 TLS 校验要求。
