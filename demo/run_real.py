"""
真实 LLM 后端消融试点(claude -p headless)
==========================================
规模控制(单次调用 ~2万输入token / ~20s, 必须省着跑):
  baseline      全部 50 任务 × 1 次
  +单技能       仅该技能适用的 10 任务 × 1 次   (×5)
  +verbose      10 任务(每类1条) × 1 次
  all-skills    10 任务(每类1条) × 1 次
  = 120 次调用, 3 并发 ≈ 15 分钟
判分用 grade_tolerant(形式宽容、对错严格)。每 10 次写检查点, 可断点续跑。
"""

import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from skilleval.backends import ClaudeCodeBackend
from skilleval.report import render_terminal, save
from skilleval.skills import ALL_SKILLS
from skilleval.tasks import build_tasks

OUT = os.path.join(os.path.dirname(__file__), "..", "output")
CKPT = os.path.join(OUT, "real_results.json")
WORKERS = 3


def load_ckpt():
    if os.path.exists(CKPT):
        with open(CKPT, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_ckpt(runs: dict):
    os.makedirs(OUT, exist_ok=True)
    with open(CKPT, "w", encoding="utf-8") as f:
        json.dump(runs, f, ensure_ascii=False)


def build_configs(tasks):
    """config名 → 任务列表。"""
    by_type = {}
    for t in tasks:
        by_type.setdefault(t.ttype, []).append(t)
    one_per_type = [v[0] for v in by_type.values()]
    cfg = {"baseline": tasks}
    for name, sk in ALL_SKILLS.items():
        cfg[f"+{name}"] = [t for t in tasks if sk.applies(t.ttype)] if sk.solver else one_per_type
    cfg["all-skills"] = one_per_type
    return cfg


def skills_for(config: str):
    if config == "baseline":
        return []
    if config == "all-skills":
        return [s for s in ALL_SKILLS.values() if s.solver]
    return [ALL_SKILLS[config[1:]]]  # "+skill-name"


def main():
    tasks = build_tasks()
    backend = ClaudeCodeBackend()
    configs = build_configs(tasks)
    runs = load_ckpt()
    todo = [(c, t) for c, ts in configs.items() for t in ts if t.task_id not in runs.get(c, {})]
    n_total = sum(len(ts) for ts in configs.values())
    n_done = sum(len(v) for v in runs.values())
    print(f"总规模 {n_total} 次调用 | 已有检查点 {n_done} | 待跑 {len(todo)}", flush=True)

    def work(item):
        c, t = item
        return c, backend.run(t, skills_for(c), c, 0)

    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(work, it) for it in todo]
        for fut in as_completed(futures):
            c, r = fut.result()
            runs.setdefault(c, {})[r.task_id] = {
                "success": r.success,
                "fail_mode": r.fail_mode,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "latency_ms": round(r.latency_ms),
                "cost_usd": round(r.real_cost_usd, 5),
                "detail": r.detail[:120],
            }
            done += 1
            if done % 10 == 0:
                save_ckpt(runs)
                spend = sum(x["cost_usd"] for v in runs.values() for x in v.values())
                print(f"[{done}/{len(todo)}] {time.time() - t0:.0f}s 已耗 ${spend:.2f}", flush=True)
    save_ckpt(runs)

    # ---- 聚合 ----
    def agg(config):
        rs = list(runs.get(config, {}).values())
        n = max(1, len(rs))
        return {
            "n": len(rs),
            "acc": sum(r["success"] for r in rs) / n,
            "tok": sum(r["prompt_tokens"] + r["completion_tokens"] for r in rs) / n,
            "cost_usd": sum(r["cost_usd"] for r in rs) / n,
            "fails": [r["fail_mode"] for r in rs if not r["success"]],
        }

    base = agg("baseline")
    skills_out = []
    for name in ALL_SKILLS:
        a = agg(f"+{name}")
        if not a["n"]:
            continue
        skills_out.append(
            {
                "name": name,
                "n_applicable": a["n"],
                "acc_base_on_applicable": base["acc"],
                "acc_skill_on_applicable": a["acc"],
                "acc_skill": a["acc"],
                "d_acc_applicable": 0,
                "ci95": (0, 0),
                "d_tokens_per_task": round(a["tok"] - base["tok"], 0),
                "d_cost_per_task_yuan": 0,
                "verdict": "见JSON明细",
            }
        )

    res = {
        "baseline": {
            "acc": base["acc"],
            "avg_total_tokens": base["tok"],
            "avg_cost_yuan": 0,
            "fail_modes": {},
        },
        "skills": skills_out,
        "configs_summary": {
            c: {
                "acc": agg(c)["acc"],
                "avg_total_tokens": agg(c)["tok"],
                "avg_cost_yuan": agg(c)["cost_usd"] * 7.2,
                "fail_modes": {},
            }
            for c in configs
        },
    }
    # 运行 manifest: 评测可追溯(代码版本/模型/时间/成本) —— 复现的第一步
    import subprocess as sp

    def git_sha():
        try:
            return sp.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
        except OSError:
            return "unknown"

    manifest = {
        "git_sha": git_sha(),
        "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
        "backend": "claude -p (GLM)",
        "workers": WORKERS,
        "n_calls": n_total,
        "total_cost_usd": round(spend, 2),
        "configs": {c: len(v) for c, v in runs.items()},
    }
    with open(os.path.join(OUT, "real_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    render_terminal(res)
    p = save(res, OUT, meta=f"真实后端 claude -p, {n_total}次调用, {WORKERS}并发")
    spend = sum(x["cost_usd"] for v in runs.values() for x in v.values())
    print(f"\n实际消耗: ${spend:.2f} | HTML 报告: {os.path.abspath(p)}")
    print("逐配置明细:", os.path.abspath(CKPT))


if __name__ == "__main__":
    main()
