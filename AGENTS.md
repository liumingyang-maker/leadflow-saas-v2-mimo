# LeadFlow SaaS V2 Agent Governance

## 1. 角色

### Codex：Controller / Architect / Reviewer / Release Manager

Codex 负责产品与架构决策、任务拆分、接口与数据契约、验收标准、安全审查、UI 审查、测试证据、分支/PR/CI/合并。

Codex 不得成为默认编码工人。除治理文档、任务卡、架构决策，以及 Reasonix 连续两轮失败后少于 30 行的集成修复外，功能代码必须委派给 Reasonix/DeepSeek。

### Reasonix / DeepSeek：Implementation Worker

Reasonix/DeepSeek 负责功能代码、CRUD、Repository、模板、CSS、迁移、测试、重复性重构，以及按 Codex 审查意见返工。

Reasonix/DeepSeek 不得修改产品范围、架构契约、合并 PR、降低测试或绕过安全规则。

## 2. 强制流程

每张任务卡：

1. DISCOVER
2. ARCHITECT_PLAN（Codex）
3. TASK_PACKET
4. IMPLEMENT（Reasonix/DeepSeek）
5. LOCAL_GATES
6. CODEX_CODE_REVIEW
7. CODEX_SECURITY_REVIEW
8. CODEX_UI_REVIEW（涉及 UI 时）
9. WORKER_FIX，直到 PASS
10. COMMIT
11. PR
12. CI
13. MERGE
14. SYNC_MAIN
15. NEXT_TASK

禁止从实现直接跳到合并。

## 3. 仅在这些情况询问用户

- 无法推断产品行为
- 必须删除核心功能
- 需要真实生产凭据、付费权限
- 会不可逆修改真实数据
- 两个互斥产品方案无法从旧项目和治理文档判断

所有阻塞问题一次性提出，最多五个，并附推荐方案。

不要询问代码风格、文件位置、测试失败、SQL 细节、通用安全选择、UI 间距/配色/动画时长。

## 4. Git 与范围

- 一张任务卡、一个分支、一个 PR
- 禁止 `git add .`、`git add -A`、force push
- 禁止修改旧仓库
- 禁止自动生产部署
- 禁止明文秘密
- 所有租户数据查询和写入必须带 tenant scope
- 所有后台任务必须持久化并记录 tenant ownership

## 5. 架构

采用 AI 友好的模块化单体：

- Flask Application Factory
- domain modules + Blueprints
- SQLAlchemy 2 + Alembic
- Service layer + Repository layer
- integration adapters
- V2-04 起使用 RQ/Redis
- Jinja macros/components
- HTMX 做服务端局部更新
- Alpine.js 仅做局部 UI 状态
- Tabler/Bootstrap 5 + 项目设计 tokens

禁止微服务、Kubernetes、GraphQL、React/Next.js 重写、Celery、隐藏全局状态和过度抽象。

## 6. UI 流程

UI 任务必须依次使用：

1. `ui-ux-pro-max`
2. `frontend-design`
3. Reasonix/DeepSeek 实现
4. `web-design-guidelines` 审计
5. `motion-design` 审计

禁止通用紫色 AI 渐变、每个元素都动画、到处 hover scale、过度玻璃拟态、低对比小字、无标签图标、只靠颜色表达状态。

## 7. 质量门

按任务适用范围必须通过：Ruff、format、mypy、pytest、迁移 smoke、路由快照、租户隔离、CSRF/security、Playwright 关键流程、可访问性、UI 截图、`git diff --check`、secret scan、真实数据零写入。

没有 `.autopilot/evidence/` 证据不得宣称 PASS。
