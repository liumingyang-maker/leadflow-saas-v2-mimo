# LeadFlow 单人版 AI 获客分阶段实施路线图

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按可独立验收的 Phase 1A 与 Phase 1B 交付单人版 AI 获客闭环，同时保留未来公共 SaaS 的租户、Capability、Job、审计与安全边界。

**Architecture:** Phase 1A 使用 MiMo、受限静态 HTTP Fetcher、持久化 Candidate/Evidence、确定性门禁与人工审核完成核心闭环，不依赖浏览器。Phase 1B 在核心闭环之上增加无数据库/无密钥的独立 Browser Worker、最小竞品入口和实用导出/通知增强；Browser 故障不得影响 Phase 1A。

**Tech Stack:** Python 3.12、Flask、SQLAlchemy 2、Alembic、RQ/Redis、Jinja/HTMX、OpenAI-compatible MiMo API、httpx、Pydantic、Playwright MCP、Docker Compose、pytest、Playwright、Ruff。

---

## 1. 状态与权威来源

- 已确认设计：`docs/superpowers/specs/2026-08-01-solo-ai-acquisition-system-design.md`
- 设计确认提交：`5e93456 docs(acquisition): simplify solo workflow design`
- 本路线图替代旧版“13 个任务一次交付”的执行顺序；旧顺序不得继续直接实施。
- 本文件只负责依赖、阶段门禁、发布顺序和跨计划规则；逐文件代码、测试和提交步骤在两份子计划中。

详细计划：

1. `docs/superpowers/plans/2026-08-01-solo-acquisition-phase-1a.md`
2. `docs/superpowers/plans/2026-08-01-solo-acquisition-phase-1b-browser.md`

## 2. 为什么必须拆成两份计划

旧计划把数据模型、MiMo、评分、Browser MCP、UI、CRM 和运维放在同一条关键路径上。这样会造成：

- Node/Chromium/MCP 未安装时，静态官网研究也无法交付；
- 浏览器安全与进程清理阻塞最基本的候选审核；
- 单个 migration 和提交过大，难以独立回滚；
- 用户无法在早期获得可用的工作台、候选列表和 CRM 晋升；
- Browser 故障容易被误判为整个 AI 获客系统故障。

拆分后，Phase 1A 是可日常使用的产品；Phase 1B 是可以单独关闭的研究增强。

## 3. 固定执行顺序

```text
设计提交 5e93456
  -> Phase 1A Task 1-12
  -> Phase 1A staging / 真实小样本门禁
  -> 创建 Phase 1A release checkpoint
  -> Phase 1B Task 1-8
  -> Phase 1B browser smoke / 安全门禁
  -> 进入正式竞品雷达 Phase 2（不在本计划实施）
```

禁止在 Phase 1A 通过前实施 Phase 1B。允许提前阅读 Phase 1B，但不得提前创建 browser migration、安装
Node/Chromium 或改变部署拓扑。

## 4. Phase 1A 交付边界

Phase 1A 必须交付：

- `AdminUser.auth_version` migration 缺口修复；
- 产品知识快照；
- 只有产品、国家、买家类型三个必填字段的 Mission；
- MiMo 结构化规划、联网发现能力探针和显式降级；
- 静态 HTTP Fetcher、URL/SSRF/redirect/content-type/大小限制；
- Candidate、Evidence、Assessment、MissionSuggestion 持久化；
- `country_unknown/conflicting -> needs_evidence`；
- 未知信号使用 `None`、`signal_coverage` 和暂定 Priority；
- 候选接受/拒绝/补证、幂等晋升 CRM；
- 三层候选信息、真实今日工作台、应用内通知；
- 结构化拒绝原因、成本复盘、半自动建议；
- MiMo/Redis/Job 健康、结构化日志、周期 reconciler、数据库备份核验；
- 现有外发门禁保持不变，不增加真实自动发送。

Phase 1A 明确不安装或运行浏览器，不实现完整竞品雷达，不做邮件通知、CSV、WhatsApp 快捷入口。

## 5. Phase 1A 发布门禁

- [ ] `python -m pytest tests/acquisition -q` 通过。
- [ ] `python -m pytest` 全量通过。
- [ ] `python -m ruff check .` 通过。
- [ ] `python -m ruff format --check .` 通过。
- [ ] `python -m alembic upgrade head` 在新 SQLite 与 PostgreSQL staging 均通过。
- [ ] downgrade 到上一 revision 后再 upgrade head 通过。
- [ ] 同一 ScoreInput 重放得到完全相同结果。
- [ ] 国家未知候选保留在补证队列，不进入推荐或拒绝。
- [ ] MiMo 关闭时仍可从手工 URL 完成 Evidence、审核和 CRM 晋升。
- [ ] 用户接受 Candidate 的重复请求只产生一个 Company/Lead。
- [ ] 工作台计数和通知均按 tenant 隔离。
- [ ] 真实联网 smoke 只有显式 `RUN_LIVE_MIMO=1` 才运行。
- [ ] `.autopilot/evidence/ACQ-1A/` 保存门禁输出和关键 UI 截图。

## 6. Phase 1B 交付边界

Phase 1B 必须交付：

