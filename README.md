# SkillAudit — Agent Skill 消融评测框架

量化"给 Agent 加某个 skill/MCP/规则到底值几个点"：同一 agent 在
(无装备 / 单技能 / 全装备) 下的 A/B 对照，输出每个技能的
**Δ成功率(bootstrap 95% CI) / Δtoken / Δ成本 / 结论**。

与项目 1 的消融（记忆系统内部组件）互补——本项目消融的是 **agent 的外部装备**。
判分全部为字段级精确匹配，**无 LLM judge**，归因干净。

## 演示结果（50 条中文办公任务 × 6 技能 × 5 次重复）

| skill | 基线 | 装备后 | Δacc(适用任务) | 95% CI | Δtoken/任务 | 结论 |
|---|---|---|---|---|---|---|
| structured-extraction | 0% | — | **+96%** | (+0.90,+1.00) | +73 | 有效增益 |
| conflict-check | 48% | — | **+52%** | (+0.22,+0.80) | +1 | 有效增益 |
| fx-aware-sum | 54% | — | **+46%** | (+0.18,+0.74) | +62 | 有效增益 |
| format-spec | 42% | — | **+56%** | (+0.30,+0.82) | +62 | 有效增益 |
| priority-rules | 40% | — | **+60%** | (+0.30,+0.90) | +3 | 有效增益 |
| verbose-audit-log | 37% | — | +2% | (0.00,+0.05) | +65 | **无显著收益, 纯增成本 → 建议移除** |

verbose-audit-log 是刻意设计的"装饰性技能"（长指令、无实效）——框架准确
识别了它。**负结果也是评测产出**：知道哪个 skill 该删，和知道哪个该加同样值钱。

复现：`python demo/run_demo.py`

## 架构

```
tasks.py    任务集: 5 类中文办公任务 × 10 条(seed固定), 字段级判分
            每类任务对应基线 agent 的一种已知系统性缺陷
skills.py   SkillSpec: 指令文本(注入system) + 适用类型 + 解法
backends.py AgentBackend 协议:
            ├─ ScriptedAgent     确定性脚本 agent(零成本自检, 种子化随机失误)
            └─ ClaudeCodeBackend claude -p headless(真实数字用, skill 注入提示词)
runner.py   消融运行器: 配对 bootstrap 95% CI + 结论判定
report.py   终端表 + 单文件 HTML 报告
```

## 用真实 agent 跑（烧 token）

```bash
python demo/run_real.py        # claude -p headless, ~$5/轮, 断点续跑
```

真实 LLM 试点结果（GLM-5.3, 110 调用 × 2 轮, 判分 grade_tolerant；首轮审计出
3 个评测自身 bug——期望答案歧义/嵌套输出漏判/日期格式误判——修复后重跑）：

| skill | 基线 | 装备 | Δ | 解读 |
|---|---|---|---|---|
| structured-extraction | 10% | **100%** | **+90pp** | 最大赢家, token 反降 1.28 万 |
| priority-rules | 20% | 70% | +50pp | 首轮 0% 纯因评测 bug |
| conflict-check | 10% | 20% | +10pp | 槽位硬约束是 LLM 真实难点 |
| fx-aware-sum | **100%** | 90% | -10pp | **冗余**——强模型自己会算 |
| format-spec | **100%** | 100% | 0 | **冗余** |
| verbose-audit-log | 48% | **20%** | **-28pp** | **有害**——长指令干扰模型 |

**确定性后端说"5 个技能全有用"，真实模型说"2 个大赢、2 个冗余、1 个难救、1 个有害"**
——skill 的价值随模型能力漂移，评测不是一次性验收而是持续过程。
这是本框架最重要的发现。

## 设计取舍

1. **不用 LLM judge**：字段级精确判分，评分离合格与内容质量解耦——
   judge 本身的噪声会让 Δacc 归因失真
2. **成本必须进报告**：skill 的代价（更长 prompt）与收益同表呈现，
   只报成功率的评测会诱导无脑堆 skill
3. **配对 bootstrap 而非独立 t 检验**：同一任务在同配置下重复采样，
   配对差消除任务难度方差；50 样本下比正态假设稳健
4. **装饰性技能对照**：报告里必须有一条"看起来有用其实没用"的基线，
   防止评测者被"加了东西、分数没跌"迷惑
5. **确定性后端先行**：框架逻辑用零成本确定性 agent 验证，真实后端只跑最终数字
   —— 与项目 1 的规则抽取隔离、项目 3 的合成信号自闭环同一设计哲学

## 技术栈

Python 3.10+ · 零外部依赖 · subprocess(Claude Code headless) · bootstrap 统计
