# CampusClaw My Group
本仓库用于学期项目开发。
项目采用 OpenSpec 进行需求与变更管理。

## 当前实施变更

本次实现以 OpenSpec 变更 `add-secure-login-class-materials` 为唯一实施来源。较早的活动变更 `add-class-scoped-material-ingestion` 与其范围重叠，但缺少密码哈希、服务端密钥、Docker Compose 和健康检查要求，因此不作为本次实现依据。

## 功能范围

- 教师和学生可使用账号密码登录。
- 未登录访问 `/materials`、`/upload` 等受保护页面会跳转到 `/login`。
- 密码以 PBKDF2-HMAC-SHA256 哈希存储，数据库不保存明文密码。
- 会话由服务端 `APP_SECRET_KEY` 签名，密钥只从服务端环境变量读取。
- 班级是材料和知识库的数据边界；列表、详情和上传入库都以服务端会话中的班级为准。
- 教师可通过 `POST /api/materials` 上传材料，上传成功后写入知识库并出现在本班材料列表。
- 学生直接调用上传接口会收到权限不足响应，且不会创建材料或知识库记录。
- 应用提供 `GET /health` 健康检查。

## 本地测试

```powershell
python -m unittest discover -v
```

## Docker Compose 启动

复制示例环境变量文件并填写服务端密钥和可选测试账号密码：

```powershell
Copy-Item .env.example .env
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

健康检查：

```powershell
Invoke-RestMethod http://localhost:8000/health
```

演示账号在启用 `SEED_DEMO_USERS=true` 后创建：

- `teacher_a` / `DEMO_TEACHER_PASSWORD`，A 班教师
- `student_a` / `DEMO_STUDENT_PASSWORD`，A 班学生
- `teacher_b` / `DEMO_TEACHER_PASSWORD`，B 班教师
- `student_b` / `DEMO_STUDENT_PASSWORD`，B 班学生

`.env` 不应提交到仓库；真实密钥不得写入前端资源或仓库明文配置。
