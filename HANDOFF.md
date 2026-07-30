# LeadFlow SaaS V2 — Codex 交接文档

**日期**: 2026-07-22
**交接人**: MiMo (AI Assistant)
**仓库**: https://github.com/liumingyang-maker/leadflow-saas-v2-mimo
**分支**: main
**基线提交**: `bbcb2cfbe748ea06926858102eb71bea15b35dd2`
**Tree SHA**: `5c66a090da32c7bfd2c076def0b4c3aa0c93e274`
**环境**: Python 3.11.15, Windows 10

---

## 一、项目概述

LeadFlow SaaS V2 是一个外贸中小企业 CRM 系统，核心功能：寻找潜在客户、整理线索、跟进触达、接收询盘。

**当前定位**: 内部团队使用工具（Internal Mode），不对外商业化，邀请制账户。

**技术栈**:
- 后端: Python 3.11/3.12 + Flask + SQLAlchemy 2 + Alembic + PostgreSQL/SQLite + Redis/RQ
- 前端: Jinja + HTMX + Alpine.js + Tabler/Bootstrap 5
- 工具: pytest + Ruff + Playwright + Docker

---

## 二、当前状态

### 门禁结果
| 门禁 | 结果 |
|------|------|
| `python -m ruff check .` | All checks passed |
| `python -m ruff format --check .` | 114 files formatted |
| `python -m pytest` | 286 passed (0 failed) |
| `git diff --check` | 无错误 |

### Git 状态
- 当前分支: `main`
- 最新提交: `bbcb2cf` fix(inbound): use exact email lookup instead of fuzzy search [INT-102]
- 远程: `origin` → https://github.com/liumingyang-maker/leadflow-saas-v2-mimo.git
- 工作区: 干净，无未提交变更

### 已完成的里程碑（旧系统）
V2-01 至 V2-06 共 65 个任务已通过 autopilot 推进完成。详见 `.autopilot/state.json`。

### 已完成的 Internal Mode 任务（新系统）
| 任务 ID | 标题 | 提交 SHA |
|---------|------|----------|
| INT-001 | Deployment Profile 和 Capability Service | de8d247 |
| INT-002 | 禁用公开注册和商业化页面 | de8d247 |
| INT-003 | 停用 batch_advance 合成 PASS | 5c66a09 |
| INT-101 | 管理员 session revocation (auth_version) | 5c66a09 |
| INT-102 | Inbound 精确邮箱查找 | bbcb2cf |

---

## 三、关键架构决策

### 3.1 Capability Service (`app/core/capabilities.py`)

所有功能开关集中管理，不散布在路由中：

```python
from app.core.capabilities import Capability, is_enabled, require_capability

# 检查
if not is_enabled(app, Capability.PUBLIC_REGISTRATION):
    abort(404)

# 或使用装饰器（需实现）
# @require_capability(app, Capability.INBOUND_API)
```

环境变量控制（见附录 A）：
- `DEPLOYMENT_MODE=internal` — 内部模式
- `ALLOW_PUBLIC_REGISTRATION=false` — 禁用注册
- `BILLING_ENABLED=false` — 禁用计费
- `INBOUND_API_ENABLED=false` — 禁用入站 API

**重要**: 非 production 环境（testing/debug）默认启用所有能力，除非显式设置环境变量。

### 3.2 管理员 Session Revocation (`app/modules/accounts/admin_routes.py`)

`admin_required` 改为装饰器工厂模式：

```python
@app.get("/admin")
@admin_required(app)  # 必须传入 app
def admin_console():
    ...
```

每次请求从数据库查询管理员，验证：
- 管理员存在且未被禁用
- `admin_auth_version` 匹配 session 中的版本
- `must_change_password` 标记

### 3.3 幂等 exactly-once (`app/modules/inbound/service.py`)

`process_and_finalize()` 在单事务中完成：
1. 续租 claim (30秒)
2. 执行业务逻辑（不 commit）
3. Finalize 幂等记录（验证 claim_token）
4. 原子 commit 或 rollback

```python
result, ownership_held = process_and_finalize(
    app, tenant_id=..., token_digest=..., body=...,
    idempotency_key=..., storage_key=..., claim_token=...,
)
if not ownership_held:
    return 409 + Retry-After
```

