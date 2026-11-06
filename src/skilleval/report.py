# -*- coding: utf-8 -*-
"""消融报告: 终端表格 + 单文件 HTML(复用项目3的报告视觉风格)。"""
import datetime
import os

_CSS = """
body{font-family:"Microsoft YaHei",-apple-system,sans-serif;max-width:960px;margin:24px auto;
     padding:0 20px;color:#2c3e50;line-height:1.6}
h1{font-size:22px;border-bottom:2px solid #8e44ad;padding-bottom:8px}
table{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0}
th,td{border:1px solid #d5dbdb;padding:6px 10px;text-align:left}
th{background:#f4f6f7}
.good{color:#1e8449;font-weight:600}.bad{color:#c0392b;font-weight:600}
.meh{color:#7f8c8d}
.note{background:#fef9e7;border-left:4px solid #f39c12;padding:8px 14px;margin:10px 0;font-size:13px}
.meta{color:#7f8c8d;font-size:12px}
"""


def render_terminal(res: dict):
    print(f"{'skill':<24}{'适用':>4}{'基线':>7}{'装备·适用':>9}{'总体':>7}{'Δacc':>8}"
          f"{'95%CI':>16}{'Δtok/任务':>10}  结论")
    for s in res["skills"]:
        ci = f"({s['ci95'][0]:+.2f},{s['ci95'][1]:+.2f})"
        print(f"{s['name']:<24}{s['n_applicable']:>4}{s['acc_base_on_applicable']:>7.0%}"
              f"{s['acc_skill_on_applicable']:>9.0%}{s['acc_skill']:>7.0%}"
              f"{s['d_acc_applicable']:>+8.0%}{ci:>16}"
              f"{s['d_tokens_per_task']:>+10.0f}  {s['verdict']}")
    print(f"\nbaseline 总体: {res['baseline']['acc']:.0%}, "
          f"均token {res['baseline']['avg_total_tokens']:.0f}, "
          f"均成本 ¥{res['baseline']['avg_cost_yuan']:.5f}/任务")


def render_html(res: dict, meta: str = "") -> str:
    rows = []
    for s in res["skills"]:
        cls = "good" if "有效" in s["verdict"] else ("bad" if "负" in s["verdict"] else "meh")
        rows.append(
            f"<tr><td>{s['name']}</td><td>{s['n_applicable']}</td>"
            f"<td>{s['acc_base_on_applicable']:.0%}</td>"
            f"<td>{s['acc_skill_on_applicable']:.0%}</td>"
            f"<td>{s['acc_skill']:.0%}</td>"
            f"<td class='{cls}'>{s['d_acc_applicable']:+.0%}</td>"
            f"<td>({s['ci95'][0]:+.2f}, {s['ci95'][1]:+.2f})</td>"
            f"<td>{s['d_tokens_per_task']:+.0f}</td>"
            f"<td>¥{s['d_cost_per_task_yuan']:.5f}</td>"
            f"<td class='{cls}'>{s['verdict']}</td></tr>")
    cfg_rows = "".join(
        f"<tr><td>{c}</td><td>{v['acc']:.0%}</td><td>{v['avg_total_tokens']:.0f}</td>"
        f"<td>¥{v['avg_cost_yuan']:.5f}</td><td>{v['fail_modes']}</td></tr>"
        for c, v in res["configs_summary"].items())
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>Skill 消融报告</title><style>{_CSS}</style></head><body>
<h1>Agent Skill 消融报告</h1>
<p class="meta">生成时间 {now} | {meta}</p>
<h2>逐技能贡献(适用任务上的配对差, bootstrap 95% CI)</h2>
<table><tr><th>skill</th><th>适用任务数</th><th>基线(适用)</th><th>装备后(适用)</th><th>装备后(总体)</th><th>Δacc</th>
<th>95% CI</th><th>Δtoken/任务</th><th>Δ成本/任务</th><th>结论</th></tr>
{''.join(rows)}</table>
<h2>配置总览</h2>
<table><tr><th>配置</th><th>成功率</th><th>均token</th><th>均成本/任务</th><th>失败模式</th></tr>
{cfg_rows}</table>
<div class="note">📌 判读: CI 不含 0 → 显著; "无显著收益且纯增成本"的 skill 建议移除 ——
负结果也是评测产出。判分全部为字段级精确匹配, 无 LLM judge, 归因干净。</div>
<p class="meta">SkillAudit · 消融对象是 agent 的外部装备</p>
</body></html>"""


def save(res: dict, out_dir: str, meta: str = "") -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"ablation_{datetime.datetime.now():%Y%m%d_%H%M%S}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html(res, meta))
    return path
