# Role Matrix V3 — LeadFlow SaaS V2

## Work Category → Responsibility Matrix

| Work Category | Qingyan (GLM) | Xiaomi MiMo | DeepSeek |
|--------------|---------------|-------------|----------|
| Product scope & decisions | **OWNER** | — | — |
| Architecture & contracts | **OWNER** | — | Review |
| Task splitting & packets | **OWNER** | — | — |
| Feature code | Delegator | **OWNER** | — |
| CRUD / Repository / Service | Delegator | **OWNER** | — |
| Templates & CSS | Delegator (spec) | **OWNER** | — |
| Database migrations | Delegator | **OWNER** | — |
| Tests (as specified) | Delegator | **OWNER** | — |
| Local gates & evidence | Verifier | Self-check | — |
| Architecture review | — | — | **OWNER** |
| Security review | — | — | **OWNER** |
| UI/UX review | — | — | **OWNER** |
| Release review | — | — | **OWNER** |
| Git / PR / CI / Merge | **OWNER** | — | — |
| Release decisions | **OWNER** | — | Advisor |
| Rework (per packet) | Delegator | **OWNER** | — |
| Integration fixes (<30 lines) | **OWNER** (fallback) | — | — |
| Docker / DevOps | Delegator | **OWNER** | Review |
| Staging deployment | Delegator | **OWNER** | Review |
| Backup/Restore tools | Delegator | **OWNER** | Review |

## Constraints

### Qingyan (GLM)
- MUST NOT be default coder (except <30 line integration fixes after 2 worker failures)
- MUST NOT modify old repo, delete real data, print secrets, deploy to production, force push

### Xiaomi MiMo
- MUST implement per task packet, no scope/architecture changes
- MUST NOT merge PRs, reduce tests, bypass security
- MUST return: changed files, implementation summary, tests, commands, results, blockers
- MUST confirm no git release action occurred

### DeepSeek
- MUST output per templates/review_report.md
- MUST include all 5 verdicts (Architecture, Security, Tests, UI/UX, Scope)
- FAIL → MUST generate focused rework packet
- MUST NOT modify product scope, architecture, merge PRs, reduce tests
