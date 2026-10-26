from __future__ import annotations
from pathlib import Path

import json
import re
import copy
import threading

from .api import TutorApi
from .openapi import handlers, generate, swagger_page
from .tutor import TutorStore, ApiError
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import Config
from .db import connect, initialize, seed_demo_data
from .rag import InvalidAnswer, RagService, RagUnavailable
from .security import ACCESS_TOKEN_TTL_SECONDS, sign_session, verify_session
from .services import (
    authenticate,
    get_authorized_material,
    get_user_by_id,
    list_materials_for_class,
    upload_material,
)


BEARER_HEADER = re.compile(r"Bearer ([A-Za-z0-9_-]+\.[0-9a-f]{64})", re.IGNORECASE)


class Application:
    def __init__(self, config: Config):
        self.config = config
        self.conn = connect(config.database_path)
        initialize(self.conn)
        # Recover interrupted turns after a process restart; never present them as successful.
        with self.conn:
            self.conn.execute("UPDATE messages SET status=CASE WHEN role='assistant' AND content<>'' "
                              "THEN 'partial' ELSE 'failed' END WHERE status='generating'")
        if config.seed_demo_users:
            seed_demo_data(
                self.conn,
                teacher_password=config.teacher_password,
                student_password=config.student_password,
            )
        self.rag = RagService(self.conn, config)
        self.lock_guard = threading.Lock()
        self.generating = set()

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

    def current_user(self, headers: dict[str, str], conn=None) -> dict[str, Any] | None:
        match = BEARER_HEADER.fullmatch(headers.get("Authorization", ""))
        if not match:
            return None
        payload = verify_session(match.group(1), self.config.secret_key)
        if not payload:
            return None
        return get_user_by_id(conn if conn is not None else self.conn, payload["user_id"])