### 3.4 租户隔离

所有业务表保留 `tenant_id`。Repository 和 Service 必须显式传入 `tenant_id`。不允许硬编码唯一租户 ID。

---

## 四、待完成任务清单

按优先级和依赖顺序排列（来自 `docs/INTERNAL_PRODUCT_ROADMAP.md`）：

### P0 — 内部共享使用前必须完成

| ID | 标题 | 简述 |
|----|------|------|
| INT-103 | 幂等 replay 保存原始 HTTP 状态码 | InboundIdempotency 新增 response_status 字段，replay 返回原始状态码而非固定 200 |
| INT-104 | Inbound 并发验证 | 需要真实并发测试（多线程/进程），验证 exactly-once 在 SQLite 和 PostgreSQL 下的行为 |
| INT-106 | 迁移前历史重复数据预检 | 创建 `tools/db_preflight.py`，检查限流和幂等表是否有重复记录 |
| INT-201 | PostgreSQL 共享部署 | 更新 docker-compose，配置连接池，创建数据迁移脚本 |
| INT-202 | Gunicorn + HTTPS | 添加 Gunicorn，创建 deploy/gunicorn.conf.py，Caddy/Nginx 配置 |
| INT-204 | Secrets 管理 | .env.example，生产密钥验证，禁止日志输出 secret |
| INT-205 | 备份/恢复 | pg_dump 备份策略，恢复演练脚本 |

### P1 — 内部稳定运行必须完成

| ID | 标题 | 简述 |
|----|------|------|
| INT-004 | 架构决策记录 (ADR) | 创建 docs/adr/ 目录，记录关键设计决策 |
| INT-105 | 统一 Inbound CORS 和 API 错误结构 | 已部分完成（_inbound_response helper），需补充 request_id 和错误结构 |
| INT-203 | Worker 和 Job 可靠性 | 遗留 running job 处理，retry 退避，correlation ID |
| INT-206 | 日志、错误追踪和审计 | 结构化日志，Sentry 集成，审计事件覆盖 |
| INT-302 | Lead 工作台改进 | 精确/模糊搜索区分，批量操作，数据导出 |
| INT-303 | Jobs 运维界面 | 队列状态，错误摘要，retry/cancel |
| INT-304 | Outreach 内部安全模式 | Dry Run，发送限额，allowlist |
| INT-401 | CI 分层 | Python 3.12 blocking + 3.11 non-blocking |
| INT-402 | 最小 Playwright 冒烟 | 登录、Lead、Job、Outreach、CSRF 等关键流程 |

### P2 — 改善体验和维护性

| ID | 标题 |
|----|------|
| INT-301 | 内部首页和导航精简 |
| INT-305 | 内部帮助和操作手册 |
| INT-403 | 内部发布清单 |
| INT-404 | 内部发布验收标准 |

### Deferred-Commercial — 当前禁止实现

COMM-001 至 COMM-007（公众注册、套餐、支付、配额、SSO、合规、高可用）全部冻结，只保留设计边界。

---

## 五、关键文件索引

### 核心配置
| 文件 | 说明 |
|------|------|
| `app/config.py` | 环境配置，生产密钥验证 |
| `app/core/capabilities.py` | **新增** Capability Service |
| `app/core/errors.py` | 错误处理，含 FeatureDisabledError |
| `app/__init__.py` | App Factory，集成 capabilities |
| `app/extensions.py` | SQLAlchemy/CSRF/模型注册 |

### 认证与授权
| 文件 | 说明 |
|------|------|
| `app/modules/accounts/models.py` | User(含 auth_version)、AdminUser(含 auth_version)、Tenant、TenantMembership |
| `app/modules/accounts/guards.py` | tenant_required 装饰器（membership join + auth_version） |
| `app/modules/accounts/admin_routes.py` | **已修改** admin_required 工厂模式 + auth_version 验证 |
| `app/modules/accounts/admin_service.py` | AdminIdentity 含 auth_version |
| `app/modules/accounts/routes.py` | 注册路由（受 Capability 控制） |
| `app/modules/accounts/service.py` | 登录/注册/密码重置，auth_version 写入 |

