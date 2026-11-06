"""
一键演示: Skill 消融全流程
==========================
50 条中文办公任务 × {baseline, 每个skill单独, 全装备, 装饰性技能} × 5 次
→ 每个技能的 Δ成功率(95%CI) / Δtoken / Δ成本 + 结论
确定性后端(ScriptedAgent): 零 token 成本、可复现 —— 框架自检用;
真实数字接 ClaudeCodeBackend(见 README)。
"""

import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from skilleval.backends import ScriptedAgent
from skilleval.report import render_terminal, save
from skilleval.runner import ablation
from skilleval.skills import ALL_SKILLS
from skilleval.tasks import build_tasks

OUT = os.path.join(os.path.dirname(__file__), "..", "output")


def main():
    print("=" * 66)
    print("SkillAudit 一键演示 —— 50 条中文办公任务 × 6 技能消融(确定性后端)")
    print("=" * 66)
    tasks = build_tasks()
    print(f"任务集: {len(tasks)} 条 ({','.join(sorted({t.ttype for t in tasks}))})\n")
    res = ablation(tasks, ScriptedAgent(), ALL_SKILLS, repeats=5)
    render_terminal(res)
    p = save(res, OUT, meta="50 任务 × 5 次重复 × 8 配置, 确定性后端(ScriptedAgent)")
    print(f"\nHTML 报告: {os.path.abspath(p)}")


if __name__ == "__main__":
    main()
