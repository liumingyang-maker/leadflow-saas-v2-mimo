---
name: leadflow-release-gate
description: Use before committing, opening a PR, merging a PR, completing a milestone, or declaring LeadFlow V2 work finished.
---

# LeadFlow Release Gate

发布被阻塞，除非：diff 范围正确、门禁通过、审查 PASS、租户与安全通过、迁移通过、UI 有证据、CI 绿色、没有生产部署。

证据保存到 `.autopilot/evidence/`。
