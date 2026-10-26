# 个人项目与 LLM 链路验证

仓库：https://github.com/gjj6666/campusclaw-mygroup

PDF：[`CampusClaw_项目与LLM链路验证报告.pdf`](../../output/pdf/CampusClaw_项目与LLM链路验证报告.pdf)

## 验证范围与结果

代码实现覆盖三个内置AI应用（课程答疑、解题引导、学习计划）、提示词模板、知识库检索、内置/上传Skill和真实HTTP MCP。此次工作为既有规约功能的验证与报告提交，不新增产品功能。

2026-10-26：94项单元测试、30项隔离HTTP用例、Node SSE测试、10个OpenSpec严格校验通过。`verify_llm_report.py --live`的八组断言通过，八组请求重放均获得真实模型完整SSE；真实2048维嵌入、专用临时Qdrant集合索引/检索/流式对话亦通过。MCP握手、发现、调用及断开拒绝使用同仓真实服务。

`llm-traces.json`包含完整脱敏请求与响应：

- `cases`：真实应用HTTP处理器、临时数据库，确定性嵌入/向量替身、本地HTTP模型。记录应用请求、meta/delta/done、实际发往HTTP模型的JSON及返回SSE。
- `real_llm_cases`：将上述固定messages快照逐一交给本机配置的真实网关，保存实际请求、SSE原文、增量及拼接正文。历史场景保留固定快照中的历史助手文本，重放不把前一轮真实输出替换进去；其目的为比较同一上下文的传输内容。
- `real_integration`：使用真实模型、嵌入和Qdrant，临时数据库与专用集合；检索证据、流式完成、引用及落库一致性断言。
- `mcp_rpc`/`mcp_audits`：真实Compose演示MCP的握手/发现/调用结果与ok/denied审计。RPC观测记录method/params及result，不保存自动生成的JSON-RPC id。

所有输入为合成教学内容，密钥和模型网关地址不写入证据，Bearer统一脱敏。复现时模型措辞、时间、端口和标识可能变化。真实服务此前有失败历史；本轮通过只表示本轮网络与配置下的结果，不代替持续可用性或同伴人工验收。

### Docker运行环境的独立限制

本机Python验证进程使用Windows已有代理，本轮八组真实模型重放与真实RAG链路通过；Docker容器仍直接连接网关且返回TLS `SSLEOFError`。尝试在单次诊断进程中使用本机代理、移除网关的代理绕过后仍失败，未关闭证书校验。`compose-runtime.json`记录实际8000端口的ok/denied MCP审计和meta，但两轮模型均未done。因此不能将本机通过解释为Docker部署的真实生成已通过；容器网络修复与复验仍待完成。

## 五个问题的验证结论

1. 流式LLM请求为`POST {CHAT_BASE_URL}/chat/completions`，请求JSON仅有`model`、`messages`、`stream:true`。当前配置的模型名为`course-chat`；不显式传temperature/max_tokens/top_p等。模板变量在应用/保存角色时渲染，保存后的角色正文每轮放进system；不会把原始模板对象、变量对象或全模板库都传给模型。历史最多6条已完成消息，每条前500字。
2. 绑定共享知识库后每轮按班级、绑定材料、ready索引版本检索，关键词与向量融合，主对话最多4片段，并可能再按助手学科过滤。本次2287字、8片段的资料只传4片段共1128字；尾部及未绑定材料均未传入。短资料可能恰好全部命中。个人资料/原会话附件是另一种机制：手动选择的正文全文传入user，每轮最多3份，私人正文总计18000字。
3. 绑定本身不保证执行。自动路由在本班已绑定、启用技能中选择一个有匹配的技能；命中后教师管理的Skill正文完整传入system，名称/条件/开关/工具等头部不整体发送。学生/教师临时上传的私有Skill正文以JSON字符串放在user中；禁止私有Skill调用任意MCP。
4. Skill是声明式提示指导与允许工具的组合，不执行Markdown代码块、Python或Shell。解析头部、校验权限、路由选择、检索、按需MCP调用、组装messages、模型流式生成、校验引用、完成落库。`knowledge_search`不触发模型自主调用；检索由主机统一执行，即使没有匹配Skill也可以检索。
5. MCP采用服务端确定性编排。先鉴权调用`tools/call`，参数`{"name":"formula_hint","arguments":{"question":"..."}}`；然后把reference/status/text/message组成JSON数据拼进最后user消息。LLM请求仍仅有model/messages/stream，没有tools、tool_choice、function_call或role=tool，也不把MCP令牌或整份tools/list发给LLM。断开后无远程调用，产生denied审计，模型收到失败状态并继续回答。

## 复现

在本机`.env`配置密钥，启动Compose的Qdrant/MCP服务；不要将`.env`提交Git。

```powershell
docker compose up -d --build
python -m unittest discover -s tests -q
node --test tests/test_sse.cjs
python apitest/run_all.py
python apitest/verify_llm_report.py --live
python apitest/check_mcp_secrets.py
openspec validate --all --strict
```

报告生成脚本为`build_report.py`，需要ReportLab与本机微软雅黑字体；PDF渲染检查使用Poppler。HTML报告与逐页PNG在忽略目录中，正式PDF和合成脱敏证据提交仓库。
