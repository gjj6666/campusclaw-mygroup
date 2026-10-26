import json
from dataclasses import replace
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from threading import Thread

from campusclaw.config import Config
from campusclaw.security import sign_session
from campusclaw.rag import RagService
from campusclaw.gateway import GatewayUnavailable
from tests.test_rag import FakeChat, FakeEmbedder, FakeVectors
from campusclaw.services import create_user
from campusclaw.web import Application, create_handler


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Config(
            secret_key="test-server-secret",
            database_path=f"{self.tmp.name}/test.db",
            max_upload_bytes=1024,
            seed_demo_users=False,
            teacher_password=None,
            student_password=None,
        )
        self.app = Application(self.config)
        self.app.conn.execute("INSERT INTO classes (id, name) VALUES (1, 'A 班'), (2, 'B 班')")
        create_user(self.app.conn, username="teacher_a", password="teacher-pass", role="teacher", class_id=1)
        create_user(self.app.conn, username="student_a", password="student-pass", role="student", class_id=1)
        create_user(self.app.conn, username="teacher_b", password="teacher-pass", role="teacher", class_id=2)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(self.app))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.app.close()
        self.tmp.cleanup()

    def request(self, path, *, method="GET", data=None, token=None, cookie=None, authorization=None, accept=None, no_redirect=False):
        body = None if data is None else json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body else {},
        )
        if cookie:
            req.add_header("Cookie", cookie)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        if authorization is not None:
            req.add_header("Authorization", authorization)
        if accept is not None:
            req.add_header("Accept", accept)
        opener = urllib.request.build_opener(NoRedirect) if no_redirect else urllib.request.build_opener()
        return opener.open(req)

    def form_request(self, path, *, data, no_redirect=False):
        body = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        opener = urllib.request.build_opener(NoRedirect) if no_redirect else urllib.request.build_opener()
        return opener.open(req)

    def login_token(self, username, password):
        res = self.request("/api/login", method="POST", data={"username": username, "password": password})
        self.assertNotIn("Set-Cookie", res.headers)
        return json.loads(res.read())["access_token"]

    def test_rag_endpoints_require_bearer_and_keep_class_scope(self):
        with self.assertRaises(urllib.error.HTTPError) as missing:
            self.request("/api/search?q=alpha&mode=keyword")
        self.assertEqual(missing.exception.code, 401)
        with self.assertRaises(urllib.error.HTTPError) as missing_ask:
            self.request("/api/ask", method="POST", data={"question": "alpha"})
        self.assertEqual(missing_ask.exception.code, 401)

        config = replace(self.config, embedding_base_url="http://example/v1", embedding_api_key="test",
                         chat_base_url="http://example/v1", chat_api_key="test", embedding_dim=2)
        self.app.config = config
        chat = FakeChat()
        self.app.rag = RagService(self.app.conn, config, embedder=FakeEmbedder(), chat=chat,
                                  vectors=FakeVectors())
        teacher = self.login_token("teacher_a", "teacher-pass")
        student = self.login_token("student_a", "student-pass")
        other = self.login_token("teacher_b", "teacher-pass")
        created = json.loads(self.request("/api/materials", method="POST", token=teacher,
                                          data={"filename": "a.txt", "content": "alpha lesson"}).read())
        self.assertEqual(created["material"]["index_status"], "ready")
        search = json.loads(self.request("/api/search?q=alpha&mode=keyword", token=student).read())
        self.assertEqual(search["results"][0]["material_id"], created["material"]["id"])
        self.assertEqual(json.loads(self.request("/api/search?q=alpha&mode=keyword", token=other).read())["results"], [])
        self.assertEqual(json.loads(self.request("/api/ask", method="POST", token=student,
                                                 data={"question": "alpha"}).read())["status"], "answered")
        self.assertEqual(json.loads(self.request("/api/ask", method="POST", token=other,
                                                 data={"question": "unknown"}).read())["status"], "no_evidence")
        self.assertEqual(chat.calls, 1)
        with self.assertRaises(urllib.error.HTTPError) as invalid:
            self.request("/api/search?q=alpha&mode=bad", token=teacher)
        self.assertEqual(invalid.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as empty:
            self.request("/api/ask", method="POST", token=student, data={"question": ""})
        self.assertEqual(empty.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as too_large:
            self.request("/api/ask", method="POST", token=student, data={"question": "x" * 21000})
        self.assertEqual(too_large.exception.code, 413)
        self.app.rag.embedder.fail = True
        with self.assertRaises(urllib.error.HTTPError) as unavailable:
            self.request("/api/search?q=alpha&mode=vector", token=student)
        self.assertEqual(unavailable.exception.code, 503)
        self.app.rag.embedder.fail = False
        self.app.rag.chat.complete = lambda messages: (_ for _ in ()).throw(GatewayUnavailable("offline"))
        with self.assertRaises(urllib.error.HTTPError) as chat_error:
            self.request("/api/ask", method="POST", token=student, data={"question": "alpha"})
        self.assertEqual(chat_error.exception.code, 503)

    def test_health_ok_and_missing_secret_unhealthy(self):
        res = self.request("/health")
        self.assertEqual(res.status, 200)
        self.assertEqual(json.loads(res.read())["status"], "ok")

        unhealthy = Application(
            Config(
                secret_key=None,
                database_path=":memory:",
                max_upload_bytes=1024,
                seed_demo_users=False,
                teacher_password=None,
                student_password=None,
            )
        )
        status, payload = unhealthy.health()
        self.assertEqual(status, 503)
        self.assertIn("APP_SECRET_KEY", payload["missing"])

    def test_login_without_secret_is_rejected(self):
        self.app.config = Config(
            secret_key=None,
            database_path=self.config.database_path,
            max_upload_bytes=1024,
            seed_demo_users=False,
            teacher_password=None,
            student_password=None,
        )

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/login", method="POST", data={"username": "teacher_a", "password": "teacher-pass"})

        self.assertEqual(ctx.exception.code, 503)

    def test_unlogged_json_materials_requires_token(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/materials", no_redirect=True)

        self.assertEqual(ctx.exception.code, 401)

    def test_login_response_has_no_password_or_secret(self):
        res = self.request("/api/login", method="POST", data={"username": "teacher_a", "password": "teacher-pass"})
        body = res.read().decode("utf-8")
        payload = json.loads(body)

        self.assertNotIn("teacher-pass", body)
        self.assertNotIn("test-server-secret", body)
        self.assertEqual(payload["token_type"], "Bearer")
        self.assertEqual(payload["expires_in"], 3600)
        self.assertEqual(payload["user"]["role"], "teacher")
        self.assertIn("access_token", payload)
        self.assertEqual(res.headers["Cache-Control"], "no-store")
        self.assertNotIn("Set-Cookie", res.headers)

    def test_form_login_returns_json_without_cookie(self):
        res = self.form_request(
            "/api/login", data={"username": "teacher_a", "password": "teacher-pass"}
        )
        self.assertEqual(res.status, 200)
        self.assertIn("access_token", json.loads(res.read()))
        self.assertNotIn("Set-Cookie", res.headers)

    def test_wrong_password_returns_no_token(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/login", method="POST", data={"username": "teacher_a", "password": "wrong"})

        self.assertEqual(ctx.exception.code, 401)
        self.assertNotIn("access_token", ctx.exception.read().decode("utf-8"))
        self.assertNotIn("Set-Cookie", ctx.exception.headers)

    def test_bearer_required_and_old_cookie_rejected(self):
        token = self.login_token("teacher_a", "teacher-pass")
        bad_headers = [
            {"authorization": f"Basic {token}"},
            {"authorization": f"Bearer {token} extra"},
            {"authorization": f"Bearer {token}tampered"},
            {"cookie": f"campusclaw_session={token}"},
        ]
        for headers in bad_headers:
            with self.subTest(headers=headers), self.assertRaises(urllib.error.HTTPError) as ctx:
                self.request("/materials", **headers)
            self.assertEqual(ctx.exception.code, 401)
        expired = sign_session({"id": 1}, self.config.secret_key, ttl_seconds=-1)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/materials", method="POST", token=expired,
                         data={"filename": "x.txt", "content": "secret"})
        self.assertEqual(ctx.exception.code, 401)
        self.assertEqual(self.app.conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0], 0)

    def test_token_uses_current_role_and_class_and_deleted_user_is_rejected(self):
        token = self.login_token("teacher_a", "teacher-pass")
        self.app.conn.execute(
            "UPDATE users SET role = 'student', class_id = 2 WHERE username = 'teacher_a'"
        )
        self.app.conn.commit()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/materials", method="POST", token=token,
                         data={"filename": "x.txt", "content": "secret"})
        self.assertEqual(ctx.exception.code, 403)
        self.app.conn.execute("DELETE FROM users WHERE username = 'teacher_a'")
        self.app.conn.commit()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/materials", token=token)
        self.assertEqual(ctx.exception.code, 401)

    def test_html_shell_contains_no_protected_data_or_token(self):
        token = self.login_token("teacher_a", "teacher-pass")
        self.request("/api/materials", method="POST", token=token,
                     data={"filename": "private-lesson.txt", "content": "private class content"})
        page = self.request("/materials", accept="text/html")
        html = page.read().decode("utf-8")
        self.assertIn("sessionStorage", html)
        self.assertNotIn(token, html)
        self.assertNotIn("teacher_a", html)
        self.assertNotIn("private-lesson.txt", html)
        self.assertNotIn("private class content", html)
        self.assertEqual(page.headers["Cache-Control"], "no-store")

    def test_teacher_upload_and_class_filtered_list(self):
        teacher_token = self.login_token("teacher_a", "teacher-pass")
        res = self.request(
            "/api/materials",
            method="POST",
            data={"filename": "lesson.txt", "content": "本班材料"},
            token=teacher_token,
        )
        self.assertEqual(res.status, 201)

        materials = json.loads(self.request("/materials", token=teacher_token).read())["materials"]
        self.assertEqual(len(materials), 1)
        self.assertEqual(materials[0]["filename"], "lesson.txt")

        other_token = self.login_token("teacher_b", "teacher-pass")
        other_materials = json.loads(self.request("/materials?class_id=1", token=other_token).read())["materials"]
        self.assertEqual(other_materials, [])

        material_id = materials[0]["id"]
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request(f"/materials/{material_id}", token=other_token)
        self.assertEqual(ctx.exception.code, 403)

    def test_student_direct_upload_is_forbidden(self):
        student_token = self.login_token("student_a", "student-pass")

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request(
                "/api/materials",
                method="POST",
                data={"filename": "student.txt", "content": "not allowed"},
                token=student_token,
            )

        self.assertEqual(ctx.exception.code, 403)
        self.assertEqual(self.app.conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0], 0)
        self.assertEqual(self.app.conn.execute("SELECT COUNT(*) FROM knowledge_entries").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