- 默认关闭的 `BROWSER_RESEARCH` Capability；
- 独立 Browser Worker 镜像、`browser` RQ 队列和持久化 artifacts volume；
- Browser Worker 不持有 `DATABASE_URL`、MiMo Key 或 Tenant Secret Key；
- BrowserSitePolicy、BrowserResearchRun、run-scoped token digest 和状态机；
- 默认 Worker 生成并校验 BrowserResearchPlan，Browser Worker 只执行 allowlist 动作；
- Playwright MCP 固定版本、Chromium 安装检查、截图和文本清洗；
- 120 秒/10 页/12 工具调用预算、同域并发 1；
- 成功、失败、取消、超时、Worker 崩溃后的进程和 artifacts 清理；
- 静态 Fetcher 失败且 SitePolicy 允许时才回退 Browser；
- 用户输入竞品/官方经销商 URL 的最小竞品入口；
- 可选任务完成邮件、审计 CSV 导出、公开企业 WhatsApp 链接；
- 浏览器禁用、未安装或故障时 Phase 1A 全部回归通过。

Phase 1B 不实现完整竞品档案、定期 diff、雷达网络图、LinkedIn 自动化、登录态浏览、验证码绕过或自动外联。

## 7. Phase 1B 发布门禁

- [ ] `BROWSER_RESEARCH_ENABLED=false` 时 Phase 1A 全量测试通过。
- [ ] Browser 容器环境中没有 `DATABASE_URL`、`MIMO_API_KEY`、`TENANT_SECRET_KEY`。
- [ ] `npm ci` 和 Chromium 安装探针通过，固定 package lock 未漂移。
- [ ] private/loopback/link-local/metadata URL 在应用层和容器网络层均被阻断。
- [ ] redirect 与最终 URL 每跳重新验证。
- [ ] captcha/login/policy/prompt-injection/预算错误均 fail closed 且不自动重试。
- [ ] Browser Worker 被强制终止后，reconciler 能结束 run、回收 lease 和临时目录。
- [ ] 30 天 artifacts 清理不删除 Evidence 元数据。
- [ ] LinkedIn URL 始终进入 `blocked/manual_only`，租户策略不能覆盖。
- [ ] CSV 不包含 debug/hash/模型隐藏字段；WhatsApp 不自动发送。
- [ ] `.autopilot/evidence/ACQ-1B/` 保存容器探针、网络阻断和关键 UI 截图。

## 8. 数据库 revision 顺序

固定 revision 链：

```text
0012_idempotency_lease
  -> 0013_admin_auth_version
  -> 0014_acquisition_core
  -> 0015_browser_research
```

- `0013` 只修复已有模型/迁移不一致，不混入获客业务。
- `0014` 只包含 Phase 1A 的产品、Mission、Candidate、Evidence、Assessment、Suggestion、Notification、
  ProviderStatus 和 CRM/Job 增量字段。
- `0015` 只包含 Phase 1B 的 BrowserSitePolicy 与 BrowserResearchRun。
- 不修改任何已经发布的 migration。

## 9. 提交与审查策略

每个 Task 一个提交。任何提交都不得同时跨 Phase 1A 与 Phase 1B。推荐前缀：

```text
fix(migrations): add admin auth version revision
feat(acquisition): add mission contracts and repositories
feat(ai): add validated MiMo acquisition provider
feat(evidence): add restricted static website fetcher
feat(workbench): connect acquisition actions and notifications
feat(browser): add allowlisted MCP gateway
test(acquisition): close phase 1a operational gates
docs(operations): document browser recovery and rollback
```

每个 migration、tenant-scoped Repository、Candidate -> Lead 晋升、SecretStore 使用、外发边界和 Browser
网络边界都需要单独安全审查。UI 提交需包含 desktop 与 390px viewport 截图，但复杂策略页面不要求在
手机上完成管理。

## 10. 回滚原则

- Phase 1A 回滚：先关闭 `AI_RESEARCH/WEBSITE_EVIDENCE_FETCH/AI_OUTREACH_DRAFT`，停止新 Job，再回滚应用；
  已保存 Candidate/Evidence 不删除。
- Phase 1B 回滚：先关闭 `BROWSER_RESEARCH`，停止 browser queue，终止 run 并保留 Evidence 元数据；
  不需要回滚 Phase 1A。
- migration downgrade 只用于 staging 演练；生产恢复优先使用发布前备份和向前修复。
- 禁止通过删除 Candidate、Evidence、AuditEvent 或历史 Assessment 解决部署问题。

## 11. 真实试点顺序

Phase 1A 先使用三个小样本：

1. 墨西哥 / 摩托车发动机 / 经销商；
2. 秘鲁 / 摩托车配件 / 进口商；
3. 一个用户提供的官网 URL，MiMo 联网能力关闭。

每个 Mission 最多 10 个深入验证候选。记录完成时间、候选数、门禁分布、接受率、未知率、费用和人工
审核分钟数。若中位数超过 5 分钟或 P95 超过 15 分钟，先减少搜索/页面预算，不增加并发。

Phase 1B 只用批准的测试官网和一个竞品官方经销商页。不得用 LinkedIn、登录页面或真实联系人发送做
验收对象。

## 12. 完成定义

只有两份子计划各自的全部任务、测试、迁移、运行手册和 evidence 门禁完成，才能宣称单人版 Phase 1
完成。完成 Phase 1A 时必须明确称为“核心闭环完成”，不能暗示 Browser 或最小竞品入口已经上线。
