"""
数据模型
========
TaskSpec  任务: 输入文本 + 期望输出(字段级精确判分, 不用 LLM judge —— 归因干净)
SkillSpec 技能: 名称 + 注入给 agent 的指令文本 + 适用任务类型 + (确定性后端的)解法
RunResult 单次运行: 成功/失败 + token 用量 + 延迟 + 失败模式

设计核心: 消融的对象是"agent 的外部装备"(skill), 评测框架只关心
(装备配置, 任务) → (结果, 成本) 的映射, 与具体 agent 实现解耦。
"""

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class TaskSpec:
    task_id: str
    ttype: str  # email_extract / schedule / expense / doc_format / priority
    prompt: str  # 呈现给 agent 的任务文本
    expected: dict  # 期望输出(字段→值), 判分 = 全字段精确匹配
    metadata: dict = field(default_factory=dict)


@dataclass
class SkillSpec:
    name: str
    instruction: str  # 注入 system 的技能说明(真实后端=提示词, 确定性后端=策略键)
    applies_to: tuple  # 适用任务类型
    solver: object = None  # 确定性后端: callable(task)->dict; None 表示"装饰性技能"

    def applies(self, ttype: str) -> bool:
        return ttype in self.applies_to


@dataclass
class RunResult:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    task_id: str = ""
    config: str = ""  # 装备配置名(如 "baseline", "+conflict-check")
    success: bool = False
    fail_mode: str = (
        ""  # wrong_format / conflict / missing_fx / over_limit / wrong_order / random_error
    )
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    detail: str = ""
    real_cost_usd: float = 0.0  # 真实后端: API 返回的实际成本


def cost_of(result: RunResult, price_in: float = 3.0, price_out: float = 15.0) -> float:
    """按百万token单价(元)折算成本。默认参考价: ¥3/Min ¥15/Mout。"""
    return (result.prompt_tokens * price_in + result.completion_tokens * price_out) / 1e6


class BudgetExceededError(RuntimeError):
    """真实后端累计花费超过预算护栏 —— 评测熔断, 防止失控烧钱。"""


def now_ms() -> float:
    return time.time() * 1000