### Inbound 幂等
| 文件 | 说明 |
|------|------|
| `app/modules/inbound/service.py` | **核心** process_and_finalize, check_idempotency, claim_token 租约 |
| `app/modules/inbound/models.py` | InboundIdempotency 含 claim_token, processing_expires_at |
| `app/modules/inbound/routes.py` | **已修改** 统一 CORS, capability 检查 |

### Leads/CRM
| 文件 | 说明 |
|------|------|
| `app/modules/leads/repository.py` | **已修改** 新增 find_by_email 精确查找 |
| `app/modules/leads/models.py` | Lead, Company, Tag, Activity |
| `app/modules/leads/import_service.py` | CSV/XLSX 导入 |

### 迁移
| 文件 | 说明 |
|------|------|
| `migrations/versions/0011_security_hardening.py` | auth_version, 唯一约束, 支付表 |
| `migrations/versions/0012_idempotency_lease.py` | claim_token, processing_expires_at, 回填 |
| `tests/test_migration_paths.py` | 4 个迁移路径测试 |

### 工具
| 文件 | 说明 |
|------|------|
| `tools/autopilot.py` | 状态机（已无实际意义，仅供参考） |
| `tools/batch_advance.py` | **已修改** 默认禁用，需 --unsafe-bulk-state-mutation |
| `tools/deepseek_reviewer.py` | DeepSeek API 审查工具 |

### 文档
| 文件 | 说明 |
|------|------|
| `docs/INTERNAL_PRODUCT_ROADMAP.md` | **新增** 完整路线图（1842行），Codex 应首先阅读 |
| `docs/ARCHITECTURE.md` | 架构文档 |
| `docs/UI_SYSTEM.md` | UI 规范 |

---

## 六、运行命令

### 安装依赖
```bash
cd c:\Users\97020\Desktop\leadflow-saas-v2-main\leadflow-saas-v2-main
python -m pip install -r requirements.txt -r requirements-dev.txt
```

### 运行门禁
```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
git diff --check
```

### 格式化
```bash
python -m ruff format .
```

### Alembic 迁移
```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head  # 验证往返
```

### 运行应用
```bash
# 开发
flask run --debug

# 生产
gunicorn "app:create_app('production')" --bind 0.0.0.0:5000 --workers 2 --threads 4 --timeout 120
```

---

## 七、已知限制和注意事项

### 7.1 Alembic 迁移待创建
- AdminUser.auth_version 需要新的 migration（当前仅 ORM 模型有，数据库无）
- 建议 revision: `0013_admin_auth_version`

### 7.2 Autopilot 已无实际意义
- `.autopilot/state.json` 显示所有里程碑完成，但这只是状态机推进，不代表真正的代码审查
- `batch_advance.py` 已禁用，不要尝试使用它来推进任务

### 7.3 测试环境
- 单元测试使用 SQLite 内存数据库
- CI 仅配置 Python 3.12（需添加 3.11 矩阵）
- Playwright 测试在缺少浏览器时静默跳过

### 7.4 安全相关
- 生产环境必须设置所有密钥（见附录 A）
- `.env` 文件不应提交到 git（已在 .gitignore）
- HANDOFF.md 中曾有 DeepSeek API Key，已替换为占位符

### 7.5 幂等指纹窗口
- 显式幂等键: 24 小时 TTL
- 指纹模式（无显式 key）: 5 分钟 TTL
- 指纹模式的 expires_at 在 process_and_finalize 中使用 FINGERPRINT_WINDOW_MINUTES

---

## 八、实施建议

### 第一批（依赖顺序）
1. INT-004: ADR 文档（无代码变更，纯文档）
2. INT-103: 幂等 replay 状态码（新增 Alembic 0013）
3. INT-106: 迁移前预检脚本
4. INT-201: PostgreSQL 部署
5. INT-202: Gunicorn/HTTPS
6. INT-204: Secrets 管理
7. INT-205: 备份/恢复

### 第二批
8. INT-104: 并发验证（依赖 PostgreSQL）
9. INT-203: Worker 可靠性
10. INT-206: 日志/审计
11. INT-301-305: UI 改进
12. INT-401-404: CI/发布

### 分支命名
```
int/INT-103-replay-status-code
int/INT-201-postgresql-deployment
```

### 提交格式
```
fix(inbound): save and replay original HTTP status [INT-103]
feat(db): add preflight script for migration safety [INT-106]
```

