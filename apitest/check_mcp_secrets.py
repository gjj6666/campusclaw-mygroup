"""Check the local MCP secret without printing it or putting it on argv."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from campusclaw.config import load_dotenv


def main():
    load_dotenv()
    secret = os.environ['MCP_AUTH_TOKEN'].encode()
    assert len(secret) >= 32, 'MCP token too short for local deployment'
    paths = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard']).split(b'\0')
    count = 0
    for raw in paths:
        if not raw: continue
        path = Path(os.fsdecode(raw))
        if path.is_file():
            assert secret not in path.read_bytes(), 'MCP secret found in a Git-visible file'
            count += 1
    assert subprocess.run(['git', 'check-ignore', '-q', '.env']).returncode == 0
    assert subprocess.run(['git', 'check-ignore', '-q', 'apitest/reports/report.html']).returncode == 0
    print('PASS Git-visible files and ignored .env/report:', count)
    images = ['campusclaw-mygroup-app', 'campusclaw-mygroup-mcp-demo']
    scan = ('import sys,pathlib; secret=sys.stdin.buffer.read(); '
            'paths=[p for p in pathlib.Path("/app").rglob("*") if p.is_file()]; '
            'assert all(secret not in p.read_bytes() for p in paths); '
            'assert not pathlib.Path("/app/.env").exists(); print("PASS immutable image filesystem",len(paths))')
    for image in images:
        metadata = subprocess.check_output(['docker', 'image', 'inspect', image])
        history = subprocess.check_output(['docker', 'image', 'history', '--no-trunc', image])
        assert secret not in metadata and secret not in history
        result = subprocess.run(['docker', 'run', '--rm', '-i', '--network', 'none', '--entrypoint', 'python', image, '-c', scan],
                                input=secret, capture_output=True)
        assert result.returncode == 0, 'Image secret check failed'
        print(image, result.stdout.decode().strip())
    verify = ('import json,os,sqlite3; import sys; token=sys.stdin.read(); '
              'c=sqlite3.connect("/app/data/campusclaw.db"); '
              'row=c.execute("SELECT auth_token FROM mcp_servers WHERE class_id=1 AND name=?",("campus-tools",)).fetchone(); '
              'assert row and row[0]==token; print("PASS host registration equals local MCP token")')
    result = subprocess.run(['docker', 'compose', 'exec', '-T', 'app', 'python', '-c', verify], input=secret, capture_output=True)
    assert result.returncode == 0, 'Host token consistency check failed'
    print(result.stdout.decode().strip())
    verify_env = 'import os,sys; assert os.environ["MCP_AUTH_TOKEN"]==sys.stdin.read(); print("PASS MCP runtime token equals local token")'
    result = subprocess.run(['docker', 'compose', 'exec', '-T', 'mcp-demo', 'python', '-c', verify_env], input=secret, capture_output=True)
    assert result.returncode == 0, 'MCP environment consistency check failed'
    print(result.stdout.decode().strip())


if __name__ == '__main__':
    main()
