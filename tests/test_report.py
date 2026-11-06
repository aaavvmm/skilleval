"""报告与模型层测试(补覆盖率): HTML 渲染 / 终端表 / 成本折算 / 预算异常。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from skilleval.models import BudgetExceededError, RunResult, cost_of
from skilleval.report import render_html, render_terminal
from skilleval.tasks import build_tasks, grade


def _fake_res():
    return {
        "baseline": {
            "acc": 0.44,
            "avg_total_tokens": 100.0,
            "avg_cost_yuan": 0.001,
            "fail_modes": {"conflict": 2},
        },
        "skills": [
            {
                "name": "structured-extraction",
                "n_applicable": 10,
                "acc_base_on_applicable": 0.1,
                "acc_skill_on_applicable": 1.0,
                "acc_skill": 0.5,
                "d_acc_applicable": 0.9,
                "ci95": (0.8, 1.0),
                "d_tokens_per_task": -100,
                "d_cost_per_task_yuan": -0.001,
                "verdict": "有效增益",
            },
            {
                "name": "verbose-audit-log",
                "n_applicable": 50,
                "acc_base_on_applicable": 0.44,
                "acc_skill_on_applicable": 0.2,
                "acc_skill": 0.2,
                "d_acc_applicable": -0.24,
                "ci95": (-0.4, 0.0),
                "d_tokens_per_task": 500,
                "d_cost_per_task_yuan": 0.002,
                "verdict": "无显著收益, 纯增成本 → 建议移除",
            },
        ],
        "configs_summary": {
            "baseline": {
                "acc": 0.44,
                "avg_total_tokens": 100.0,
                "avg_cost_yuan": 0.001,
                "fail_modes": {},
            }
        },
    }


def test_render_html_contains_verdicts():
    html = render_html(_fake_res(), meta="测试")
    assert "有效增益" in html and "建议移除" in html
    assert "+90%" in html and "structured-extraction" in html


def test_render_terminal_smoke(capsys):
    render_terminal(_fake_res())
    out = capsys.readouterr().out
    assert "baseline 总体" in out


def test_cost_of():
    r = RunResult(prompt_tokens=1_000_000, completion_tokens=0)
    assert abs(cost_of(r) - 3.0) < 1e-9
    r2 = RunResult(prompt_tokens=0, completion_tokens=1_000_000)
    assert abs(cost_of(r2) - 15.0) < 1e-9


def test_budget_error_is_runtime_error():
    assert issubclass(BudgetExceededError, RuntimeError)
    with pytest.raises(BudgetExceededError):
        raise BudgetExceededError("熔断")


def test_grade_tolerant_semantics():
    """宽容判分回归: 嵌套 JSON / 日期归一化 / 人名-级别双答法 (三 bug 的回归测试)。"""
    from skilleval.tasks import build_tasks, grade_tolerant

    tasks = {t.task_id: t for t in build_tasks()}
    # 嵌套输出里的正确答案(schedule)
    sc = tasks["sc01"]
    assert grade_tolerant(sc, {"A会议": {"最终时段": sc.expected["A"]}, "B": sc.expected["B"]})
    # 日期等价形式(email)
    ee = tasks["ee00"]
    assert grade_tolerant(
        ee, {"date": "2026-03-12", "amount": 12800, "contact": ee.expected["contact"]}
    )
    # priority: 级别名序与人名序等价
    pr = tasks["pr00"]
    seq = pr.expected["order"].split(">")
    assert grade_tolerant(pr, {"排序结果": ">".join(seq)})
    assert not grade_tolerant(pr, {"排序结果": ">".join(reversed(seq))})


def test_skill_solvers_match_expected():
    """确定性解法与期望答案同源(排序键一致的回归)。"""
    from skilleval.skills import _solve_format, _solve_priority, _solve_structured

    tasks = {t.task_id: t for t in build_tasks()}
    for t in tasks.values():
        if t.ttype == "priority":
            assert grade(t, _solve_priority(t)), t.task_id
        if t.ttype == "email_extract":
            assert grade(t, _solve_structured(t)), t.task_id
        if t.ttype == "doc_format":
            assert grade(t, _solve_format(t)), t.task_id
