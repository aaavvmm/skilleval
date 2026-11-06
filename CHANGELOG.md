# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与语义化版本。

## [0.2.0] - 2026-11-06

### Added
- CI 工作流: ruff lint/format + mypy + pytest(覆盖率门槛 70%) 矩阵 (Python 3.10/3.12)
- Dependabot (pip / github-actions 周更)
- Makefile 任务入口 (sync/lint/format/typecheck/test/ci)
- MIT LICENSE
- `ClaudeCodeBackend`: 指数退避重试(瞬态失败)、`max_spend_usd` 成本预算护栏(超限熔断)
- `demo/run_real.py`: 运行 manifest(git sha/模型/时间戳/成本), 评测可追溯可复现
- 结构化运行日志(stderr, JSON 行)

## [0.1.0] - 2026-10-12

### Added
- 50 条中文办公任务评测集(5 类, seed 固定), 字段级+语义级双判分
- 6 个 SkillSpec(5 实 1 装饰性对照), 确定性 ScriptedAgent + ClaudeCodeBackend 双后端
- 配对 bootstrap 95% CI 消融运行器, 终端/HTML 报告
- 确定性后端消融: 5 技能 +40~96pp 全显著, 装饰技能被识别"纯增成本→建议移除"
- 真实 LLM 两轮试点(claude -p/GLM, $5.12): 审计出 3 个评测自身 bug 并修复,
  修复后 structured-extraction +90pp, fx/format 冗余, verbose 有害(-28pp) — 见 FINDINGS.md