def create_handler(app: Application) -> type[BaseHTTPRequestHandler]:
    class CampusClawHandler(TutorApi, BaseHTTPRequestHandler):
        server_version = "CampusClaw/0.1"


        def handle_one_request(self):
            self.app = app
            self.conn = connect(app.config.database_path)
            self.rag = copy.copy(app.rag)
            self.rag.conn = self.conn
            try:
                super().handle_one_request()
            finally:
                self.conn.close()

        def _dispatch(self):
            path = urlparse(self.path).path
            try:
                if self.command == 'GET' and path in ('/openapi.json', '/swagger', '/swagger/'):
                    if path == '/openapi.json':
                        self._json(200, generate(type(self)))
                    else:
                        self._html(200, swagger_page())
                    return
                if self.command == 'GET' and path == '/tutor':
                    from .tutor_page import tutor_page
                    self._html(200, tutor_page())
                    return
                if self.command == 'GET' and path == '/admin':
                    from .admin_page import admin_page
                    self._html(200, admin_page())
                    return
                for name, fn in handlers(type(self)):
                    match = fn.route.fullmatch(path)
                    if fn.api['method'] == self.command and match:
                        if not fn.api['public']:
                            # HTML material shell obtains identity via its subsequent Bearer request.
                            if path == '/materials' and not self._wants_json():
                                self._legacy_GET()
                                return
                            user = self._require_login(json_response=True)
                            if not user:
                                return
                            self.store = TutorStore(self.conn, user)
                            if path.startswith(('/api/mcp/', '/api/prompt-templates', '/api/skill-library')):
                                from .tutor import teacher
                                teacher(user)
                            if self.command in ('POST', 'PUT', 'DELETE') and path.startswith(('/api/agents', '/api/skills')):
                                from .tutor import teacher
                                teacher(user)
                        params = {k: v if k == 'key' else int(v) for k, v in match.groupdict().items()}
                        if any(v > 9223372036854775807 or v < 1 for v in params.values() if type(v) is int):
                            raise ApiError(404, 'not_found')
                        getattr(self, name)(**params)
                        return
                if path.startswith('/api/'):
                    self._json(404, {'error': 'not_found'})
                elif self.command == 'GET':
                    self._legacy_GET()
                else:
                    self._json(404, {'error': 'not_found'})
            except ApiError as exc:
                payload = {'error': exc.code}
                if exc.message:
                    payload['message'] = exc.message
                self._json(exc.status, payload)
            except (ValueError, UnicodeError, TypeError) as exc:
                self._json(400, {'error': 'invalid_request', 'message': str(exc)})
            except RagUnavailable:
                self._json(503, {'error': 'search_unavailable'})

        def do_GET(self):
            self._dispatch()

        def do_POST(self):
            self._dispatch()

        def do_PUT(self):
            self._dispatch()

        def do_DELETE(self):
            self._dispatch()

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _legacy_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._redirect("/materials")
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
                if not self._wants_json():
                    from .tutor_page import tutor_page
                    self._html(HTTPStatus.OK, tutor_page(library=True))
                    return
                user = self._require_login(json_response=True)
                if not user:
                    return
                materials = list_materials_for_class(self.conn, class_id=user["class_id"])
                self._json(HTTPStatus.OK, {"user": user, "materials": materials})
                return
            if parsed.path == "/api/search":
                user = self._require_login(json_response=True)
                if not user:
                    return
                query = parse_qs(parsed.query)
                q = query.get("q", [""])[0].strip()
                mode = query.get("mode", ["hybrid"])[0]
                try:
                    limit = int(query.get("limit", ["5"])[0])
                    if not q or len(q) > 2000 or mode not in {"keyword", "vector", "hybrid"}:
                        raise ValueError
                    if mode != "keyword" and app.config.validate_rag():
                        raise RagUnavailable("RAG configuration incomplete")
                    results = self.rag.search(q, user["class_id"], mode, limit)
                except ValueError:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_search"})
                    return
                except RagUnavailable:
                    self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "search_unavailable"})
                    return
                self._json(HTTPStatus.OK, {"results": results})
                return
            if parsed.path.startswith("/materials/"):
                user = self._require_login(json_response=True)
                if not user:
                    return
                material_id = int(parsed.path.rsplit("/", 1)[-1])
                material = get_authorized_material(self.conn, material_id=material_id, class_id=user["class_id"])
                if not material:
                    self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                    return
                self._json(HTTPStatus.OK, {"material": material})
                return
            if parsed.path == "/upload":
                self._html(HTTPStatus.OK, upload_page())
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def _legacy_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/login":
                if not app.config.is_healthy_config:
                    self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "configuration_error"})
                    return
                payload = self._read_payload()
                user = authenticate(self.conn, str(payload.get("username", "")), str(payload.get("password", "")))
                if not user:
                    self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid_credentials"})
                    return
                token = sign_session(user, app.config.secret_key or "")
                self._json(
                    HTTPStatus.OK,
                    {
                        "access_token": token,
                        "token_type": "Bearer",
                        "expires_in": ACCESS_TOKEN_TTL_SECONDS,
                        "user": user,
                    },
                )
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
                    material = upload_material(self.conn, user=user, filename=filename, content=content, subject=payload.get("subject", "通用"))
                except PermissionError:
                    self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                    return
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                if app.config.validate_rag():
                    material["index_status"] = "failed"
                else:
                    material["index_status"] = self.rag.index_material(material["id"])
                if self._is_form_post():
                    self._redirect("/materials")
                else:
                    self._json(HTTPStatus.CREATED, {"material": material})
                return
            if parsed.path == "/api/ask":
                user = self._require_login(json_response=True)
                if not user:
                    return
                if int(self.headers.get("Content-Length", "0")) > 20000:
                    self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "question_too_large"})
                    return
                try:
                    question = self._read_payload().get("question", "")
                    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
                        raise ValueError
                    if app.config.validate_rag():
                        raise RagUnavailable("RAG configuration incomplete")
                    answer = self.rag.answer(question.strip(), user["class_id"])
                except (ValueError, json.JSONDecodeError):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_question"})
                    return
                except RagUnavailable:
                    self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "answer_unavailable"})
                    return
                except InvalidAnswer:
                    self._json(HTTPStatus.BAD_GATEWAY, {"error": "invalid_answer"})
                    return
                self._json(HTTPStatus.OK, answer)
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def _headers_dict(self) -> dict[str, str]:
            return {key: value for key, value in self.headers.items()}

        def _require_login(self, *, json_response: bool = False) -> dict[str, Any] | None:
            user = app.current_user(self._headers_dict(), self.conn)
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
            if length < 0 or length > max(app.config.max_upload_bytes, 65536):
                raise ApiError(413, "request_too_large")
            raw = self.rfile.read(length) if length else b""
            content_type = self.headers.get("Content-Type", "")
            if content_type.startswith("application/json") and raw:
                decoded = json.loads(raw.decode("utf-8"))
                if isinstance(decoded, dict):
                    return decoded
                raise ValueError("请求体必须为JSON对象")
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
            self.send_header("Cache-Control", "no-store")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def _html(self, status: int, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return CampusClawHandler


def login_page(*, error: bool = False) -> str:
    error_html = '<p class="error">账号或密码错误，请重试。</p>' if error else ""
    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>登录</title>
  <script>{theme_bootstrap()}</script><style>{page_css()}</style>
</head>
<body data-page="login">
  <main class="login-layout">
    <section class="brand-panel">
      <p class="eyebrow">CampusClaw</p>
      <h1>CampusClaw AI 应用平台</h1>
      <p>登录后体验课程答疑、解题引导与学习计划。教师可以配置提示词模板、上传技能、绑定本班知识库并接入外部 MCP 工具。</p>
      <div class="stat-grid">
        <span><strong>教师</strong>上传入库</span>
        <span><strong>学生</strong>提问与私有附件</span>
        <span><strong>班级</strong>数据隔离</span>
      </div>
    </section>
    <section class="panel login-card">
      <button type="button" class="secondary" aria-label="切换深浅主题" onclick="toggleCampusTheme()">◐ 主题</button><p class="eyebrow">账号登录</p>
      <h2>进入本班空间</h2>
      <p class="muted">使用教师或学生账号登录。</p>
      {error_html}
      <form id="login-form">
        <label>账号<input name="username" autocomplete="username" required></label>
        <label>密码<input name="password" type="password" autocomplete="current-password" required></label>
        <button type="submit">登录</button>
      </form>
      <p id="login-error" class="error" hidden></p>
      <noscript><p class="error">登录需要启用 JavaScript。</p></noscript>
      <div class="demo">
        <strong>演示账号</strong>
        <span>如已启用演示账号，可使用 teacher_a 或 student_a；密码由服务端环境变量配置。</span>
      </div>
    </section>
  </main>
  {client_script()}
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
  <script>{theme_bootstrap()}</script><style>{page_css()}</style>
</head>
<body data-page="upload">
  <main class="page">
    <nav class="app-nav"><a href="/materials">本班材料</a><span>教师上传</span></nav>
    <section class="panel workspace">
      <p class="eyebrow">教师工作台</p>
      <h1>上传教学材料</h1>
      <p class="muted">材料解析成功后会写入当前教师所属班级的知识库，并出现在本班材料列表。</p>
      <form id="upload-form">
        <label>材料名称<input name="filename" value="lesson.txt" required></label>
        <label>正文内容<textarea name="content" rows="10" placeholder="粘贴本节课讲义、知识点或课堂资料..." required></textarea></label>
        <button type="submit">上传入库</button>
      </form>
      <p id="upload-status" role="status"></p>
    </section>
  </main>
  {client_script()}
</body>
</html>
""".strip()


def materials_page() -> str:
    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>本班材料</title>
  <script>{theme_bootstrap()}</script><style>{page_css()}</style>
</head>
<body data-page="materials"><p><a href="/tutor">AI 应用平台与教师配置</a> · <a href="/swagger">Swagger接口文档</a></p>
  <main class="page">
    <nav class="app-nav"><strong>CampusClaw</strong><span id="class-label"></span></nav>
    <section class="panel workspace">
      <div class="topline dashboard-head">
        <div>
          <p class="eyebrow">本班知识库</p>
          <h1>教学材料</h1>
          <p id="user-label" class="muted"></p>
        </div>
        <a id="upload-link" class="button-link" href="/upload" hidden>上传材料</a>
      </div>
      <div class="summary-grid">
        <span><strong id="material-count">0</strong> 可用材料</span>
        <span><strong id="class-count"></strong> 当前班级</span>
        <span><strong id="role-count"></strong> 当前角色</span>
      </div>
      <ul id="materials-list" class="materials"></ul>
      <section id="material-detail" hidden><h2 id="detail-title"></h2><pre id="detail-content"></pre></section>
      <section class="rag-panel">
        <h2>检索本班资料</h2>
        <form id="search-form">
          <label>关键词或问题<input name="q" maxlength="2000" required></label>
          <label>检索方式<select name="mode"><option value="hybrid">混合</option><option value="keyword">关键词</option><option value="vector">向量</option></select></label>
          <button type="submit">检索</button>
        </form>
        <ul id="search-results" class="materials"></ul>
        <h2>依据资料简答</h2>
        <form id="ask-form"><label>问题<input name="question" maxlength="2000" required></label><button type="submit">提问</button></form>
        <p id="answer-status" role="status"></p>
        <p id="answer-text"></p>
        <ul id="answer-sources" class="materials"></ul>
      </section>
      <p id="materials-error" class="error" hidden></p>
    </section>
  </main>
  {client_script()}
</body>
</html>
""".strip()


def client_script() -> str:
    return """
<script>
(() => {
  const tokenKey = 'campusclaw_access_token';
  const page = document.body.dataset.page;

  function goToLogin() {
    sessionStorage.removeItem(tokenKey);
    location.replace('/login');
  }

  async function authorizedFetch(path, options = {}) {
    const token = sessionStorage.getItem(tokenKey);
    if (!token) {
      goToLogin();
      return null;
    }
    const response = await fetch(path, {
      ...options,
      cache: 'no-store',
      headers: { ...(options.headers || {}), Authorization: `Bearer ${token}` }
    });
    if (response.status === 401) {
      goToLogin();
      return null;
    }
    return response;
  }

  if (page === 'login') {
    document.getElementById('login-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const error = document.getElementById('login-error');
      error.hidden = true;
      try {
        const response = await fetch('/api/login', {
          method: 'POST',
          cache: 'no-store',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: form.elements.username.value,
            password: form.elements.password.value
          })
        });
        const result = await response.json();
        if (!response.ok || !result.access_token) {
          throw new Error(response.status === 401 ? '账号或密码错误，请重试。' : '登录失败，请稍后重试。');
        }
        sessionStorage.setItem(tokenKey, result.access_token);
        location.assign(result.user.role === 'teacher' ? '/admin' : '/tutor');
      } catch (cause) {
        error.textContent = cause.message || '登录失败，请稍后重试。';
        error.hidden = false;
      }
    });
  }

  if (page === 'materials') {
    function showSources(list, sources) {
      list.replaceChildren();
      for (const source of sources) {
        const row = document.createElement('li');
        const excerpt = document.createElement('span');
        excerpt.textContent = `${source.citation ? `[${source.citation}] ` : ''}${source.material_title} · 片段 ${source.ordinal + 1}：${source.content}`;
        const link = document.createElement('a');
        link.href = source.url;
        link.textContent = '查看原文';
        link.addEventListener('click', async (event) => {
          event.preventDefault();
          const response = await authorizedFetch(source.url, { headers: { Accept: 'application/json' } });
          if (!response || !response.ok) return;
          const payload = await response.json();
          document.getElementById('detail-title').textContent = payload.material.title;
          document.getElementById('detail-content').textContent = payload.material.content;
          document.getElementById('material-detail').hidden = false;
          document.getElementById('material-detail').scrollIntoView();
        });
        row.append(excerpt, link);
        list.append(row);
      }
    }
    document.getElementById('search-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const list = document.getElementById('search-results');
      list.replaceChildren();
      try {
        const params = new URLSearchParams({ q: form.elements.q.value, mode: form.elements.mode.value });
        const response = await authorizedFetch(`/api/search?${params}`);
        if (!response) return;
        if (!response.ok) throw new Error('检索暂不可用。');
        const payload = await response.json();
        showSources(list, payload.results);
        if (!payload.results.length) list.textContent = '未检索到本班资料。';
      } catch (cause) { list.textContent = cause.message || '检索失败。'; }
    });
    document.getElementById('ask-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const status = document.getElementById('answer-status');
      const answer = document.getElementById('answer-text');
      const list = document.getElementById('answer-sources');
      answer.textContent = '';
      list.replaceChildren();
      status.textContent = '正在检索依据…';
      try {
        const response = await authorizedFetch('/api/ask', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: form.elements.question.value })
        });
        if (!response) return;
        if (!response.ok) throw new Error('问答暂不可用。');
        const payload = await response.json();
        if (payload.status === 'no_evidence') { status.textContent = '未检索到依据，因此没有生成回答。'; return; }
        status.textContent = '根据本班资料回答：';
        answer.textContent = payload.answer;
        showSources(list, payload.sources);
      } catch (cause) { status.textContent = cause.message || '问答失败。'; }
    });
    (async () => {
      try {
        const response = await authorizedFetch('/materials', { headers: { Accept: 'application/json' } });
        if (!response) return;
        if (!response.ok) throw new Error('材料加载失败。');
        const result = await response.json();
        const role = result.user.role === 'teacher' ? '教师' : '学生';
        const classText = `#${result.user.class_id}`;
        document.getElementById('class-label').textContent = `班级 ${classText}`;
        document.getElementById('class-count').textContent = classText;
        document.getElementById('role-count').textContent = role;
        document.getElementById('user-label').textContent = `${result.user.username} · ${role} · 服务端班级隔离已启用`;
        document.getElementById('material-count').textContent = String(result.materials.length);
        document.getElementById('upload-link').hidden = result.user.role !== 'teacher';
        const list = document.getElementById('materials-list');
        if (result.materials.length === 0) {
          const empty = document.createElement('li');
          empty.textContent = '本班还没有可用材料。教师上传后会在这里出现。';
          list.append(empty);
        }
        for (const material of result.materials) {
          const row = document.createElement('li');
          const title = document.createElement('strong');
          title.textContent = material.title;
          const view = document.createElement('button');
          view.type = 'button';
          view.textContent = '查看';
          view.addEventListener('click', async () => {
            try {
              const detail = await authorizedFetch(`/materials/${material.id}`, { headers: { Accept: 'application/json' } });
              if (!detail) return;
              if (!detail.ok) throw new Error('材料读取失败。');
              const payload = await detail.json();
              document.getElementById('detail-title').textContent = payload.material.title;
              document.getElementById('detail-content').textContent = payload.material.content;
              document.getElementById('material-detail').hidden = false;
            } catch (cause) {
              const error = document.getElementById('materials-error');
              error.textContent = cause.message || '材料读取失败。';
              error.hidden = false;
            }
          });
          row.append(title, view);
          list.append(row);
        }
      } catch (cause) {
        const error = document.getElementById('materials-error');
        error.textContent = cause.message || '材料加载失败。';
        error.hidden = false;
      }
    })();
  }

  if (page === 'upload') {
    (async () => {
      try {
        const response = await authorizedFetch('/materials', { headers: { Accept: 'application/json' } });
        if (!response) return;
        if (!response.ok) throw new Error('身份验证失败。');
        const result = await response.json();
        if (result.user.role !== 'teacher') {
          location.replace('/materials');
          return;
        }
      } catch (cause) {
        document.getElementById('upload-status').textContent = cause.message || '身份验证失败。';
      }
    })();
    document.getElementById('upload-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const status = document.getElementById('upload-status');
      status.textContent = '';
      try {
        const response = await authorizedFetch('/api/materials', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: form.elements.filename.value, content: form.elements.content.value })
        });
        if (!response) return;
        if (!response.ok) throw new Error(response.status === 403 ? '权限不足。' : '上传失败，请检查材料内容。');
        status.textContent = '上传成功，正在返回材料列表。';
        location.assign('/materials');
      } catch (cause) {
        status.textContent = cause.message || '上传失败。';
      }
    });
  }
})();
</script>
""".strip()


def theme_bootstrap() -> str:
    return Path(__file__).with_name("static").joinpath("theme.js").read_text(encoding="utf-8")


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
input, textarea, select { width: 100%; box-sizing: border-box; border: 1px solid #b9c7d1; border-radius: 6px; padding: 12px; font: inherit; background: #fbfcfd; }
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
.rag-panel { margin-top: 30px; padding-top: 24px; border-top: 1px solid #e1e8ee; display: grid; gap: 12px; }
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
""".strip() + "\n" + Path(__file__).with_name("static").joinpath("warm.css").read_text(encoding="utf-8")


def serve(config: Config) -> None:
    app = Application(config)
    port = 8000
    server = ThreadingHTTPServer(("0.0.0.0", port), create_handler(app))
    server.serve_forever()
