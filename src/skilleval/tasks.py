"""
中文办公任务集(合成, seed 固定可复现)
====================================
5 类任务 × 每类 10 条 = 50 条。判分 = 输出字段与 expected 精确匹配
(金额允许 ±0.01 容差)—— 不用 LLM judge, 归因干净。

每类任务对应基线 agent 的一种已知缺陷(无 skill 时的系统性失败模式):
  email_extract → 输出非结构化(wrong_format)
  schedule      → 不检查日历冲突(conflict)
  expense       → 漏汇率换算(missing_fx)
  doc_format    → 超字数/无编号(over_limit)
  priority      → 按收件时间而非优先级排序(wrong_order)
"""

import random

from .models import TaskSpec

N_PER_TYPE = 10

DATES = [
    "3月12日",
    "3月15日",
    "4月2日",
    "4月18日",
    "5月6日",
    "5月20日",
    "6月1日",
    "6月11日",
    "7月3日",
    "7月22日",
]
AMOUNTS = [12800, 4500, 96000, 780, 15600, 2300, 64000, 8900, 33000, 5100]
CONTACTS = [
    "王经理",
    "李总监",
    "赵老师",
    "陈主管",
    "刘工",
    "孙经理",
    "周总监",
    "吴老师",
    "郑主管",
    "冯工",
]
SLOTS = [
    "周一 10:00",
    "周一 14:00",
    "周二 09:30",
    "周二 16:00",
    "周三 11:00",
    "周三 15:00",
    "周四 10:00",
    "周四 14:30",
]
CURRENCIES = [("美元", 7.2), ("欧元", 7.8), ("日元", 0.048), ("港币", 0.92)]
CATEGORIES = [
    ("差旅", False),
    ("餐饮", False),
    ("设备采购", False),
    ("咨询服务", True),
    ("软件服务", True),
    ("培训", True),
]
PEOPLE = ["小张", "小刘", "小陈", "小赵", "小王"]
LEVELS = [("CEO", 3), ("客户", 3), ("直属上级", 2), ("平级同事", 1), ("外包", 0)]
HOURS = [2, 6, 12, 24, 48, 72]
BULLETS = [
    "确认项目里程碑",
    "更新风险清单",
    "同步客户反馈",
    "评审设计方案",
    "安排下一轮排期",
    "整理会议纪要",
]


def _email_extract(rng: random.Random, i: int) -> TaskSpec:
    date, amount, contact = DATES[i], AMOUNTS[i], CONTACTS[i]
    prompt = (
        f"【邮件】发件人: {contact}\n"
        f"主题: 合同条款确认\n\n"
        f"您好, 关于{date}要签约的采购合同, 总金额为人民币{amount}元, "
        f"请贵方财务在签约前完成审批。有任何问题直接联系我。\n"
    )
    return TaskSpec(
        f"ee{i:02d}",
        "email_extract",
        prompt,
        {"date": date, "amount": str(amount), "contact": contact},
    )


def _schedule(rng: random.Random, i: int) -> TaskSpec:
    slots = rng.sample(SLOTS, 4)
    busy = slots[:2]  # 已占用
    free = slots[2:]  # 可用
    r1, r2 = rng.sample(SLOTS, 2)
    # 两个请求: 一个撞占用时段(须改期到 free), 一个本来就空闲
    req1 = busy[i % 2]
    req2 = free[i % 2]
    prompt = (
        f"【排程】我已有的日程占用: {busy[0]}、{busy[1]}。\n"
        f"新会议请求: A会议想约 {req1}; B会议想约 {req2}。\n"
        f"可用时段池: {', '.join(SLOTS)}。\n"
        f"请为 A、B 安排不冲突的时段, 输出 A/B 各自最终时段。\n"
    )
    return TaskSpec(
        f"sc{i:02d}",
        "schedule",
        prompt,
        {"A": next(f for f in free if f != req2), "B": req2},
        metadata={"busy": busy, "free": free, "req": [req1, req2]},
    )


