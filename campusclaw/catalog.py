"""Trusted built-in content. Public callers receive copies, never mutable originals."""
from copy import deepcopy

_SKILLS = {
    'guided-solving': dict(name='解题引导', description='通过提问、检查和逐步提示帮助学生解题。', content='''名称：解题引导
适用条件：解题 题目 求解 计算 方程 数学 物理 牛顿
启用：是
工具：knowledge_search

先询问学生的已知条件和思路，再给下一步提示。逐步检查推理，不直接给出最终答案。'''),
    'knowledge-summary': dict(name='知识整理', description='整理资料概念、关系和复习要点。', content='''名称：知识整理
适用条件：整理 总结 概念 知识 复习 课程 定义
启用：是
工具：knowledge_search

根据可用资料整理核心概念、概念关系和复习要点，明确区分资料事实与补充解释，不编造出处。'''),
    'study-plan': dict(name='学习计划', description='根据目标和可用时间安排可执行的学习任务。', content='''名称：学习计划
适用条件：计划 安排 学习 目标 时间 备考
启用：是

先确认学习目标、当前基础与可用时间，再给出分阶段任务、检查点和调整建议；缺少条件时先提问。'''),
}
_TEMPLATES = {
    'course-qa': dict(name='课程答疑', description='解释概念、举例并检查学生理解。',
                      content='你是{{subject}}课程助教，面向{{audience}}。本次学习目标是{{goal}}。清晰解释概念，结合例子，最后给出一个检查理解的问题；有资料时按出处回答。'),
    'guided-solving': dict(name='解题引导', description='分步提示，帮助学生独立完成推理。',
                           content='你是{{subject}}解题教练，面向{{audience}}。目标是{{goal}}。先确认已知量和学生思路，每次只给下一步提示并检查推理，不直接给出最终答案。'),
    'study-plan': dict(name='学习计划', description='澄清目标并制定阶段任务与检查点。',
                       content='你是{{subject}}学习规划助手，面向{{audience}}。目标是{{goal}}。先确认基础和可用时间，再给出可执行的阶段任务、复习安排与检查点。'),
}
_APPS = {
    'course-qa': dict(name='课程答疑', description='解释课程概念，结合本班资料梳理知识。',
                      example='请解释牛顿第二定律，并总结质量、力和加速度的关系。', skill='knowledge-summary', icon='问'),
    'guided-solving': dict(name='解题引导', description='从已知条件开始，分步提示你的下一步思路。',
                           example='牛顿第二定律解题：已知质量和加速度，应该如何分析力？', skill='guided-solving', icon='解'),
    'study-plan': dict(name='学习计划', description='明确学习目标，安排阶段任务和复习检查点。',
                       example='我每天有30分钟，想在两周内复习力学，如何安排学习计划？', skill='study-plan', icon='计'),
}


def skills():
    return deepcopy(_SKILLS)


def templates():
    return deepcopy(_TEMPLATES)


def apps():
    return deepcopy(_APPS)
