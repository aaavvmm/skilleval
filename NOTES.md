# 项目2 · SkillAudit 注意事项（回顾用）

> 最后更新: 2026-10-12 · 状态: **完工 + 真实 LLM 试点已跑(110调用/$5.04)**
> 维护约定: 后续对项目的任何更改, 由 Claude 同步更新本文件

## 一句话

Agent Skill 消融评测框架——量化"给 agent 加某个 skill/MCP/规则到底值几个点"：A/B 对照 + 配对 bootstrap 95% CI + Δtoken/成本同表呈现 + 自动结论（含"建议移除"的负结果）。

> 📋 **真实 LLM 两轮实验的完整审计档案见 [FINDINGS.md](FINDINGS.md)**（三个评测自身 bug 的证据、修复、方法论结论——面试讲"如何对待差结果"的完整素材）

## 运行命令

```bash
.venv/Scripts/python demo/run_demo.py      # 50任务×6技能消融(确定性后端, 免费可复现)
.venv/Scripts/python -m pytest tests/ -q   # 8 个测试
.venv/Scripts/python demo/run_real.py      # 真实后端试点(claude -p, ~$5, 有断点续跑)
```

## 核心数字 A：确定性后端（框架自检, 简历主表）

| skill | 基线(适用) | 装备后(适用) | Δacc | 结论 |
|---|---|---|---|---|
| structured-extraction | 0% | **96%** | +96% | 有效增益 |
| conflict-check | 46% | **98%** | +52% | 有效增益 |
| fx-aware-sum | 58% | **98%** | +40% | 有效增益 |
| format-spec | 48% | **96%** | +48% | 有效增益 |
| priority-rules | 38% | **98%** | +60% | 有效增益 |
| verbose-audit-log | 38% | 36% | -2% | **无显著收益, 纯增成本→建议移除** |

## 核心数字 B：真实 LLM 试点（claude -p / GLM, 110 调用 × 2 轮, $5.12）★更有料

> 2026-10-12 二轮: 审计发现首轮三个**评测自身 bug**（priority 期望答案级别重复
> 导致 ground truth 歧义 / 判分只看顶层值漏掉嵌套 JSON 里的正确答案 / 邮件日期
> 被 ISO 化误判错）——修复重跑受影响的 40 次调用。**"评测自己的 bug 比模型的
> bug 多"正是评测工程师的日常, 审计过程本身是简历素材。**

| skill | 基线(适用) | 装备 | Δ | 解读 |
|---|---|---|---|---|
| structured-extraction | 10% | **100%** | **+90pp** | 大赢家, token 反降 1.28 万(基线啰嗦, skill 逼出紧凑 JSON) |
| priority-rules | 20% | 70% | +50pp | 首轮 0% 纯因评测 bug, 修复后显形 |
| conflict-check | 10% | 20% | +10pp | **真实难点**: LLM 难满足槽位硬约束(非评测 bug) |
| fx-aware-sum | **100%** | 90% | -10pp | **冗余**: 强模型自己会算汇率 |
| format-spec | **100%** | 100% | 0 | **冗余**: 基线已满分 |
| verbose-audit-log | 48% | **20%** | **-28pp** | **有害**: 长指令干扰模型 |
| baseline 总体 48% | | all-skills 80% | | |

**真正的卖点在 B 表**: 脚本后端说"5 个技能全有用", 真实模型说"2 个大赢、2 个冗余、1 个难救、1 个有害"——**skill 消融的价值恰恰是识别哪些 skill 在强模型上是负资产**。这是 evals 岗位最核心的洞察, 面试必讲。

## 架构速查

```
src/skilleval/
├── models.py    TaskSpec/SkillSpec/RunResult(含real_cost_usd); dataclass字段必须带类型注解
├── tasks.py     5类中文办公任务×10条(seed=42); grade(精确,脚本后端) + grade_tolerant(语义级,真实后端)
├── skills.py    6个SkillSpec(5实1装饰); 解法函数须先定义再引用
├── backends.py  ScriptedAgent(确定性) + ClaudeCodeBackend(claude -p, stdin传prompt, grade_tolerant)
├── runner.py    ablation(): 配对bootstrap CI → verdict
└── report.py    终端表 + HTML
demo/run_real.py  真实试点(3并发, 每10次写检查点 output/real_results.json, 断点续跑)
```

## 面试深挖点（README"设计取舍"+本次新增）

1. **不用 LLM judge**——字段级/语义级判分, judge 噪声会让 Δacc 归因失真
2. **成本必须进报告**——skill 代价与收益同表, 防止无脑堆 skill
3. **配对 bootstrap**——同任务配对差消除难度方差
4. **装饰性技能对照**——报告自带"看似有用实则无用"基线
5. **确定性后端先行, 真实后端出真相**——脚本说全有用, 真实模型说一半冗余: 两个都要跑, 差异本身就是发现
6. **强模型会让部分 skill 失业**——fx/format 类技能在 GLM 上基线已 100%; skill 的价值随模型能力漂移, 评测须持续重跑（这是 evals 岗和一次性测试的本质区别）

## 开发中踩过的坑（debug 故事素材, 本次新增两个 Windows 级的）

- **dataclass 字段漏类型注解**: `solver=None` 裸赋值不是字段
- **dict 迭代拿 key 当值**: 收进字符串 → 后端崩
- **任务期望值构造 bug**: schedule 期望解自相冲突
- **★ Windows .cmd 垫片吞多行 argv**: subprocess 传 `["claude.CMD", "-p", 多行prompt]` 经 cmd.exe 转发, prompt 在首个换行处被截断——模型只看到第一行指令(它还礼貌地回"请补充任务内容")。修复: prompt 走 stdin(`-p` 无位置参数时读标准输入), 顺带绕开 cmd 8k 限制
- **★ subprocess 找不到 claude**: bash 里能用是因为 shell 解析 .cmd 垫片; Python 须 `shutil.which("claude")` 取完整路径
- **★ 二轮审计三连**: ①priority 期望答案里"平级同事"出现两次(同级别不同时限被当不同发件人)→ground truth 歧义, 生成时须保证 4 级别互异 ②判分只看顶层 value, 模型嵌套 JSON 里的正确答案全被判错→须递归展平叶子 ③模型把"7月3日"规范化成"2026-07-03"被判错→日期要归一化等价。教训: **真实模型上跑出来的"差结果", 第一步是怀疑评测集而不是模型**
- **falsy-zero**: `now_ts or time.time()` 类写法吞掉合法的 0.0（项目1同款坑, 此处为提醒）
- **真实后端判分**: 精确匹配 grade() 会把 LLM 的合理变体全判错 → 必须分 grade / grade_tolerant 两级
- **测试容忍噪声**: 确定性引擎留了 2% 种子化失误, 测试断言"装备后必成功"会偶发翻车→ 断言应放行 random_error

## 已知边界（主动说）

- 真实试点 n=10/配置、单次重复、无 CI——是试点不是结论; 扩到 n≥30×3次才有统计强度
- 模型单一(GLM-5.3), skill 价值随模型漂移, 换模型须重测
- priority-rules 0%存疑: 可能是任务提示歧义而非纯模型问题, 值得人工复核 10 条输出

## 待办

- [x] git init + 首次提交 (main 846ee9d, 含 FINDINGS.md 与 output/real_results.json 存档)
- [ ] 录 demo 视频: 演示"建议移除"判读 + 真实后端 B 表
- [ ] （可选）真实后端扩样本(n=30, 3次) 出带 CI 的正式数字
- [ ] （可选）人工复核 priority-rules 的 10 条失败输出
