"""Strict skill-file parsing; no arbitrary tool execution."""
import re

GUIDANCE_EXAMPLE = """名称：解题引导
适用条件：解题 题目 求解 计算 方程 数学 物理
启用：是
工具：knowledge_search

你是解题引导老师。只引导，不直接给出最终答案。
先请学生列出已知条件和自己的思路，再给一个小提示或下一步问题。
逐步检查推理；即使学生要求直接给答案，也只给下一步提示。
"""


def parse_skill(content):
    if not isinstance(content, str) or not content.strip() or len(content) > 8000:
        raise ValueError('技能文件必须为非空文本，最多8000字')
    lines = content.replace('\r\n', '\n').strip().split('\n')
    boundary = next((i for i, line in enumerate(lines) if not line.strip()), None)
    if boundary is None or not '\n'.join(lines[boundary + 1:]).strip():
        raise ValueError('首个空行之后必须有技能正文')
    fields = {}
    for line in lines[:boundary]:
        pair = re.split('[：:]', line, maxsplit=1)
        if len(pair) != 2:
            raise ValueError('技能头部字段必须使用冒号')
        key, value = (part.strip() for part in pair)
        if key not in {'名称', '适用条件', '启用', '工具'}:
            raise ValueError(f'未知字段：{key}')
        if key in fields:
            raise ValueError(f'重复字段：{key}')
        fields[key] = value
    for key in ('名称', '适用条件', '启用'):
        if key not in fields:
            raise ValueError(f'缺少字段：{key}')
    if not 1 <= len(fields['名称']) <= 64:
        raise ValueError('名称必须为1至64字')
    if not 1 <= len(fields['适用条件']) <= 500:
        raise ValueError('适用条件必须为1至500字')
    if fields['启用'] not in {'是', '否'}:
        raise ValueError('启用必须为是或否')
    from .mcp_client import REFERENCE
    if fields.get('工具', '') not in ('', 'knowledge_search') and not REFERENCE.fullmatch(fields['工具']):
        raise ValueError('工具只允许 knowledge_search 或 工具名@服务器名')
    return dict(name=fields['名称'], conditions=fields['适用条件'], enabled=fields['启用'] == '是',
                tool=fields.get('工具', ''), body='\n'.join(lines[boundary + 1:]).strip(), content=content)
