# -*- coding: utf-8 -*-
"""
技能库(消融对象)
================
每个 SkillSpec = {指令文本(注入system), 适用类型, 确定性解法}。
指令文本同时用于: ① 真实后端的提示词注入 ② 确定性后端的 token 成本模拟
—— skill 不是免费的: 更长的 system prompt = 更多 token, 消融报告必须
同时展示收益(Δ成功率)与代价(Δtoken/成本)。

verbose-audit-log 是刻意设计的"装饰性技能": 指令很长、无解法——
用于演示框架识别"纯增成本的无用 skill"的能力(负结果也是结果)。
"""
import re


# ---------- 解法函数(确定性后端用; 先定义, SkillSpec 才能引用) ----------

def _rx(text: str, pattern: str) -> str:
    m = re.search(pattern, text)
    return m.group(1) if m else ""


def _solve_structured(t):
    return {"date": _rx(t.prompt, r"关于(.{3,6})要签约"),
            "amount": _rx(t.prompt, r"人民币(\d+)元"),
            "contact": _rx(t.prompt, r"发件人: (.{2,5})")}


def _solve_schedule(t):
    md = t.metadata
    busy, free = md["busy"], md["free"]
    a = md["req"][0] if md["req"][0] not in busy else next(f for f in free if f not in md["req"])
    return {"A": a, "B": md["req"][1]}


def _solve_expense(t):
    md = t.metadata
    total = round(md["amt"] * md["rate"] * (1.06 if md["taxed"] else 1.0), 2)
    return {"total_cny": total}


def _solve_format(t):
    items = t.metadata["items"]
    limit = t.expected["max_len"]
    lines = []
    for i, it in enumerate(items, 1):
        s = f"{i}. {it}"
        lines.append(s if len(s) <= limit else f"{i}. {it[:limit - 3]}…")
    return {"n_items": len(lines), "numbered": all(l[0].isdigit() for l in lines),
            "max_len": limit, "lines": lines}


def _solve_priority(t):
    rows = t.metadata["rows"]
    ordered = sorted(rows, key=lambda r: (-r[1], r[2]))
    return {"order": ">".join(r[0] for r in ordered)}


# ---------- 技能定义 ----------

from .models import SkillSpec  # noqa: E402

SKILL_STRUCTURED = SkillSpec(
    name="structured-extraction",
    instruction=("结构化抽取: 从邮件/文档中抽取字段时, 只输出 JSON, "
                 "键为 date/amount/contact, 不要输出任何解释文字。"),
    applies_to=("email_extract",),
    solver=_solve_structured)

SKILL_CONFLICT = SkillSpec(
    name="conflict-check",
    instruction=("排程冲突检查: 安排会议前必须对照已有日程逐个时段检查, "
                 "请求时段被占用时从可用时段池中选第一个空闲时段改期。"),
    applies_to=("schedule",),
    solver=_solve_schedule)

SKILL_FX = SkillSpec(
    name="fx-aware-sum",
    instruction=("多币种金额处理: 凡遇外币金额必须按给定汇率换算成人民币; "
                 "服务类费用按公司规定加计6%税额后再汇总。"),
    applies_to=("expense",),
    solver=_solve_expense)

SKILL_FORMAT = SkillSpec(
    name="format-spec",
    instruction=("格式化输出规范: 列表必须逐条编号(1. 2. ...), "
                 "每条严格不超过指定字数, 超长先精简再输出。"),
    applies_to=("doc_format",),
    solver=_solve_format)

SKILL_PRIORITY = SkillSpec(
    name="priority-rules",
    instruction=("优先级排序规则: 先按发件人级别降序(CEO/客户=3 > 直属上级=2 "
                 "> 平级=1 > 外包=0), 同级按剩余时限升序。忽略收件顺序。"),
    applies_to=("priority",),
    solver=_solve_priority)

SKILL_VERBOSE = SkillSpec(
    name="verbose-audit-log",
    instruction=("审计日志规范: 每次处理任务前, 在内部思考中完整复述任务的全部"
                 "输入字段并逐字确认, 记录数据来源、处理时间戳与置信度评估, "
                 "对每个字段执行三遍一致性校验并在日志中保留全部中间版本, "
                 "以确保全链路可追溯。此规范适用于所有任务类型, 不得省略。"),
    applies_to=("email_extract", "schedule", "expense", "doc_format", "priority"),
    solver=None)          # 装饰性技能: 无实际作用, 只增加提示长度

ALL_SKILLS = {s.name: s for s in (SKILL_STRUCTURED, SKILL_CONFLICT, SKILL_FX,
                                  SKILL_FORMAT, SKILL_PRIORITY, SKILL_VERBOSE)}
