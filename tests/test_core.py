"""核心测试: 任务判分 / 基线缺陷 / skill 解法 / 消融统计 / 装饰性技能识别。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from skilleval.backends import ScriptedAgent
from skilleval.runner import ablation
from skilleval.skills import ALL_SKILLS, _solve_expense, _solve_schedule
from skilleval.tasks import build_tasks, grade

# ---------- 任务与判分 ----------


def test_build_tasks_count_and_types():
    tasks = build_tasks()
    assert len(tasks) == 50
    assert {t.ttype for t in tasks} == {
        "email_extract",
        "schedule",
        "expense",
        "doc_format",
        "priority",
    }


def test_tasks_deterministic():
    a = build_tasks(seed=42)
    b = build_tasks(seed=42)
    assert [t.prompt for t in a] == [t.prompt for t in b]


def test_grade_tolerance():
    t = build_tasks(n_per_type=1)[2]  # expense
    assert grade(t, {"total_cny": t.expected["total_cny"]})
    assert grade(t, {"total_cny": t.expected["total_cny"] + 0.005})
    assert not grade(t, {"total_cny": t.expected["total_cny"] + 1})


# ---------- 基线缺陷与 skill 解法 ----------


def test_naive_fails_skill_solves():
    tasks = build_tasks()
    backend = ScriptedAgent()
    by_type = {}
    for t in tasks:
        r = backend.run(t, [], "baseline", 0)
        by_type.setdefault(t.ttype, []).append(r.success)
    # 基线在每类上都有系统性失败(远低于 100%)
    for ttype, oks in by_type.items():  # noqa: B007 — ttype 用于失败信息
        assert sum(oks) < len(oks), f"{ttype} 基线居然全对"
    # 装上对应 skill 后该类应接近全对(2% 种子化随机失误属正常噪声)
    for t in tasks:
        sk = next(s for s in ALL_SKILLS.values() if s.applies(t.ttype) and s.solver)
        r = backend.run(t, [sk], f"+{sk.name}", 0)
        assert r.success or r.fail_mode == "random_error", (
            f"{t.task_id} 装备 {sk.name} 仍失败: {r.fail_mode}"
        )


def test_solve_schedule_conflict():
    tasks = [t for t in build_tasks() if t.ttype == "schedule"]
    for t in tasks:
        out = _solve_schedule(t)
        assert out["A"] not in t.metadata["busy"] or out["A"] == t.metadata["req"][0]


def test_solve_expense_tax():
    tasks = [t for t in build_tasks() if t.ttype == "expense"]
    for t in tasks:
        assert _solve_expense(t)["total_cny"] == t.expected["total_cny"]


# ---------- 消融统计 ----------


def test_ablation_structure_and_gains():
    res = ablation(build_tasks(), ScriptedAgent(), ALL_SKILLS, repeats=3)
    assert res["baseline"]["acc"] < 1.0
    names = {s["name"] for s in res["skills"]}
    assert "structured-extraction" in names and "verbose-audit-log" in names
    for s in res["skills"]:
        lo, hi = s["ci95"]
        assert lo <= hi
        assert lo <= s["d_acc_applicable"] <= hi
    # 有解法的 skill 应显著为正
    real = [s for s in res["skills"] if s["name"] != "verbose-audit-log"]
    assert all(s["d_acc_applicable"] > 0.3 for s in real)
    # 装饰性技能: 无显著收益 + 纯增成本
    deco = next(s for s in res["skills"] if s["name"] == "verbose-audit-log")
    assert "无显著收益" in deco["verdict"]
    assert deco["d_tokens_per_task"] > 0


def test_verbose_skill_costs_tokens():
    tasks = build_tasks()[:5]
    b = ScriptedAgent()
    r0 = b.run(tasks[0], [], "baseline", 0)
    r1 = b.run(tasks[0], [ALL_SKILLS["verbose-audit-log"]], "verbose", 0)
    assert r1.prompt_tokens > r0.prompt_tokens + 50
