"""Local deterministic browser-verification environment, isolated from real data."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apitest.support import Context

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--failure', action='store_true', help='隔离的流式失败页面验收场景')
    parser.add_argument('--mcp', action='store_true', help='启动真实同仓 MCP 并预登记供浏览器验证')
    args = parser.parse_args()
    context = Context()
    remote = None
    if args.mcp:
        from apitest.mcp_support import DemoMcp
        remote = DemoMcp()
        context.request('/api/mcp/servers', 'POST', {'name': 'campus-tools', 'base_url': remote.url,
                                                   'auth_token': remote.token})
    if args.failure:
        from campusclaw.gateway import GatewayUnavailable
        class FailureChat:
            def stream(self, messages):
                yield '本段用于验证中途失败。'
                raise GatewayUnavailable('simulated browser-test failure')
        context.app.rag.chat = FailureChat()
        context.conversation()
    print(context.base, flush=True)
    print('Local accounts: teacher / student; password: local-test-password', flush=True)
    try:
        input('Press Enter to stop.\n')
    finally:
        context.close()
        if remote:
            remote.close()
