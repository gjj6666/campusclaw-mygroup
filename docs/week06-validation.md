# 第 6 课接入与验收

本应用保持单一 CampusClaw，新增同仓 `mcp-server/`。Compose 启动 `app`、`qdrant`、`mcp-demo`，主机登记地址为 `http://mcp-demo:8090`；浏览器不能用这个 Docker 服务名直接访问，独立 MCP 调试使用 `http://127.0.0.1:8090`。

## 配置与使用

在本机 `.env` 设置随机 `MCP_AUTH_TOKEN`，不要提交其实际值。可用 `python -c "import secrets; print(secrets.token_urlsafe(40))"` 本地生成后填入；避免录屏或将输出放进报告。`.env.example` 只含空占位。

执行 `docker compose up -d --build`。教师登录 `/tutor`，在“本班 MCP 工具”登记 `campus-tools`、`http://mcp-demo:8090` 和 `.env` 中相同的令牌，点击“连接并发现”。令牌字段提交即清空，服务器响应不含密钥。

工具采用 question 字符串输入，发现清单包括 `formula_hint`、`unit_convert`。前者提供公式思路与下一步提示；后者支持 mm/cm/m/km、g/kg、s/min/h、C/F，同量纲转换。例如“把100厘米换算成米”返回 `100 cm = 1 m`。非 question 输入契约的外部工具能展示，但不能保存为本轮技能绑定。

新建并保存技能，再绑定到本班智能体：

```text
名称：公式提示
适用条件：牛顿 力 加速度 解题 计算
启用：是
工具：formula_hint@campus-tools

根据工具数据帮助学生列出已知条件，分步提示，不直接代替学生完成题目。
```

学生选择该智能体新建会话，提问“牛顿第二定律解题：质量和加速度怎样决定力？”。SSE `meta.tool_calls` 包含 `tool_ref` 与 `status`，成功为 `ok`；MCP 故障为 `error`；断开、未发现或权限拒绝为 `denied`。工具数据只进入 user 消息，固定系统规则要求忽略其中指令。普通知识检索保持原有流程。

教师管理页显示最近 200 条本班审计，包括引用、状态、用户、时间。断开后缓存清空，保存同引用返回 400，旧技能再次命中记录 denied，远端不再被调用。重新连接可恢复可用性。

## 独立 MCP 验证

以下 PowerShell 请求的 `$mcpToken` 只在本机从 `.env` 获取，不把值写入脚本或报告：

```powershell
Invoke-RestMethod http://127.0.0.1:8090/health
$headers = @{Authorization="Bearer $mcpToken"}
$body = @{jsonrpc='2.0'; id=1; method='tools/list'; params=@{}} | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8090/mcp -Method Post -Headers $headers -ContentType application/json -Body $body
$body = @{jsonrpc='2.0'; id=2; method='tools/call'; params=@{name='unit_convert'; arguments=@{question='100 cm to m'}}} | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8090/mcp -Method Post -Headers $headers -ContentType application/json -Body $body
```

无令牌或错误令牌返回 401。握手协议版本为 `2024-11-05`；主机执行 initialize、notifications/initialized、tools/list。服务提供 JSON-RPC 错误 -32700/-32600/-32601/-32602，内部错误固定返回 -32603，不附带原始异常。

## 接口与测试

Swagger：`http://127.0.0.1:8000/swagger`，点击“使用当前登录鉴权”，或在 Authorize 输入 CampusClaw 登录令牌。MCP 服务令牌仅写入登记请求，不是 Swagger 的用户登录凭证。动态文档为 `/openapi.json`，导出副本为 `docs/openapi.json`，均由 endpoint 注解生成。

教师接口包括 POST/GET `/api/mcp/servers`、POST `/api/mcp/servers/{id}/connect` 与 `/disconnect`、GET `/api/mcp/servers/{id}/tools`、GET `/api/mcp/audits`。学生访问这些接口返回 403；无登录返回 401；他班编号与不存在编号统一 404。登记的 class_id 不从请求体读取。技能通过既有 POST/PUT `/api/skills` 接口保存，当前发现状态同时用于保存和执行校验。

```powershell
python -m unittest discover -s tests
node tests/test_sse.cjs
python apitest/run_all.py
python apitest/verify_mcp_compose.py
python apitest/check_mcp_secrets.py
```

`run_all.py` 使用临时数据库、真实自建 MCP HTTP 服务，模型与向量库为隔离替身，生成 `apitest/reports/report.html`，报告被 Git 忽略。用例覆盖连接、绑定、学生完整流式、ok/error/denied 审计、注入文本边界、连接失败清缓存、跨班和教师鉴权。

`verify_mcp_compose.py` 使用本机 Compose、已有演示账号及真实模型网关，保留“第6课公式提示”技能和“第6课 MCP 助教”供教师查看，最后重新连接 campus-tools。报告只存选定的脱敏字段至 `apitest/reports/week06-compose.json`。若模型网关不可用，可加 `--allow-model-unavailable` 检查 MCP 与 SSE meta 链路，脚本仍明确输出 `Real model completed: False`，不能据此声称真实模型验收通过。

密钥检查脚本不在命令行传值，检查 Git 可见文件、不可变镜像文件和构建历史，并验证服务端登记值、`.env` 和 MCP 运行时环境一致。服务端 SQLite 中保存凭证，数据库卷应限制本机访问；不把数据库备份纳入 Git。HTTP 客户端拒绝重定向，限制超时、发现数量和返回大小。

## 本次验收记录（2026-10-21）

- 第 5 课基线：71 项单元测试通过。
- 最终回归：77 项单元测试、24 项接口脚本与 SSE 字节边界测试全部通过；HTML 报告为 `apitest/reports/report.html`。
- 新增 MCP 测试验证协议、迁移幂等及外键、绑定兼容、跨班拒绝、失败清缓存、断开竞争、慢响应超时、重定向和响应大小限制。
- Compose 三个服务健康；app 容器通过服务名访问 MCP，真实发现和调用成功；学生 SSE meta 出现 ok，断开后出现 denied，审计记录相应状态，普通健康与关键词检索可用。
- 实际模型网关在容器内出现 `SSLEOFError: UNEXPECTED_EOF_WHILE_READING`，真实流式以 generation_failed 结束。MCP 执行成功与模型生成失败分别记录；模型网关恢复后重新运行不带降级参数的验收脚本。
- 浏览器已验证管理页发现两个真实工具、重复登记错误提示、令牌提交清空；Swagger 使用当前登录鉴权后实际 connect=200、tools=200、MCP 技能保存=201。截图放在被忽略的 `apitest/reports/`。
- 参考课件与原型 OpenAPI 本轮均无法读取，尚未核对课件额外要求；实施依据为已确认规约与用户清单。

## 升级与回滚

迁移重建旧 skills 工具约束，保留技能 id、关联和历史消息，通过 `foreign_key_check` 后提交，失败回滚，重复初始化不重复迁移。新增数据前已在 Docker 数据卷 `/app/data/backups/week06-before-demo.db` 保存快照。旧版本不支持 MCP 技能，回滚需恢复升级前备份及匹配的旧代码；不要让旧版本直接写入含 MCP 技能的新库。本轮规约尚未归档。
