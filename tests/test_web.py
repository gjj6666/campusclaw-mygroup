import json
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from threading import Thread

from campusclaw.config import Config
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

    def request(self, path, *, method="GET", data=None, cookie=None, no_redirect=False):
        body = None if data is None else json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body else {},
        )
        if cookie:
            req.add_header("Cookie", cookie)
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

    def login_cookie(self, username, password):
        res = self.request("/api/login", method="POST", data={"username": username, "password": password})
        return res.headers["Set-Cookie"].split(";", 1)[0]

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

    def test_unlogged_protected_page_redirects_to_login(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/materials", no_redirect=True)

        self.assertEqual(ctx.exception.code, 302)
        self.assertEqual(ctx.exception.headers["Location"], "/login")

    def test_login_response_has_no_password_or_secret(self):
        res = self.request("/api/login", method="POST", data={"username": "teacher_a", "password": "teacher-pass"})
        body = res.read().decode("utf-8")

        self.assertNotIn("teacher-pass", body)
        self.assertNotIn("test-server-secret", body)
        self.assertIn("teacher", body)

    def test_browser_form_login_redirects_to_materials(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.form_request(
                "/api/login",
                data={"username": "teacher_a", "password": "teacher-pass"},
                no_redirect=True,
            )

        self.assertEqual(ctx.exception.code, 302)
        self.assertEqual(ctx.exception.headers["Location"], "/materials")
        self.assertIn("campusclaw_session=", ctx.exception.headers["Set-Cookie"])

    def test_teacher_upload_and_class_filtered_list(self):
        teacher_cookie = self.login_cookie("teacher_a", "teacher-pass")
        res = self.request(
            "/api/materials",
            method="POST",
            data={"filename": "lesson.txt", "content": "本班材料"},
            cookie=teacher_cookie,
        )
        self.assertEqual(res.status, 201)

        materials = json.loads(self.request("/materials", cookie=teacher_cookie).read())["materials"]
        self.assertEqual(len(materials), 1)
        self.assertEqual(materials[0]["filename"], "lesson.txt")

        other_cookie = self.login_cookie("teacher_b", "teacher-pass")
        other_materials = json.loads(self.request("/materials?class_id=1", cookie=other_cookie).read())["materials"]
        self.assertEqual(other_materials, [])

        material_id = materials[0]["id"]
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request(f"/materials/{material_id}", cookie=other_cookie)
        self.assertEqual(ctx.exception.code, 403)

    def test_student_direct_upload_is_forbidden(self):
        student_cookie = self.login_cookie("student_a", "student-pass")

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request(
                "/api/materials",
                method="POST",
                data={"filename": "student.txt", "content": "not allowed"},
                cookie=student_cookie,
            )

        self.assertEqual(ctx.exception.code, 403)
        self.assertEqual(self.app.conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0], 0)
        self.assertEqual(self.app.conn.execute("SELECT COUNT(*) FROM knowledge_entries").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
