## Why

第 4 课已有 Bearer 登录、本班材料检索与有依据的单次问答，但缺少教师配置的解题引导、持久会话和流式交互。第 5 课需在本人学期仓增量实现这些能力，并通过同源接口文档、数据库断言和同伴验证证明班级隔离。

## What Changes

- 幂等新增会话、消息、智能体主表及技能/材料绑定表，并建立技能存储与班内唯一约束。
- 教师维护角色提示词、技能文件、启用状态及本班绑定；学生创建和读取自己的会话。
- 每次提问重读绑定及技能开关，至多选一条技能；绑定材料范围内检索前 4 条后按学科过滤，结合最近 6 条历史进行真实流式生成。
- 新会话无依据时继续回答并返回空引用；保留第 4 课 `/api/search`、`/api/ask` 的既有行为。
- 从处理器注解生成 `/openapi.json`，提供 `/swagger` 实际试调和 Bearer 认证。
- 新增教师配置与学生会话页面，使用 fetch 解帧增量渲染并访问出处。
- 新增按 URL 分目录的 `apitest/` 脚本、一键 HTML 报告、数据库一致性校验及同伴验证记录。

## Capabilities

### New Capabilities

- `tutor-agent-skills`: 本班智能体、角色提示词、技能文件和两类绑定管理。
- `streaming-tutor-conversations`: 会话归属、消息持久化、技能路由、绑定材料检索和流式界面。
- `api-documentation-verification`: 注解同源 OpenAPI、Swagger 试调、接口测试和验证证据。

### Modified Capabilities

无。主规约目录尚无已归档能力；现有在途变更的第 4 课接口保持兼容，本变更新增独立会话入口。

## Impact

涉及 `campusclaw/db.py`、`services.py`、`rag.py`、`vector_store.py`、`gateway.py`、`web.py`，新增技能、会话编排和注解文档模块，以及 `tests/`、`apitest/`、验证记录与 README。复用 Python 标准库、SQLite、Qdrant 和已有网关配置，不增加运行依赖，不新建仓库；真实密钥仅在本机 `.env`，报告与密钥不入 Git 或镜像。现有未提交改动作为第 4 课基线保留。
