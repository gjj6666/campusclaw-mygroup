"""Run isolated HTTP acceptance scripts and always produce a local HTML report."""
import argparse
import html
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apitest.support import Context


def live_case(c):
    material = c.material('牛顿第一定律：物体不受外力时保持静止或匀速直线运动。解题先分析受力，再判断运动状态。')
    c.evidence.append({'stage': '真实材料索引', 'index_status': material['index_status']})
    assert material['index_status'] == 'ready', '真实索引未完成'
    skill = c.skill()
    agent = c.agent(subject='物理', skill_ids=[skill['id']], material_ids=[material['id']])
    conv = c.conversation(agent)
    status, frames = c.request(f"/api/conversations/{conv['id']}/messages", 'POST',
                               {'question': '牛顿第一定律解题：物体不受外力，应该如何分析运动状态？请引导我，不要直接给最终答案。'}, 'student')
    c.evidence.append({'stage': '真实会话流式', 'status': status, 'events': [event for event, _ in frames],
                       'answer': ''.join(data['text'] for event, data in frames if event == 'delta'),
                       'meta': next((data for event, data in frames if event == 'meta'), None),
                       'error': next((data for event, data in frames if event == 'error'), None)})
    assert status == 200 and frames[-1][0] == 'done', '真实流式未成功完成'
    deltas = [d['text'] for e, d in frames if e == 'delta']
    assert len(deltas) > 1, '真实网关未产生多次增量'
    meta = frames[0][1]
    assert meta['skill']['id'] == skill['id'] and meta['sources']
    answer = ''.join(deltas)
    row = c.row('messages', meta['message_id'])
    assert row['content'] == answer and row['status'] == 'completed'
    c.evidence.append({'mode': '真实网关与Qdrant', 'delta_count': len(deltas), 'sources': [s['citation'] for s in meta['sources']],
                       'skill': meta['skill']['name'], 'answer': answer, 'note': '真实示例已生成，解题引导效果请人工复核；不替代同伴验证。'})
    # Only the isolated collection created for this run is removed.
    c.app.rag.vectors._request('DELETE', c.app.rag.vectors.path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='本机.env真实网关/Qdrant，使用临时数据库和专用测试集合')
    parser.add_argument('--report', default='apitest/reports/report.html')
    args = parser.parse_args()
    scripts = sorted(Path(__file__).with_name('cases').rglob('*.py'))
    results = []
    targets = [(Path('live'), live_case)] if args.live else [(p, None) for p in scripts]
    for path, fn in targets:
        context = None
        start = time.monotonic()
        try:
            context = Context(live=args.live)
            if fn is None:
                spec = importlib.util.spec_from_file_location('api_case', path)
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                fn = module.run
            fn(context)
            results.append((str(path), True, time.monotonic() - start, json.dumps(context.evidence, ensure_ascii=False)))
            print(f'PASS {path}')
        except Exception as exc:
            # Avoid exception payloads containing account credentials, tokens, or gateway data.
            last = traceback.extract_tb(exc.__traceback__)[-1]
            detail = {'error_type': type(exc).__name__, 'location': f'{Path(last.filename).name}:{last.lineno}',
                      'assertion': last.line if isinstance(exc, AssertionError) else '',
                      'evidence': context.evidence if context else []}
            results.append((str(path), False, time.monotonic() - start, json.dumps(detail, ensure_ascii=False)))
            print(f'FAIL {path}: {type(exc).__name__}')
        finally:
            if context:
                context.close()
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    rows = ''.join(f'<tr><td>{html.escape(name)}</td><td>{"通过" if ok else "失败"}</td><td>{seconds:.2f}s</td><td><pre>{html.escape(detail)}</pre></td></tr>' for name, ok, seconds, detail in results)
    passed = sum(r[1] for r in results)
    report.write_text(f'<!doctype html><meta charset="utf-8"><title>接口测试报告</title><style>body{{font-family:system-ui;margin:30px}}td,th{{border:1px solid #ddd;padding:10px}}pre{{white-space:pre-wrap;max-width:700px}}</style><h1>接口测试报告</h1><p>{"真实环境" if args.live else "隔离HTTP环境，网关/Qdrant替身"} · {passed}/{len(results)}通过</p><p>不替代同伴账号交叉验证。报告不含令牌或密码。</p><table><tr><th>接口脚本</th><th>结果</th><th>耗时</th><th>脱敏证据</th></tr>{rows}</table>', encoding='utf-8')
    print(f'Report: {report.resolve()}')
    return 0 if results and passed == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