---

## 九、AI 执行协议

### Task Packet 模板
每个任务必须使用以下格式（详见 `docs/INTERNAL_PRODUCT_ROADMAP.md` 第 16 章）：
- Goal / Current Mode / Baseline Commit
- Preconditions / In Scope / Out of Scope
- Current Risk / Required Design / Implementation Steps
- Tests / Migration / Security Review
- UX States / Commercialization Hook / Acceptance Criteria
- Rollback / Deliverables

### AI 硬性限制
- 不得修改已发布 migration
- 不得删除失败测试来让 CI 通过
- 不得使用 `except Exception` 吞掉数据库错误
- 不得通过 sleep 伪造并发测试
- 不得将 UI 隐藏视为服务端授权
- 不得自动推送 main 或标记 PASS
- 未经要求不得实现 Billing、Public Signup 或 Payment Webhook

### Definition of Done
1. 根因已明确
2. 实现符合 Internal Mode
3. 未破坏商业化预留边界
4. 新增行为测试（不只是修改 fixture）
5. 必要时新增 migration
6. Migration 路径有历史数据测试
7. 错误和边界状态已覆盖
8. Security review 已完成
9. UI 有 Loading/Empty/Error/Success
10. 文档更新
11. 全部门禁通过
12. 独立 reviewer 通过

---

## 附录 A：环境变量

```env
# Deployment profile
DEPLOYMENT_MODE=internal
APP_ENV=production

# Product capabilities
ALLOW_PUBLIC_REGISTRATION=false
INVITE_ONLY=true
BILLING_ENABLED=false
PAYMENT_WEBHOOKS_ENABLED=false
INBOUND_API_ENABLED=false
OUTREACH_SEND_ENABLED=true
ADMIN_CONSOLE_ENABLED=true

# Database (生产用 PostgreSQL)
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/leadflow

# Redis
REDIS_URL=redis://localhost:6379

# Security (必须全部设置，>=32 字符，不得使用默认值)
SECRET_KEY=<random-32+>
TENANT_SECRET_KEY=<random-32+>
TRACKING_SIGNING_KEY=<random-32+>
UNSUBSCRIBE_SIGNING_KEY=<random-32+>
INBOUND_TOKEN_KEY=<random-32+>

# Session
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=Lax

# Operations
LOG_FORMAT=json
LOG_LEVEL=INFO
ERROR_TRACKING_DSN=
RELEASE_SHA=
```

---

## 附录 B：数据库 Schema 索引

核心表（由 Alembic 管理）：
- `tenants` — 租户
- `users` — 用户（含 auth_version）
- `admin_users` — 管理员（含 auth_version, disabled_at, must_change_password）
- `tenant_memberships` — 租户-用户关系
- `email_tokens` — 邮箱验证/密码重置令牌
- `leads` — 线索
- `companies` — 公司
- `tags` / `lead_tags` — 标签
- `activities` — 活动记录
- `import_batches` / `import_batch_rows` — 导入批次
- `jobs` — 采集任务
- `email_templates` / `email_tracking` / `suppressions` — 外联
- `inbound_tokens` / `inbound_allowed_origins` — 入站 API
- `inbound_rate_limits` — 限流（含唯一约束）
- `inbound_idempotency` — 幂等（含 claim_token, processing_expires_at）
- `audit_events` — 审计事件
- `coupons` / `payments` / `payment_events` — 支付（模型已有，业务未实现）

---

## 附录 C：Capability 矩阵

| Capability | Internal | Commercial |
|------------|----------|------------|
| PUBLIC_REGISTRATION | 关闭 | 开启 |
| BILLING | 关闭 | 开启 |
| PAYMENT_WEBHOOKS | 关闭 | 开启 |
| INBOUND_API | 按需 | 客户级配置 |
| OUTREACH_SEND | 开启 | 开启 |
| MULTI_TENANT_SELF_SERVICE | 关闭 | 开启 |
| ADMIN_CONSOLE | 开启 | 开启 |
| INVITE_ONLY | 开启 | 关闭 |

---

**交接完成。请首先阅读 `docs/INTERNAL_PRODUCT_ROADMAP.md` 获取完整上下文，然后按上述任务清单顺序实施。**
