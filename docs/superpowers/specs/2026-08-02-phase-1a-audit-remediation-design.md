# Phase 1A 审计整改设计

日期：2026-08-02

基线分支：`design/solo-ai-acquisition-system`

基线提交：`10bec446988ec2b31da6a25729a93a40f5833d35`

## 1. 背景和目标

Phase 1A 的租户隔离、证据模型、CRM 幂等晋升和静态抓取边界已经建立，但本地审计确认了三个会影响实际试用的缺口：后台重跑可能覆盖人工终态；手工 URL 和国家补证只有服务函数而没有生产入口；缺少意向信号时顶部评级可能显示 S，却没有清楚提示暂定性质。

本整改不改变既有 Mission、Candidate、Evidence、Assessment、Lead 或未来 SaaS 架构，只补齐用户闭环并升级评分版本。真实外发、浏览器自动化、LinkedIn 登录态和公共注册不进入本次范围。

## 2. 方案比较

### 方案 A：只加状态判断和两个表单

改动最少，但手工 URL 仍需要注入一个 `CompanyExtractor`。MiMo 整体不可用时生产环境没有可用 extractor，仍然不是真正降级，因此不采用。

### 方案 B：手工 URL 始终调用 MiMo 抽取

可以解决 MiMo 联网搜索插件缺失，但不能处理 API、额度、鉴权或模型整体不可用，与“MiMo 不可用仍能完成审核和 CRM 晋升”的验收目标冲突，因此不采用。

### 方案 C：混合抽取和人工结构化证据

MiMo 可用时，用它从已通过 StaticFetcher 的页面抽取并预填结构化事实；MiMo 不可用时，用户提交最小结构化事实，系统验证事实所引用的公开页面文本，再走同一 Evidence、Gate、Score 和 Review 流程。该方案完整、可解释，并保留以后把入口移入后台 Job 的空间，因此采用。

## 3. 人工决定终态保护

`accepted`、`promoted`、`rejected` 是人工终态。任何后台 `candidate_assess` 重试、stale recovery 或重复投递都可以追加幂等 Assessment、更新分数与覆盖率，但不得修改以下字段：

- `candidate.status`
- `candidate.eligibility_code`
- `candidate.decision_reason_code`
- `candidate.decided_by`
- `candidate.decided_at`

`handle_candidate_assess` 必须使用与同步 assessment 相同的终态集合。新增回归测试模拟 Candidate 已被人工拒绝后再次执行同一 assessment Job，断言状态、决定人、原因和时间均保持不变，同时 Assessment 不重复。

国家补证只允许 Candidate 处于 `needs_evidence`。不得对 `accepted`、`promoted`、`rejected` 或普通 `eligible` Candidate 执行 country override。补证成功后进入 `verifying`，写 `candidate.country_overridden` AuditEvent，再排队或执行确定性重评。

## 4. 手工 URL 与国家补证闭环

### 4.1 入口

Mission 详情页增加“补充企业网址”区域，仅当 Mission 的 `allowed_channels` 包含 `manual_url` 且 Mission 未取消时显示。Candidate 处于 `needs_evidence` 且原因为国家未知或冲突时，在 Candidate 卡片显示“补充国家证据”。

生产路由固定为：

- `POST /acquisition/missions/<mission_id>/manual-url`
- `POST /acquisition/candidates/<candidate_id>/country-evidence`

两者都必须使用 `@tenant_required`、CSRF、当前 session 的 `tenant_id/user_id`，跨租户资源继续返回 404。

### 4.2 两级降级

1. **搜索插件不可用、MiMo 模型可用**：用户提供 URL，StaticFetcher 抓取并清洗，MiMo 只做结构化抽取，不执行联网发现。
2. **MiMo 整体不可用**：用户提供 URL、公司名、ISO 国家、买家类型、页面证据句和联系路径。系统不调用大模型，构造确定性的 `ExtractedCompanyFacts`。

人工证据句必须能在 StaticFetcher 返回的清洗文本中规范化匹配；不匹配则拒绝写入，不能把用户自由输入包装成网页证据。Observed claim 的 `source_url` 固定为抓取后的 final URL。联系方式只接受规范邮箱、`mailto:`、HTTP(S) 联系页或受限长度电话号码，并且必须出现在清洗文本中；若提交的是联系页 URL，则必须与 final URL 同一规范域名并经过 StaticFetcher 校验。最终公司域名始终从安全 final URL 规范化，不信任表单提交的域名。

MiMo 的失败只触发显式降级提示，不自动把模型失败结果当作人工事实。用户确认人工字段后才写 Candidate/Evidence。

### 4.3 数据和幂等

继续复用现有规则：

