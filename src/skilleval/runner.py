"""
消融运行器
==========
ablation(tasks, backend, repeats):
  configs = baseline(无skill) + 每个skill单独装备 + 全装备
  每配置 × 每任务 × repeats 次运行 → 指标 + 配对 bootstrap 95% CI

输出结构(每 skill):
  {name, n_applicable, acc_base, acc_skill, d_acc, ci95, d_tokens_per_task,
   d_cost_per_task, verdict}
verdict ∈ 有效增益 / 无显著收益(纯增成本, 建议移除) / 显著负收益 / 复杂结论
"""

import random

from .models import cost_of


def _run_config(tasks, backend, skills, config_name, repeats):
    results = []
    for task in tasks:
        for rep in range(repeats):
            results.append(backend.run(task, skills, config_name, rep))
    return results


def _acc_ci(base_results, skill_results, n_boot: int = 1000, seed: int = 7):
    """配对 bootstrap: 同一任务维度重采样, 求 Δ成功率 95% CI。"""
    by_task_b: dict[str, list[bool]] = {}
    by_task_s: dict[str, list[bool]] = {}
    for r in base_results:
        by_task_b.setdefault(r.task_id, []).append(r.success)
    for r in skill_results:
        by_task_s.setdefault(r.task_id, []).append(r.success)
    task_ids = sorted(by_task_b)
    diffs = []
    for tid in task_ids:
        pb = sum(by_task_b[tid]) / len(by_task_b[tid])
        ps = sum(by_task_s[tid]) / len(by_task_s[tid])
        diffs.append(ps - pb)
    point = sum(diffs) / len(diffs)
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        sample = [diffs[rng.randrange(len(diffs))] for _ in range(len(diffs))]
        boots.append(sum(sample) / len(sample))
    boots.sort()
    lo, hi = boots[int(n_boot * 0.025)], boots[int(n_boot * 0.975) - 1]
    return point, lo, hi


def ablation(
    tasks, backend, skills_by_name, repeats: int = 5, price_in: float = 3.0, price_out: float = 15.0
) -> dict:
    """主入口: baseline + 单技能 + 全装备 的完整消融。"""
    all_names = [s for s in skills_by_name if skills_by_name[s].solver]
    deco = [skills_by_name[s] for s in skills_by_name if not skills_by_name[s].solver]

    configs: dict[str, list] = {"baseline": []}
    for name in all_names:
        configs[f"+{name}"] = [skills_by_name[name]]
    configs["all-skills"] = [skills_by_name[n] for n in all_names]
    if deco:
        configs["baseline+verbose"] = deco  # 装饰性技能对照

    runs = {c: _run_config(tasks, backend, cfg, c, repeats) for c, cfg in configs.items()}

    base = runs["baseline"]
    skills_out: list[dict] = []
    out = {"baseline": _summary(base, price_in, price_out), "skills": skills_out}
    for name in all_names + (["verbose-audit-log"] if deco else []):
        cname = f"+{name}"
        if cname not in runs:
            cname = "baseline+verbose"
            skill = skills_by_name[name]
        else:
            skill = skills_by_name[name]
        r_sk = runs[cname]
        app_ids = {t.task_id for t in tasks if skill.applies(t.ttype)}
        b_app = [r for r in base if r.task_id in app_ids]
        sk_app = [r for r in r_sk if r.task_id in app_ids]
        if not app_ids:
            continue
        # 只在适用任务上算配对差
        point, lo, hi = _acc_ci(b_app, sk_app)
        tok_base = sum(x.prompt_tokens + x.completion_tokens for x in b_app) / len(b_app)
        tok_sk = sum(x.prompt_tokens + x.completion_tokens for x in r_sk) / len(r_sk)
        d_cost = sum(cost_of(x, price_in, price_out) for x in r_sk) / len(r_sk) - sum(
            cost_of(x, price_in, price_out) for x in b_app
        ) / len(b_app)
        sig = not (lo <= 0 <= hi)
        if sig and point > 0:
            verdict = "有效增益"
        elif sig and point < 0:
            verdict = "显著负收益"
        else:
            verdict = "无显著收益" + (", 纯增成本 → 建议移除" if tok_sk > tok_base else "")
        skills_out.append(
            {
                "name": name,
                "n_applicable": len(app_ids),
                "acc_base_on_applicable": round(sum(x.success for x in b_app) / len(b_app), 3),
                "acc_skill_on_applicable": round(sum(x.success for x in sk_app) / len(sk_app), 3),
                "acc_skill": round(sum(x.success for x in r_sk) / len(r_sk), 3),
                "d_acc_applicable": round(point, 3),
                "ci95": (round(lo, 3), round(hi, 3)),
                "d_tokens_per_task": round(tok_sk - tok_base, 1),
                "d_cost_per_task_yuan": round(d_cost, 5),
                "verdict": verdict,
            }
        )
    out["configs_summary"] = {c: _summary(rs, price_in, price_out) for c, rs in runs.items()}
    return out


def _summary(results, price_in, price_out) -> dict:
    n = len(results)
    return {
        "acc": round(sum(r.success for r in results) / n, 3),
        "avg_prompt_tokens": round(sum(r.prompt_tokens for r in results) / n, 1),
        "avg_total_tokens": round(
            sum(r.prompt_tokens + r.completion_tokens for r in results) / n, 1
        ),
        "avg_cost_yuan": round(sum(cost_of(r, price_in, price_out) for r in results) / n, 5),
        "fail_modes": _fail_modes(results),
    }


def _fail_modes(results) -> dict:
    from collections import Counter

    c = Counter(r.fail_mode for r in results if not r.success)
    return dict(c)
