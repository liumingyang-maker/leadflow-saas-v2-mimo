# LeadFlow SaaS V2 — Agent Allocation V3

## 1. Background

LeadFlow SaaS V2 is a Flask modular monolith SaaS for B2B lead management. The original governance used two-party collaboration: Codex (Controller/Architect/Reviewer) + Reasonix/DeepSeek (Worker).

As of v1.0.0-rc1, all 6 milestones (V2-01 through V2-06) are merged with 64 commits. The project now transitions to three-party governance for the rc1 → v1.0.0 finalization phase.

## 2. Three-Party Role Mapping

| Role | Agent | Original Role | Core Responsibilities |
|------|-------|---------------|----------------------|
| Controller / Architect / Release Manager | Qingyan (GLM) | Codex (control/architect/release) | Task splitting, architecture contracts, release management, Go/No-Go |
| Implementation Worker | Xiaomi MiMo | Reasonix / DeepSeek | Feature code, CRUD, tests, migrations, rework |
| Reviewer | DeepSeek | Codex (review, split独立) | Architecture/Security/UI/Release review |

## 3. Mandatory 15-Step Flow (Responsibility Matrix)

| # | Step | Owner | Description |
|---|------|-------|-------------|
| 1 | DISCOVER | Qingyan | Confirm task scope and dependencies |
| 2 | ARCHITECT_PLAN | Qingyan | Architecture plan, interface/data contracts |
| 3 | TASK_PACKET | Qingyan | Generate task packet (task_packet.md) |
| 4 | IMPLEMENT | MiMo | Feature code, tests, migrations |
| 5 | LOCAL_GATES | MiMo + Qingyan | MiMo self-check + Qingyan verification, evidence JSON |
| 6 | CODE_REVIEW | DeepSeek | Architecture review verdict |
| 7 | SECURITY_REVIEW | DeepSeek | Security review verdict |
| 8 | UI_REVIEW | DeepSeek (if UI) | UI review with screenshots |
| 9 | WORKER_FIX | MiMo (per rework packet) | Fix defects |
| 10 | COMMIT | Qingyan | Structured commit |
| 11 | PR | Qingyan | Create Pull Request |
| 12 | CI | Qingyan | Monitor CI pipeline to green |
| 13 | MERGE | Qingyan | Merge branch to main |
| 14 | SYNC_MAIN | Qingyan | Local sync of main branch |
| 15 | NEXT_TASK | Qingyan | Schedule next task |

## 4. Rework Discipline

1. DeepSeek FAIL → generate focused rework packet for MiMo
2. MiMo fails 2 consecutive rounds → Qingyan may do <30 line integration fix
3. Max 4 rework rounds (autopilot.json worker.max_fix_rounds), escalate to user beyond that

## 5. Evidence Directory

All evidence stored in `.autopilot/evidence/`:
- Gate run results (JSON)
- Security review verdicts
- UI review verdicts with screenshots
- Migration test results
- Staging deployment evidence

## 6. State Machine

Maintained by Qingyan via `tools/autopilot.py`, persisted in `.autopilot/state.json`:

```
READY → PLANNING → WORKER_BUILD → VERIFYING → REVIEWING → WORKER_FIX (loop max 4) → ACCEPTED → PR_OPEN → CI → MERGED → DONE
```

## 7. Communication Rules

- Blocking issues reported immediately, all at once, max 5 with recommendations
- No silent retries
- One task card = one branch = one PR
- No `git add .`, force push, old repo modification, production deploy, plaintext secrets