- Candidate：`tenant + mission + domain` 去重；
- Evidence：`tenant + candidate + canonical URL + content hash` 去重；
- Assessment：输入版本唯一约束；
- Candidate 到 Lead：现有 `promoted_lead_id` 和唯一约束；
- 重复提交同一 URL 不创建第二个 Candidate、Evidence 或 Lead。

手工 URL 仍必须经过 StaticFetcher 的 scheme、DNS、私网、重定向、响应大小和 Content-Type 门禁。页面正文不进入日志，URL query 不进入结构化日志。

## 5. Priority v2

`priority-v1` 历史 Assessment 保持不变。新增 `priority-v2`：

- Fit、Intent、Data Quality 权重不变；
- coverage 计算不变；
- coverage 低于 60 时最高 A，延续 v1；
- `priority_mode=fit_quality_provisional_v1` 时最高 A，即使已知 Fit/Data Quality 得分很高；
- Intent 至少有一个已知信号时才允许 S。

Job 和同步 assessment 统一写 `score_version="priority-v2"`。不得原地改写旧 Assessment。新评估可以更新 Candidate 上的当前展示分数，但历史详情仍保留原版本。

Candidate 顶层徽章在 provisional 模式显示“暂定 A/B/C”，并显示“暂无意向信号”。技术详情继续展示 score version 和 priority mode。用户不会看到“低意向”这种把未知当作低分的表述。

## 6. 工作台前置动作

工作台在没有任何已批准 Product Knowledge Snapshot 时，把 `next_action_url` 和空状态主按钮指向 `/acquisition/products`；存在产品后才指向 `/acquisition/missions/new`。Mission 页面现有空状态仍保留，作为深链接和并发删除情况下的第二层保护。

这是低风险 UX 修复，与三个主要整改放在同一验收批次，但不阻塞终态保护的独立提交。

## 7. 本地 SQLite 稳定性

本地长期试用仍保持一个 RQ Worker。SQLite 文件数据库连接增加受测试的 `busy_timeout`，本地文件部署启用 WAL；内存数据库和 PostgreSQL 不应用 SQLite PRAGMA。Web、Worker、reconciler 并发 smoke 至少覆盖一个 Web 写入和一个 reconciler/assessment 写入，不允许出现未处理的 `database is locked`。

WAL 文件与主数据库一起视为运行数据；备份继续使用 SQLite online backup，而不是在运行时直接复制单个 `.db` 文件。

## 8. 日志和网络残余风险

本整改不把 StaticFetcher 改写成固定 IP TLS transport。当前前后 DNS 校验继续保留，并在公共 SaaS 前通过独立 Fetcher Worker 和网络层禁止私网出站关闭残余 TOCTOU 风险。

Hosted Solo 部署时必须对 access log 中的 `/verify-email/<token>` 和 `/reset-password/<token>` 路径脱敏。`safe_event` 不能被当作 WSGI/反向代理 access log 已自动脱敏的证据。

上述两项不阻塞本地人工试用，但阻塞公共 SaaS 发布。

## 9. 错误处理

- URL、DNS、页面类型或大小失败：显示安全错误码，不创建 Candidate；
- MiMo 失败：保留 URL 表单内容，提示进入人工字段模式；
- 人工证据不在页面文本中：返回表单错误，不创建 Evidence；
- country override 状态非法：不修改 Candidate，不创建 Job；
- 重复 Job：允许幂等返回，不覆盖人工终态；
- Redis 不可用：入口显示任务未排队，不伪装成功；可完全人工模式只执行明确设计为同步的单 URL 流程。

任何错误响应都不回显 API Key、模型异常原文、页面正文或私网地址。

## 10. 测试和完成标准

必须增加或扩展以下自动测试：

1. rejected/accepted/promoted Candidate 重跑 assessment 不改变人工字段；
2. country override 只接受 needs_evidence；
3. 手工 URL 路由 tenant/CSRF/跨租户保护；
4. MiMo 抽取模式和完全人工模式都创建相同契约的 Evidence；
5. 人工证据句不在页面中时拒绝；
6. 重复 URL 不重复 Candidate/Evidence；
7. provisional 最高 A，full 模式可以 S；
8. 新 Assessment 使用 priority-v2，旧记录不改写；
9. UI 明确显示“暂定”和“暂无意向信号”；
10. 无产品知识时工作台指向产品知识；
11. SQLite 文件数据库 busy timeout/WAL 与并发 smoke；
12. 全量无浏览器 pytest、Ruff、format、migration round trip 通过。

完成上述代码和本地运行验证后，才能继续 Docker Compose、PostgreSQL 并发和 30 家真实样本验收。Phase 1A release checkpoint 仍须等外部门禁通过后创建。
