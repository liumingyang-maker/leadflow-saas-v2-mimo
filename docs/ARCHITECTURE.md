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

## 配置

- DevelopmentConfig
- TestingConfig
- StagingConfig
- ProductionConfig

生产环境缺秘密时启动失败，不允许弱默认值。

## Migration

每次 schema 改动同时包含 upgrade、可安全时的 downgrade、迁移测试、回滚说明。

## Observability

每个请求有 request ID，每个 job 有 job ID 和 tenant ID。结构化日志禁止秘密和正文。健康端点：`/health/live`、`/health/ready`。
