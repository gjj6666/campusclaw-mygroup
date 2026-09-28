from __future__ import annotations

import json
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import Config
from .db import connect, initialize, seed_demo_data
from .security import sign_session, verify_session
from .services import (
    authenticate,
    get_authorized_material,
    list_materials_for_class,
    upload_material,
)


SESSION_COOKIE = "campusclaw_session"


class Application:
    def __init__(self, config: Config):
        self.config = config
        self.conn = connect(config.database_path)
        initialize(self.conn)
        if config.seed_demo_users:
            seed_demo_data(
                self.conn,
                teacher_password=config.teacher_password,
                student_password=config.student_password,
            )

    def health(self) -> tuple[int, dict[str, Any]]:
        missing = self.config.missing_config
        if missing:
            return HTTPStatus.SERVICE_UNAVAILABLE, {"status": "unhealthy", "missing": missing}
        try:
            self.conn.execute("SELECT 1").fetchone()
        except Exception:
            return HTTPStatus.SERVICE_UNAVAILABLE, {"status": "unhealthy", "database": "unavailable"}
        return HTTPStatus.OK, {"status": "ok"}

    def close(self) -> None:
        self.conn.close()

    def current_user(self, headers: dict[str, str]) -> dict[str, Any] | None:
        cookie = SimpleCookie(headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        token = morsel.value if morsel else None
        return verify_session(token, self.config.secret_key)


def create_handler(app: Application) -> type[BaseHTTPRequestHandler]:
    class CampusClawHandler(BaseHTTPRequestHandler):
        server_version = "CampusClaw/0.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                destination = "/materials" if app.current_user(self._headers_dict()) else "/login"
                self._redirect(destination)
                return
            if parsed.path == "/health":
                status, payload = app.health()
                self._json(status, payload)
                return
            if parsed.path == "/login":
                query = parse_qs(parsed.query)
                self._html(HTTPStatus.OK, login_page(error=bool(query.get("error"))))
                return
            if parsed.path == "/materials":
                user = self._require_login()
                if not user:
                    return
                materials = list_materials_for_class(app.conn, class_id=user["class_id"])
                if self._wants_json():
                    self._json(HTTPStatus.OK, {"materials": materials})
                else:
                    self._html(HTTPStatus.OK, materials_page(user, materials))
                return
            if parsed.path.startswith("/materials/"):
                user = self._require_login()
                if not user:
                    return
                material_id = int(parsed.path.rsplit("/", 1)[-1])
                material = get_authorized_material(app.conn, material_id=material_id, class_id=user["class_id"])
                if not material:
                    self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                    return
                self._json(HTTPStatus.OK, {"material": material})
                return
            if parsed.path == "/upload":
                user = self._require_login()
                if not user:
                    return
                if user["role"] != "teacher":
                    self._html(HTTPStatus.FORBIDDEN, "权限不足")
                    return
                self._html(HTTPStatus.OK, upload_page())
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/login":
                if not app.config.is_healthy_config:
                    self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "configuration_error"})
                    return
                payload = self._read_payload()
                user = authenticate(app.conn, str(payload.get("username", "")), str(payload.get("password", "")))
                if not user:
                    if self._is_form_post():
                        self._redirect("/login?error=1")
                    else:
                        self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid_credentials"})
                    return
                token = sign_session(user, app.config.secret_key or "")
                if self._is_form_post():
                    self._redirect("/materials", headers={"Set-Cookie": cookie_header(token)})
                else:
                    self._json(HTTPStatus.OK, {"user": user}, headers={"Set-Cookie": cookie_header(token)})
                return
            if parsed.path == "/api/materials":
                user = self._require_login(json_response=True)
                if not user:
                    return
                if user["role"] != "teacher":
                    self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                    return
                if int(self.headers.get("Content-Length", "0")) > app.config.max_upload_bytes:
                    self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "file_too_large"})
                    return
                payload = self._read_payload(raw_ok=True)
                filename = str(payload.get("filename") or self.headers.get("X-Filename") or "material.txt")
                raw_content = payload.get("content")
                if isinstance(raw_content, str):
                    content = raw_content.encode("utf-8")
                else:
                    content = payload.get("_raw", b"")
                try:
                    material = upload_material(app.conn, user=user, filename=filename, content=content)
                except PermissionError:
                    self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                    return
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                if self._is_form_post():
                    self._redirect("/materials")
                else:
                    self._json(HTTPStatus.CREATED, {"material": material})
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def _headers_dict(self) -> dict[str, str]:
            return {key: value for key, value in self.headers.items()}

        def _require_login(self, *, json_response: bool = False) -> dict[str, Any] | None:
            user = app.current_user(self._headers_dict())
            if user:
                return user
            if json_response:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "login_required"})
            else:
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/login")
                self.end_headers()
            return None

        def _read_payload(self, *, raw_ok: bool = False) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b""
            content_type = self.headers.get("Content-Type", "")
            if content_type.startswith("application/json") and raw:
                decoded = json.loads(raw.decode("utf-8"))
                if isinstance(decoded, dict):
                    return decoded
            if content_type.startswith("application/x-www-form-urlencoded") and raw:
                parsed = parse_qs(raw.decode("utf-8"))
                return {key: values[-1] for key, values in parsed.items()}
            if raw_ok:
                return {"_raw": raw}
            return {}

        def _is_form_post(self) -> bool:
            return self.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded")

        def _wants_json(self) -> bool:
            accept = self.headers.get("Accept", "")
            return not accept or "application/json" in accept

        def _redirect(self, location: str, *, headers: dict[str, str] | None = None) -> None:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", location)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()

        def _json(
            self,
            status: int,
            payload: dict[str, Any],
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def _html(self, status: int, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return CampusClawHandler


def cookie_header(token: str) -> str:
    return f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/"


def login_page(*, error: bool = False) -> str:
    error_html = '<p class="error">账号或密码错误，请重试。</p>' if error else ""
    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>登录</title>
  <style>{page_css()}</style>
</head>
<body>
  <main class="login-layout">
    <section class="brand-panel">
      <p class="eyebrow">CampusClaw</p>
      <h1>班级教学材料知识库</h1>
      <p>教师上传材料后自动进入本班知识库，学生只能查看自己班级的内容。权限和班级过滤都在服务端执行。</p>
      <div class="stat-grid">
        <span><strong>教师</strong>上传入库</span>
        <span><strong>学生</strong>只读访问</span>
        <span><strong>班级</strong>数据隔离</span>
      </div>
    </section>
    <section class="panel login-card">
      <p class="eyebrow">账号登录</p>
      <h2>进入本班空间</h2>
      <p class="muted">使用教师或学生账号登录。</p>
      {error_html}
      <form method="post" action="/api/login">
        <label>账号<input name="username" autocomplete="username" required></label>
        <label>密码<input name="password" type="password" autocomplete="current-password" required></label>
        <button type="submit">登录</button>
      </form>
      <div class="demo">
        <strong>演示账号</strong>
        <span>teacher_a / teacher-pass</span>
        <span>student_a / student-pass</span>
      </div>
    </section>
  </main>
</body>
</html>
""".strip()


def upload_page() -> str:
    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>上传材料</title>
  <style>{page_css()}</style>
</head>
<body>
  <main class="page">
    <nav class="app-nav"><a href="/materials">本班材料</a><span>教师上传</span></nav>
    <section class="panel workspace">
      <p class="eyebrow">教师工作台</p>
      <h1>上传教学材料</h1>
      <p class="muted">材料解析成功后会写入当前教师所属班级的知识库，并出现在本班材料列表。</p>
      <form method="post" action="/api/materials">
        <label>材料名称<input name="filename" value="lesson.txt" required></label>
        <label>正文内容<textarea name="content" rows="10" placeholder="粘贴本节课讲义、知识点或课堂资料..." required></textarea></label>
        <button type="submit">上传入库</button>
      </form>
    </section>
  </main>
</body>
</html>
""".strip()


def materials_page(user: dict[str, Any], materials: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        f"""
        <li>
          <div>
            <strong>{escape(item['title'])}</strong>
            <small>材料 #{item['id']} · 知识库记录 #{item['knowledge_entry_id']}</small>
          </div>
          <a href="/materials/{item['id']}">查看</a>
        </li>
        """
        for item in materials
    )
    if not rows:
        rows = '<li class="empty"><strong>本班还没有可用材料</strong><small>教师上传后会在这里出现。</small></li>'
    upload_link = '<a class="button-link" href="/upload">上传材料</a>' if user["role"] == "teacher" else ""
    role_label = "教师" if user["role"] == "teacher" else "学生"
    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>本班材料</title>
  <style>{page_css()}</style>
</head>
<body>
  <main class="page">
    <nav class="app-nav"><strong>CampusClaw</strong><span>班级 #{user["class_id"]}</span></nav>
    <section class="panel workspace">
      <div class="topline dashboard-head">
        <div>
          <p class="eyebrow">本班知识库</p>
          <h1>教学材料</h1>
          <p class="muted">{escape(user["username"])} · {role_label} · 服务端班级隔离已启用</p>
        </div>
        {upload_link}
      </div>
      <div class="summary-grid">
        <span><strong>{len(materials)}</strong> 可用材料</span>
        <span><strong>#{user["class_id"]}</strong> 当前班级</span>
        <span><strong>{role_label}</strong> 当前角色</span>
      </div>
      <ul class="materials">{rows}</ul>
    </section>
  </main>
</body>
</html>
""".strip()


def page_css() -> str:
    return """
body { margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; color: #17202a; background: #eef3f7; }
.login-layout { min-height: 100vh; display: grid; grid-template-columns: minmax(320px, 1fr) minmax(320px, 440px); gap: 28px; align-items: stretch; padding: 32px; box-sizing: border-box; }
.brand-panel, .panel { border: 1px solid #d7e0e7; border-radius: 8px; box-sizing: border-box; }
.brand-panel { display: flex; flex-direction: column; justify-content: center; padding: 46px; color: #fff; background: linear-gradient(135deg, #124e78, #1b6b61 58%, #9a6b22); min-height: 520px; }
.brand-panel h1 { max-width: 620px; font-size: 44px; line-height: 1.12; margin: 0 0 18px; }
.brand-panel p { max-width: 620px; font-size: 18px; line-height: 1.7; margin: 0; color: #edf7f6; }
.stat-grid, .summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 28px; }
.stat-grid span, .summary-grid span { border: 1px solid rgba(255,255,255,.28); border-radius: 8px; padding: 14px; background: rgba(255,255,255,.1); }
.stat-grid strong, .summary-grid strong { display: block; font-size: 24px; margin-bottom: 4px; }
.auth-shell, .page { min-height: 100vh; display: grid; place-items: center; padding: 32px; box-sizing: border-box; }
.page { place-items: start center; }
.panel { width: min(900px, 100%); background: #fff; padding: 30px; box-shadow: 0 18px 40px rgba(26, 38, 52, .1); }
.login-card { align-self: center; width: 100%; }
.workspace { margin-top: 18px; }
.eyebrow { margin: 0 0 10px; color: #1b6b61; font-weight: 700; text-transform: uppercase; font-size: 13px; }
h1, h2 { margin: 0 0 10px; }
h1 { font-size: 32px; }
h2 { font-size: 28px; }
.muted { margin: 0 0 22px; color: #617182; line-height: 1.6; }
form { display: grid; gap: 16px; }
label { display: grid; gap: 7px; font-weight: 700; }
input, textarea { width: 100%; box-sizing: border-box; border: 1px solid #b9c7d1; border-radius: 6px; padding: 12px; font: inherit; background: #fbfcfd; }
input:focus, textarea:focus { outline: 3px solid #cfe7df; border-color: #1b6b61; }
textarea { resize: vertical; }
button, .button-link { border: 0; border-radius: 6px; background: #124e78; color: white; padding: 12px 16px; font: inherit; font-weight: 700; text-decoration: none; cursor: pointer; }
button:hover, .button-link:hover { background: #0e4165; }
.demo { margin-top: 22px; display: grid; gap: 7px; color: #435466; font-size: 14px; padding-top: 18px; border-top: 1px solid #e1e8ee; }
.error { border: 1px solid #f1b8b8; background: #fff2f2; color: #9b1c1c; padding: 10px 12px; border-radius: 6px; }
.topline { display: flex; align-items: start; justify-content: space-between; gap: 16px; }
.dashboard-head { padding-bottom: 18px; border-bottom: 1px solid #e1e8ee; }
.summary-grid { color: #284253; margin: 22px 0; }
.summary-grid span { border-color: #d7e0e7; background: #f7faf8; }
.materials { list-style: none; padding: 0; margin: 8px 0 0; display: grid; gap: 12px; }
.materials li { border: 1px solid #d9e1e8; border-radius: 8px; padding: 16px; display: flex; align-items: center; justify-content: space-between; gap: 16px; background: #fcfdfb; }
.materials small { display: block; margin-top: 5px; color: #617182; }
.materials a { font-weight: 700; }
.empty { color: #617182; }
.app-nav { width: min(900px, 100%); margin: 0; display: flex; justify-content: space-between; align-items: center; color: #435466; }
a { color: #124e78; }
@media (max-width: 820px) {
  .login-layout { grid-template-columns: 1fr; padding: 18px; }
  .brand-panel { min-height: auto; padding: 28px; }
  .brand-panel h1 { font-size: 34px; }
  .stat-grid, .summary-grid { grid-template-columns: 1fr; }
  .topline, .materials li { flex-direction: column; align-items: stretch; }
}
""".strip()


def serve(config: Config) -> None:
    app = Application(config)
    port = 8000
    server = ThreadingHTTPServer(("0.0.0.0", port), create_handler(app))
    server.serve_forever()
