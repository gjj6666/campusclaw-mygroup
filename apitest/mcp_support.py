"""Run the repository's actual MCP server in an isolated HTTP listener."""
import importlib.util
from pathlib import Path
import secrets
import threading


def server_module():
    spec = importlib.util.spec_from_file_location('campus_mcp_demo', Path(__file__).resolve().parents[1] / 'mcp-server' / 'server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DemoMcp:
    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.module = server_module()
        self.server = self.module.create_server(('127.0.0.1', 0), self.token)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
