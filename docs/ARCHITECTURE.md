# LeadFlow SaaS V2 Architecture

## 风格

适合 AI 维护的模块化单体。

## 技术栈

- Python 3.12
- Flask Application Factory
- SQLAlchemy 2
- Alembic
- PostgreSQL（staging/production）
- SQLite（仅本地与单元测试）
- Redis + RQ（V2-04 起）
- Jinja
- Tabler / Bootstrap 5
- HTMX
- Alpine.js
- CSS variables + design tokens
- pytest / Ruff / mypy
- Playwright
- Docker Compose

## 目录

```text
app/
  __init__.py
  config.py
  extensions.py
  core/
    security.py
    errors.py
    request_id.py
    tenancy.py
  modules/
    auth/
    tenants/
    leads/
    crm/
    collection/
    jobs/
    outreach/
    inbound/
    billing/
    admin/
  integrations/
  ui/
  templates/
  static/
migrations/
tests/
  unit/
  integration/
  e2e/
scripts/
docs/
```

## 模块契约

模块可包含：`blueprint.py`、`models.py`、`repository.py`、`service.py`、`forms.py`、`schemas.py`、`policies.py`、`events.py`。

依赖方向：

```text
blueprint -> service -> repository -> database
                    -> integration adapter
```

模板禁止直接查数据库。

## 租户隔离

所有租户表有 `tenant_id NOT NULL`。Repository 对外暴露 `get_for_tenant`、`list_for_tenant`、`update_for_tenant` 等明确接口。无租户查询只允许管理员且命名必须带 `for_admin`。

## Jobs

V2-04 引入 RQ。Web 仅入队，Worker 执行。每个 Job 持久化 ID、tenant_id、status、progress、error summary。

Phase 1A 的单人部署固定为一个 `default` 队列 Worker，避免 SQLite 多写入者带来的锁竞争。独立 `reconciler` 每分钟恢复过期 heartbeat、推导 Mission 终态并以 `dedupe_key` 生成通知。只有迁移到 PostgreSQL，并完成并发与队列压测后，才允许把 Worker 扩到 2 个；继续扩容必须有新的容量数据。

获客研究是可降级能力：MiMo 负责计划、联网发现与结构化抽取，但不属于 Web 就绪依赖。MiMo 不可用时，用户仍可提交公开网站 URL，通过静态抓取、证据保存、确定性评分和人工审核完成流程。浏览器自动化不在 Phase 1A 的无人值守执行边界内。

## 配置

- DevelopmentConfig
- TestingConfig
- ProductionConfig

生产环境缺秘密时启动失败，不允许弱默认值。

## Migration

每次 schema 改动同时包含 upgrade、可安全时的 downgrade、迁移测试、回滚说明。

## Observability

每个请求有 request ID，每个 job 有 job ID。结构化 JSON 日志只接受事件名、request/job/mission/candidate ID、provider、stage、safe error code 和耗时；tenant_id 只保留 12 位哈希引用。Key、token、secret、password、authorization、cookie、body、HTML 一律丢弃；URL 只记录 scheme、host、path，不记录 query/fragment。

`safe_event` 的保护范围仅限应用主动生成的结构化事件，不会自动处理反向代理或 WSGI 服务器的 access log。托管部署必须在实际选用的反向代理与 WSGI access logger 中，对 `/verify-email/` 和 `/reset-password/` 后面的路径段做脱敏，并对最终输出的整行日志进行验证。在部署层配置完成并验证实际日志行之前，该项是公共发布阻断项；本地单元测试不能证明它已关闭。

- `/health/live`：仅证明进程活着，不访问外部依赖。
- `/health/ready`：检查 SQL 与 Redis；失败返回 503 和安全错误码，不回显连接串或异常。
- MiMo 状态：保存在 `provider_statuses`，设置页展示最近检查、最近成功、连续失败和安全错误码。连续 3 次失败生成一次应用内通知；恢复写不可变审计事件。
- Docker 的 Web、Worker、reconciler 日志按 10 MB × 5 文件轮转。

产品数据、Mission、Candidate、Evidence、Assessment、Suggestion 与 Notification 都以 SQL 为事实来源；Redis 只承载可重建的队列状态。具体恢复步骤见 `RUNBOOK_BACKUP_RESTORE.md`。

## Fetcher 网络安全边界

`StaticFetcher` 会验证每次重定向的目标地址并比较解析结果，但 DNS 校验与实际建立连接之间仍存在 TOCTOU（time-of-check/time-of-use）残余风险。公共 SaaS 不得只依赖应用层 URL/DNS 校验：Fetcher 必须运行在隔离 Worker 中，并由网络层拒绝向 private、loopback、link-local、reserved、metadata 等私有地址范围发起 egress。只有在真实托管网络中验证该拒绝策略后才能关闭此发布阻断项；本地单元测试不构成部署控制证据。

Phase 1A 的暂定性能目标是：单个 30 候选 Mission 在 MiMo 正常时 15 分钟内进入可审核状态，手工 URL 单条在 60 秒内完成，Web 页面请求不等待后台研究。它们是 staging 采样门槛，不是当前本地 SQLite 测试已经证明的 SLA；真实 30 样本报告会记录 duration、coverage、接受率和每个候选成本。