def _expense(rng: random.Random, i: int) -> TaskSpec:
    cur_name, rate = CURRENCIES[i % len(CURRENCIES)]
    cat, taxed = CATEGORIES[i % len(CATEGORIES)]
    amt = 1000 + i * 137
    total = round(amt * rate * (1.06 if taxed else 1.0), 2)
    prompt = (
        f"【报销】员工{PEOPLE[i % len(PEOPLE)]}提交一笔{cat}费用: "
        f"{amt}{cur_name}。汇率: 1{cur_name}={rate}人民币。"
        f"公司规定{'服务类' if taxed else '非服务类'}费用{'需加计6%税额' if taxed else '不加税'}。"
        f"请输出报销总额(人民币, 保留两位小数)。\n"
    )
    return TaskSpec(
        f"xp{i:02d}",
        "expense",
        prompt,
        {"total_cny": total},
        metadata={"amt": amt, "rate": rate, "taxed": taxed},
    )


def _doc_format(rng: random.Random, i: int) -> TaskSpec:
    items = rng.sample(BULLETS, 4)
    limit = 12  # 每行字数上限(含编号)
    prompt = (
        "【格式化】把以下要点整理成会议纪要, 要求: 每条加编号(1. 2. ...), "
        f"每条不超过{limit}个字符(超长请精简), 逐行输出。\n"
        + "\n".join(f"- {it}" for it in items)
        + "\n"
    )
    return TaskSpec(
        f"df{i:02d}",
        "doc_format",
        prompt,
        {"n_items": 4, "numbered": True, "max_len": limit},
        metadata={"items": items},
    )


def _priority(rng: random.Random, i: int) -> TaskSpec:
    # 4 个级别必须互不相同(否则期望顺序有并列, ground truth 歧义)
    picked = rng.sample(LEVELS, 4)
    rows = [(nm, lv, rng.choice(HOURS)) for nm, lv in picked]
    recv = rng.sample(range(4), 4)  # 收件顺序(与优先级无关)
    prompt = (
        "【排序】按优先级排序待处理邮件。规则应考虑: 发件人级别高者优先, "
        "级别相同则时限近者优先。\n"
        + "\n".join(
            f"- {PEOPLE[j]} 转发, 发件人: {r[0]}, 时限: {r[2]}小时内, 收件序号{recv[j]}"
            for j, r in enumerate(rows)
        )
        + "\n"
        "请输出排序后的发件人序列(用>连接)。\n"
    )
    ordered = sorted(rows, key=lambda r: (-r[1], r[2]))
    return TaskSpec(
        f"pr{i:02d}",
        "priority",
        prompt,
        {"order": ">".join(r[0] for r in ordered)},
        metadata={"rows": rows, "recv": recv},
    )


GENERATORS = {
    "email_extract": _email_extract,
    "schedule": _schedule,
    "expense": _expense,
    "doc_format": _doc_format,
    "priority": _priority,
}


def build_tasks(n_per_type: int = N_PER_TYPE, seed: int = 42) -> list[TaskSpec]:
    rng = random.Random(seed)
    tasks = []
    for _ttype, gen in GENERATORS.items():
        tasks += [gen(rng, i) for i in range(n_per_type)]
    return tasks


def grade(task: TaskSpec, output: dict) -> bool:
    """字段级精确判分; 金额允许 ±0.01 容差。"""
    if not isinstance(output, dict):
        return False
    for k, v in task.expected.items():
        got = output.get(k)
        if isinstance(v, float):
            if got is None:
                return False
            try:
                if abs(float(got) - v) > 0.01:
                    return False
            except (TypeError, ValueError):
                return False
        elif got != v:
            return False
    return True


# ---------- 宽容判分(真实 LLM 后端用) ----------
# 真实 LLM 的输出形式多样(键名/嵌套结构/编号符号/日期格式), 语义级判分,
# 但仍以 expected 的值为准 —— 宽容的是"形式", 不是"对错"。


def _norm(s) -> str:
    return str(s).replace(" ", "").replace("　", "")


