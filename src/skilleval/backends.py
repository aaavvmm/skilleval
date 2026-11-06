# -*- coding: utf-8 -*-
"""
Agent 后端(可插拔)
==================
AgentBackend 协议: run(task, skills, config_name, repeat) -> RunResult

ScriptedAgent   确定性脚本 agent: 无 skill 时按"基线人格"用朴素解法
                (每类任务有已知系统性缺陷); 有 skill 时优先用 skill 解法。
                零成本、零延迟、可复现 —— 用于框架自检/演示/测试。
                另含少量种子化随机失误, 让 bootstrap 置信区间有意义。
ClaudeCodeBackend  真实后端: `claude -p` headless, skill 指令注入 system,
                   输出 JSON 判分。真实数字用这个跑(烧 token, demo 不调)。
"""
import json
import random
import subprocess

from .models import RunResult
from .tasks import grade, grade_tolerant

# ---------- 基线(无 skill)的朴素解法: 每类任务一个系统性缺陷 ----------

def _naive_extract(t):
    return {"summary": t.prompt[:40]}                      # 非结构化 → wrong_format


def _naive_schedule(t):
    md = t.metadata
    a = md["req"][0]
    if a in md["busy"]:                                    # 查了占用, 但改期时不避让 B
        a = md["free"][0]
    return {"A": a, "B": md["req"][1]}


def _naive_expense(t):
    md = t.metadata
    return {"total_cny": round(md["amt"] * md["rate"], 2)}  # 换算了但漏税 → missing_fx


def _naive_format(t):
    if t.task_id.endswith(("0", "2", "4", "6", "8")):      # 时好时坏
        return _skill_format_of(t)
    lines = t.metadata["items"]                             # 不编号 → over_limit
    return {"n_items": len(lines), "numbered": False,
            "max_len": t.expected["max_len"], "lines": lines}


def _skill_format_of(t):
    from .skills import _solve_format
    return _solve_format(t)


def _naive_priority(t):
    md = t.metadata
    rows = md["rows"]
    order = [rows[j][0] for j in sorted(range(4), key=lambda j: md["recv"][j])]
    return {"order": ">".join(order)}                       # 按收件序 → wrong_order


NAIVE_SOLVERS = {"email_extract": _naive_extract, "schedule": _naive_schedule,
                 "expense": _naive_expense, "doc_format": _naive_format,
                 "priority": _naive_priority}

NAIVE_FAIL = {"email_extract": "wrong_format", "schedule": "conflict",
              "expense": "missing_fx", "doc_format": "over_limit",
              "priority": "wrong_order"}


class ScriptedAgent:
    """确定性脚本 agent。基线失误率 8%, 装备 skill 后 2%(种子化, 可复现)。"""

    def __init__(self, base_error: float = 0.08, skilled_error: float = 0.02):
        self.base_error = base_error
        self.skilled_error = skilled_error

    def run(self, task, skills, config_name: str, repeat: int = 0) -> RunResult:
        applicable = [s for s in skills if s.applies(task.ttype)]
        solver = next((s.solver for s in applicable if s.solver), None)
        rng = random.Random(hash((config_name, task.task_id, repeat)) & 0xFFFFFFFF)

        if solver:
            output = solver(task)
            fail_mode = "" if grade(task, output) else "wrong_answer"
            err_p = self.skilled_error
            completion = 220
        else:
            output = NAIVE_SOLVERS[task.ttype](task)
            fail_mode = "" if grade(task, output) else NAIVE_FAIL[task.ttype]
            err_p = self.base_error
            completion = 160
        if rng.random() < err_p:                             # 种子化偶发失误
            output, fail_mode = {}, "random_error"

        prompt_tokens = 300 + len(task.prompt) // 2 \
            + sum(len(s.instruction) for s in skills) // 2
        return RunResult(task_id=task.task_id, config=config_name,
                         success=(fail_mode == ""), fail_mode=fail_mode,
                         prompt_tokens=prompt_tokens,
                         completion_tokens=0 if fail_mode == "random_error" else completion,
                         latency_ms=600 + prompt_tokens / 20 + rng.random() * 200)


class ClaudeCodeBackend:
    """真实后端: claude -p headless。skill 指令拼接进提示, 输出 JSON 判分。
    真实评测用; demo 不调用(烧 token)。"""

    def __init__(self, model: str | None = None, timeout: int = 180):
        import shutil
        self.claude = shutil.which("claude")
        if not self.claude:
            raise RuntimeError("找不到 claude 可执行文件(npm 垫片需在 PATH 中)")
        self.model = model
        self.timeout = timeout

    def run(self, task, skills, config_name: str, repeat: int = 0) -> RunResult:
        sys_ins = "\n".join(f"- {s.instruction}" for s in skills)
        prompt = (f"{'技能规范:' + chr(10) + sys_ins + chr(10) if sys_ins else ''}"
                  f"处理以下任务, 只输出一个 JSON 对象, 不要其他文字。\n{task.prompt}")
        # prompt 必须走 stdin: Windows 上 claude 是 .cmd 垫片, 经 cmd.exe 转发,
        # 多行 argv 会在首个换行处被截断(模型只看到第一行), 且有 8k 长度上限
        cmd = [self.claude, "-p", "--output-format", "json"]
        if self.model:
            cmd += ["--model", self.model]
        r = RunResult(task_id=task.task_id, config=config_name)
        import time
        t0 = time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  input=prompt, timeout=self.timeout,
                                  encoding="utf-8")
            data = json.loads(proc.stdout)
            r.detail = data.get("result", "")[:200]
            usage = data.get("usage") or {}
            r.prompt_tokens = usage.get("input_tokens", 0)
            r.completion_tokens = usage.get("output_tokens", 0)
            r.real_cost_usd = data.get("total_cost_usd", 0.0)
            try:
                body = r.detail[r.detail.index("{"): r.detail.rindex("}") + 1]
                output = json.loads(body)
            except (ValueError, json.JSONDecodeError):
                output = None
            # 真实 LLM 用宽容判分(形式宽容、对错严格); 脚本后端保持精确判分
            r.success = grade_tolerant(task, output) if output else False
            r.fail_mode = "" if r.success else "wrong_answer"
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            r.success, r.fail_mode, r.detail = False, "backend_error", str(e)[:120]
        r.latency_ms = (time.time() - t0) * 1000
        return r
