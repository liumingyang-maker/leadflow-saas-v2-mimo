---
name: leadflow-controller
description: Use for planning, delegating, reviewing and releasing any LeadFlow V2 engineering task through Codex as controller and Reasonix/DeepSeek as implementation worker.
---

# LeadFlow Controller

遵守 `AGENTS.md` 和 `docs/AUTOMATION_WORKFLOW.md`。

每个任务：生成契约型任务包、交给 Reasonix/DeepSeek、运行证据门禁、审查架构/安全/UI、把精确修复交回 Worker、仅在 PASS 后负责 Git/PR/CI/合并。

使用 `python tools/autopilot.py` 记录状态与证据。