def _leaves(obj, out=None):
    """递归展平 JSON 的所有叶子值(真实 LLM 爱输出嵌套结构)。"""
    if out is None:
        out = []
    if isinstance(obj, dict):
        for v in obj.values():
            _leaves(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _leaves(v, out)
    else:
        out.append(obj)
    return out


def _date_key(s: str):
    """日期归一化: 7月3日 / 2026-07-03 / 07-03 → (月, 日)。"""
    import re

    m = (
        re.search(r"(\d{1,2})月(\d{1,2})日", s)
        or re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
        or re.search(r"^(\d{1,2})-(\d{1,2})$", s.strip())
    )
    if m:
        g = m.groups()
        return (int(g[-2]), int(g[-1]))
    return None


def _g_email(task, out) -> bool:
    vals = [str(v) for v in _leaves(out) if len(str(v)) <= 40]
    for exp in task.expected.values():
        hit = any(exp in v for v in vals)
        if not hit and _date_key(exp):  # 日期等价形式(模型爱规范化成 ISO)
            dk = _date_key(exp)
            hit = any(_date_key(v) == dk for v in vals)
        if not hit:
            return False
    return True


def _g_schedule(task, out) -> bool:
    found = {_norm(v) for v in _leaves(out) if len(str(v)) <= 20}
    return all(_norm(exp) in found for exp in task.expected.values())


def _g_expense(task, out) -> bool:
    want = task.expected["total_cny"]
    for v in _leaves(out):
        s = str(v).replace(",", "").replace("¥", "").replace("元", "")
        try:
            if abs(float(s) - want) <= 0.01:
                return True
        except ValueError:
            continue
    return False


def _g_doc_format(task, out) -> bool:
    import re

    limit = task.expected["max_len"]
    lines = []
    for v in out.values():
        if isinstance(v, list):
            lines += [str(x) for x in v]
        elif isinstance(v, str) and "\n" in v:
            lines += v.splitlines()
    numbered = [ln for ln in lines if re.match(r"^\s*\d+\s*[.、)）]", ln)]
    if len(numbered) != task.expected["n_items"]:
        return False
    return all(len(_norm(ln)) <= limit + 1 for ln in numbered)  # 编号点占1字符


_LEVEL_WORDS = ("CEO", "客户", "直属上级", "平级同事", "外包")


def _g_priority(task, out) -> bool:
    """接受两种等价答法: 级别名序列 或 人名序列(含'CEO小赵'混写, 逐 token 映射比对)。

    注意不能"全局剥离级别词"—— 正序和倒序会同时退化成同一个空串, 失去判别力。
    """
    import re

    rows = task.metadata["rows"]  # (级别名, 级别值, 时限)
    ordered = sorted(rows, key=lambda r: (-r[1], r[2]))
    want = [r[0] for r in ordered]
    level_by_person = {PEOPLE[j]: rows[j][0] for j in range(4)}
    level_names = {r[0] for r in rows}

    def to_levels(s: str) -> list[str] | None:
        """'>' 分隔的 token 序列 → 级别名序列; 有无法识别的 token → None。"""
        toks = [t for t in re.split(r">|＞|、", _norm(s)) if t]
        if len(toks) != len(rows):
            return None
        seq = []
        for t in toks:
            t2 = t
            for w in _LEVEL_WORDS:  # 混写形式 'CEO小赵' → '小赵'
                t2 = t2.replace(w, " ")
            t2 = t2.strip()
            if t2 in level_by_person:
                seq.append(level_by_person[t2])
            elif t in level_names:
                seq.append(t)
            else:
                return None
        return seq

    for v in _leaves(out):
        got = to_levels(str(v))
        if got is not None and got == want:
            return True
    return False


_TOLERANT = {
    "email_extract": _g_email,
    "schedule": _g_schedule,
    "expense": _g_expense,
    "doc_format": _g_doc_format,
    "priority": _g_priority,
}


def grade_tolerant(task: TaskSpec, output) -> bool:
    """语义级宽容判分: 形式宽容、对错严格。"""
    if not isinstance(output, dict):
        return False
    return _TOLERANT[task.ttype](task, output)
