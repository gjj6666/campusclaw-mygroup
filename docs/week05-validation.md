# 第5课实施自验

日期：2026-10-14（Asia/Shanghai）。变更：`add-week05-streaming-tutor`。

## 已验证行为

- SQLite重复初始化保留数据；数据库拒绝跨班绑定；技能同名约束、非法字段校验与绑定原子替换通过。
- Bearer认证、学生写接口403、本人本班会话、他班/他人和不存在相同404通过；智能体停用后既有会话可继续提问。
- 每轮重读技能与绑定、至多一条技能、绑定范围先取前4条再按学科过滤、连续编号及无材料仍作答通过。
- 历史取最近6条已完成消息，每条上下文500字；完整原文保留，失败轮次排除。
- 网关发送stream:true，受控HTTP流产生多次delta；结束前已收到delta，done在提交后发出；断连及异常保存失败/部分状态并释放锁。
- SSE客户端逐字节UTF-8和CRLF跨块解帧测试通过，缺结束事件检测为未完成。
- 第4课本班检索、单次问答无依据不生成行为回归通过。
- 浏览器在隔离HTTP环境中实际完成：教师登录、保存解题引导示例、上传物理材料并索引、保存智能体与两类绑定；学生登录后教师配置隐藏，新建会话、提问、看到引导正文与S1、携带Bearer打开材料原文。
- 浏览器Swagger实际完成：登录200，Authorize输入Bearer，本班智能体GET 200、新建会话POST 201、检索GET 200。Swagger固定版本资源从CDN加载成功，OpenAPI由处理器注解生成。
- 浏览器双标签自验：教师把解题技能改为启用否，学生原会话重复同一问题由引导正文切换为默认回答，无需新建会话；该自验不计为同伴验证。
- 浏览器失败场景自验：收到部分正文后模型失败，页面显示未完成和可读错误，发送按钮恢复可用；无成功结束状态。

## 报告与证据

运行 `python -m unittest discover -v`、`node tests/test_sse.cjs`、`python apitest/run_all.py`。最终数量和结果以本次生成的 `apitest/reports/report.html` 及控制台为准。该目录被Git忽略；浏览器截图 `apitest/reports/browser-tutor.jpg` 为隔离环境自验，不含真实密钥，不算同伴截图。

最终Python自验71项通过；客户端解帧验证通过；接口脚本23项通过（含Swagger页面）；单脚本直接执行通过；Compose配置校验与Git diff空白检查通过。APP_SECRET_KEY、EMBEDDING_API_KEY、CHAT_API_KEY真实值未出现在可跟踪文件；.env和报告未被跟踪，Docker构建上下文显式忽略.env。测试和README中的公开演示密码沿用第4课示例，不是网关密钥。

## 实际环境限制

`python apitest/run_all.py --live --report apitest/reports/live.html` 已尝试，实际材料索引失败，不能宣称真实环境端到端通过。脱敏诊断：嵌入与对话网关均为GatewayUnavailable（底层URLError，无HTTP状态码）；本机Qdrant健康请求无法连接；Docker Desktop Linux引擎管道不存在。临时数据库隔离，未修改真实业务数据库。

解决实际服务连通性后重跑live模式；只有真实产生多次增量、引用落库一致并人工确认引导示例后，才完成任务7.3。密钥仅通过本机.env配置，不贴进记录。四项真实同伴证据仍待执行，见 `week05-peer-verification.md`，自动化不替代同伴复核。
