"""Validated per-class policies and deterministic source-preserving splits."""
import json
import re
from dataclasses import asdict

from .chunking import Chunk, split_text


def normalize(data, config):
    if not isinstance(data, dict) or set(data) - {'mode', 'size', 'ratio', 'separator', 'trim'}:
        raise ValueError('非法分段策略字段')
    if data.get('mode', 'auto') == 'auto':
        return dict(mode='auto', size=config.chunk_size, overlap=config.chunk_overlap, separator='paragraph', trim=True)
    if data.get('mode') != 'custom':
        raise ValueError('分段模式须为auto/custom')
    size, ratio = data.get('size'), data.get('ratio')
    separator, trim = data.get('separator', 'paragraph'), data.get('trim', True)
    if type(size) is not int or not 100 <= size <= 2000 or type(ratio) is not int or not 0 <= ratio <= 40:
        raise ValueError('长度须为100–2000整数，重叠比例须为0–40整数')
    if separator not in ('paragraph', 'newline', 'sentence') or type(trim) is not bool:
        raise ValueError('非法分隔符或清理选项')
    return dict(mode='custom', size=size, ratio=ratio, overlap=size * ratio // 100, separator=separator, trim=trim)


def current(conn, class_id, config):
    row = conn.execute('SELECT * FROM class_index_policies WHERE class_id=?', (class_id,)).fetchone()
    return dict(policy=normalize(json.loads(row['policy']), config) if row else normalize({}, config),
                revision=row['revision'] if row else 0)


def public_policy(policy):
    return {k: v for k, v in policy.items() if k != 'overlap'} | {'ratio': policy.get('ratio', round(policy['overlap'] * 100 / policy['size'], 2))}


def split_policy(content, policy):
    if policy['mode'] == 'auto':
        return split_text(content, size=policy['size'], overlap=policy['overlap'])
    separators = dict(paragraph=r'\n\s*\n', newline=r'\n', sentence=r'(?<=[。！？.!?])')
    cuts = [m.end() for m in re.finditer(separators[policy['separator']], content)] + [len(content)]
    size, overlap, chunks, start = policy['size'], policy['overlap'], [], 0
    while start < len(content):
        hard_end = min(start + size, len(content))
        boundaries = [p for p in cuts if start + overlap < p <= hard_end]
        end = max(boundaries) if boundaries else hard_end
        left, right = start, end
        if policy['trim']:
            while left < right and content[left].isspace(): left += 1
            while right > left and content[right - 1].isspace(): right -= 1
        if content[left:right].strip():
            chunks.append(Chunk(len(chunks), left, right, content[left:right]))
        if end == len(content): break
        start = max(start + 1, end - overlap)
    return chunks


def preview(content, policy):
    if not isinstance(content, str) or not content.strip() or len(content.encode('utf-8')) > 1048576:
        raise ValueError('预览正文须为非空UTF-8文本，最多1 MiB')
    chunks = split_policy(content, policy)
    return dict(total=len(chunks), chunks=[asdict(c) for c in chunks[:20]], has_more=len(chunks) > 20)
