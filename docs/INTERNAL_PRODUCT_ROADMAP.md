# LeadFlow SaaS V2 内部使用版后续开发与未来商业化预留路线

> 文档用途：交给 AI 编程代理、开发人员、设计人员和审查人员，作为后续工作的统一执行依据。  
> 当前产品定位：**团队内部使用工具，不对外商业化，不提供公众自助注册，不承诺外部 SLA。**  
> 未来方向：可能恢复商业化，因此当前整改不得破坏租户隔离、迁移链、计费边界和扩展能力。  
> 当前代码基线：`106c66f506bf95627e014c4500bd24d29b009e55`  
> 仓库：`liumingyang-maker/leadflow-saas-v2-mimo`  
> 文档状态：`IMPLEMENTATION PLAN`  
> 建议存放位置：`docs/INTERNAL_PRODUCT_ROADMAP.md`

---

## 1. 决策摘要

LeadFlow SaaS V2 从现在起按两个阶段设计：

| 阶段 | 定位 | 当前状态 |
|---|---|---|
| Internal Mode | 单个可信团队内部使用，邀请制账户，低到中等并发，不收费 | **当前实施阶段** |
| Commercial Mode | 面向外部客户，多租户自助注册、计费、套餐、合规和 SLA | **冻结，仅预留边界** |

当前阶段的目标不是继续堆叠 SaaS 功能，而是完成以下五件事：

1. 让团队可以稳定地使用核心 CRM、采集、任务、外联和入站功能。
2. 保证账户、租户、数据和任务不会因为并发、迁移或误操作而损坏。
3. 建立可靠的共享部署、备份、恢复、日志、错误追踪和发布流程。
4. 删除或关闭所有会让内部团队误以为系统已经商业化的入口。
5. 通过集中配置和模块边界保留未来商业化能力，避免今后推倒重写。

**内部使用不等于可以忽略安全和数据完整性。** 可以推迟的是计费、公开注册、高可用、多区域、外部合规和客户支持；不能推迟的是身份验证、权限、备份、数据库迁移、错误恢复、密钥管理和核心业务数据正确性。

---

## 2. 当前运行假设

以下是假设，不是硬编码限制。若实际情况超出阈值，应重新评估架构。

| 项目 | Internal Mode 默认假设 |
|---|---|
| 组织数量 | 1 个主要内部组织；数据模型仍保留多租户 |
| 用户数量 | 2–30 个实名团队账户 |
| 并发用户 | 通常低于 10 |
| 数据量 | 低于 100 万 Leads；超出后评估索引、分页和归档 |
| 部署数量 | 1 个共享团队环境，另有本地开发环境 |
| 可用性 | 工作时间内可用；无正式外部 SLA |
| 网络 | 优先部署在 VPN、Tailscale、公司内网或受限域名 |
| 数据敏感度 | 包含联系人、邮件、公司和外联记录，按敏感业务数据处理 |
| 支付 | 禁用 |
| 公众注册 | 禁用 |
| 公共 API | 默认关闭；团队明确需要时单独开启 |
| 邮件发送 | 受控开启，必须有发送限额、退订和审计 |
| 生产数据库 | 推荐 PostgreSQL；SQLite 仅用于本地开发和临时单机试用 |

当出现以下任一情况时，触发“商业化/规模化重新评审”：

- 第一个外部客户或非团队成员需要账户；
- 开始收费、试用、优惠券或套餐限制；
- 开放公众注册；
- 承诺 SLA、客户支持或数据处理协议；
- 共享环境超过 30 个活跃用户；
- Leads 超过 100 万或任务量持续增长；
- 需要多实例、多主机或多区域；
- 需要公开 API、SDK、第三方集成市场；
- 需要 SOC 2、ISO 27001、GDPR、CCPA 或行业合规；
- 任何客户要求 SSO、SAML、SCIM、MFA 或审计导出。

---

## 3. 不可破坏的设计原则

### 3.1 保留租户模型，不把系统改成真正的单租户代码

即使内部只有一个组织，也必须继续遵守：

- 所有租户业务表保留 `tenant_id`；
- Repository 和 Service 必须显式传入 `tenant_id`；
- 不允许在模板、路由或全局变量中硬编码唯一租户 ID；
- 测试继续覆盖跨租户不可读、不可写；
- 未来商业化时无需重构全部数据模型。

内部模式只是“部署和产品策略单组织”，不是“数据库取消租户”。

### 3.2 商业化开关必须集中管理

不得在数十个路由和模板中散落：

```python
if app.config["INTERNAL_MODE"]:
    ...
```

应建立统一能力服务，例如：

```python
# app/core/capabilities.py

from enum import StrEnum

class Capability(StrEnum):
    PUBLIC_REGISTRATION = "public_registration"
    BILLING = "billing"
    PAYMENT_WEBHOOKS = "payment_webhooks"
    INBOUND_API = "inbound_api"
    OUTREACH_SEND = "outreach_send"
    MULTI_TENANT_SELF_SERVICE = "multi_tenant_self_service"
    ADMIN_CONSOLE = "admin_console"

def is_enabled(app, capability: Capability) -> bool:
    profile = app.config["DEPLOYMENT_PROFILE"]
    ...
```

建议环境变量：

```env
DEPLOYMENT_MODE=internal
ALLOW_PUBLIC_REGISTRATION=false
INVITE_ONLY=true
BILLING_ENABLED=false
PAYMENT_WEBHOOKS_ENABLED=false
INBOUND_API_ENABLED=false
OUTREACH_SEND_ENABLED=true
ADMIN_CONSOLE_ENABLED=true
```

所有服务端路由必须验证能力开关。仅隐藏菜单不构成禁用。

### 3.3 数据库迁移一旦推送不得修改

规则：

1. 已进入 `main` 的 Alembic revision 视为不可变。
2. 后续修复只能新建 revision。
3. 每个 migration 必须测试：
   - 空数据库到 head；
   - 上一个正式 revision 到 head；
   - downgrade 一个 revision；
   - 再次 upgrade；
   - 有历史数据时的行为；
   - 可能存在的重复数据和 NULL 数据。
4. 生产升级前运行预检脚本。
5. 任何数据清理必须可审计，不得静默删除冲突记录。

### 3.4 内部环境也禁止开发默认密钥

共享环境必须满足：

```env
APP_ENV=production
SECRET_KEY=<随机值>
TENANT_SECRET_KEY=<随机值>
TRACKING_SIGNING_KEY=<随机值>
UNSUBSCRIBE_SIGNING_KEY=<随机值>
INBOUND_TOKEN_KEY=<随机值>
```

不得因为“只有团队使用”而保留开发默认值。

### 3.5 AI 不得自己实现、自己审查、自己宣布通过

一个任务至少区分三个角色：

| 角色 | 职责 |
|---|---|
| Implementer | 修改代码和测试 |
| Reviewer | 审查代码、风险和范围 |
| Verifier | 独立运行测试并验证验收条件 |

同一个 AI 会话不得同时承担最终 Implementer 和 Verifier。

---

## 4. 功能范围决策

| 模块 | Internal Mode 决策 | 未来商业化备注 |
|---|---|---|
| Accounts | 保留，改为邀请制 | 后续增加公众注册、邮箱验证策略、SSO |
| Tenants | 保留数据模型；默认一个主要组织 | 后续开放自助创建、切换和套餐绑定 |
| Leads / CRM | 核心功能，优先稳定 | 后续配额、共享权限、细粒度 RBAC |
| Collection | 保留 | 后续资源配额、代理池、客户级限制 |
| Jobs / Worker | 保留，重点可靠性 | 后续水平扩容、队列隔离、优先级 |
| Outreach | 受控保留 | 后续发送配额、信誉、域名验证、合规 |
| Inbound API | 默认关闭，按需开启 | 后续 API 版本、客户密钥、配额和 SLA |
| Admin | 保留，必须修复会话撤销 | 后续客服工具、impersonation 审计 |
| Billing / Coupons / Payments | **完全禁用，不继续实现业务流程** | 后续单独商业化里程碑完成 |
| Payment Webhooks | 禁用 | 后续必须重新安全设计和专项审计 |
| Public Registration | 禁用 | 后续通过 Capability 打开 |
| Autopilot State | 仅开发辅助，不作为发布证明 | 后续可重构为正式工程工作流 |
| DeepSeek/Codex Review | 可用于辅助审查 | 永远不能替代真实测试和人工发布决定 |

---

## 5. 推荐的内部部署目标架构

### 5.1 共享团队环境

```text
Internet / Company Network
          |
      HTTPS / VPN
          |
   Caddy / Nginx / Traefik
          |
      Gunicorn Web
          |
   ---------------------
   |        |          |
PostgreSQL Redis      RQ Worker
   |
Encrypted backup storage
```

### 5.2 数据库策略

| 环境 | 数据库 |
|---|---|
| 单元测试 | SQLite 内存数据库 |
| 本地开发 | SQLite 文件或本地 PostgreSQL |
| 团队共享环境 | **PostgreSQL** |
| 未来商业环境 | PostgreSQL，按规模评估只读副本、连接池和高可用 |

共享环境不建议继续使用 Web 和 Worker 共用的 SQLite 文件。原因：

- 多进程写入容易产生锁冲突；
- 行锁与并发语义和 PostgreSQL 不同；
- 未来商业化迁移成本更高；
- 备份与恢复可控性较弱。

### 5.3 Web 服务

内部共享环境必须使用正式 WSGI 服务：

```text
gunicorn "app:create_app('production')" \
  --bind 0.0.0.0:5000 \
  --workers 2 \
  --threads 4 \
  --timeout 120
```

实际 worker 数量应根据主机资源调整。禁止在共享环境使用 Flask 开发服务器。

### 5.4 网络暴露

优先顺序：

1. Tailscale/VPN 内部访问；
2. 公司内网反向代理；
3. 受身份保护的公网域名；
4. 完全公开公网仅在确有需要时使用。

公共 Inbound API 是例外路径，必须单独启用，不能因此把全部后台页面暴露为公共服务。

---

## 6. 用户角色与内部工作流设计

### 6.1 用户角色

Internal Mode 最小角色：

| 角色 | 权限 |
|---|---|
| System Admin | 管理部署、用户、租户、密钥和系统诊断 |
| Team Owner | 管理组织成员、业务设置、外联和入站 |
| Operator | 管理 Leads、Collection、Jobs、Outreach |
| Reviewer | 审核 Leads、结果和任务，不修改系统设置 |
| Read-only | 查看数据和报表，不产生业务副作用 |

当前若代码只支持较少角色，可先映射到现有模型，但权限检查必须集中在 Guard/Policy 层，不得仅依赖菜单隐藏。

### 6.2 核心工作流

#### 工作流 A：Lead 导入和审核

```text
导入/采集/Inbound
→ 数据验证
→ 精确去重
→ pending_review
→ 人工接受/拒绝
→ 分配阶段
→ 后续动作
```

设计要求：

- 精确邮箱查询不得复用模糊搜索；
- 重复判定必须显示原因；
- 批量操作必须有确认和结果摘要；
- 错误记录必须可以导出；
- 页面必须有 Loading、Empty、Error、Success 四类状态。

#### 工作流 B：Collection 和 Jobs

```text
创建采集任务
→ 参数预览
→ 入队
→ Worker 执行
→ 进度/日志
→ 成功、失败或取消
→ 结果导入 Leads
```

设计要求：

- 任务必须可重试但不能重复产生不可控副作用；
- 显示 `queued/running/succeeded/failed/cancelled`；
- 失败信息应提供可操作原因；
- 管理员能查看卡住任务；
- Worker 重启后任务状态可恢复或明确标记失败。

#### 工作流 C：Outreach

```text
选择 Leads
→ 预览目标和内容
→ Dry Run
→ 确认发送
→ 记录发送结果
→ 打开/点击/回复/退订
```

内部模式必须默认安全：

- 默认 Dry Run；
- 每次批量发送显示收件人数；
- 设置每日发送上限；
- 支持测试邮箱 allowlist；
- 退订机制始终生效；
- 发送失败不得无限重试；
- 所有发送动作写入审计日志。

#### 工作流 D：Inbound API

```text
外部表单
→ Token 校验
→ Origin 检查
→ Rate Limit
→ Idempotency Claim
→ 单事务写入 Lead/Activity/Idempotency
→ 返回结果
```

若团队暂时不用此功能，应通过配置完全关闭，而不是保持公开但“没人使用”。

---

## 7. UI/UX 设计方向

### 7.1 内部工具优先级

内部版不需要：

- 营销首页；
- 价格页；
- Upgrade CTA；
- Trial 倒计时；
- Coupon 页面；
- Payment 页面；
- 面向客户的 onboarding 演示；
- 复杂的移动端营销体验。

内部版需要：

- 高信息密度；
- 清晰的状态和错误；
- 快速批量操作；
- 可恢复的操作流程；
- 稳定的表格、筛选和分页；
- 操作确认与审计；
- 环境提示；
- 键盘和桌面优先。

### 7.2 全局布局

建议：

```text
Top Bar:
- LeadFlow Internal
- Environment: INTERNAL / STAGING / PROD
- 当前组织
- 当前用户
- 系统状态入口

Sidebar:
- Workbench
- Leads
- Collection
- Jobs
- Outreach
- Inbound（能力开启时）
- Audit
- Settings
- Admin（有权限时）
```

禁止显示 Billing、Plan、Coupon 和 Upgrade 菜单。

### 7.3 环境和风险提示

页面顶部显示非干扰式环境标识：

```text
INTERNAL
```

危险操作使用统一样式：

- 删除；
- 批量发送；
- 清空任务；
- 轮换 Token；
- 禁用用户；
- 数据导入覆盖；
- 迁移或恢复。

### 7.4 表格规范

所有数据表格至少支持：

- 服务端分页；
- 明确总数；
- 过滤条件可清除；
- 空状态；
- 加载状态；
- 错误重试；
- 批量选择；
- 可见列设置可延后；
- 不允许将 10 万条记录一次性载入浏览器。

### 7.5 可访问性最低标准

- 所有输入有 label；
- 错误信息与字段关联；
- 按钮有明确文本或 aria-label；
- 键盘可操作；
- 焦点可见；
- 颜色不是唯一状态表达；
- 表单提交失败后焦点移到错误摘要；
- 重要动作不得只依赖 hover。

---

## 8. 后续工作路线总览

### 优先级定义

| 等级 | 含义 |
|---|---|
| P0 | 内部共享使用前必须完成 |
| P1 | 内部稳定运行必须完成 |
| P2 | 改善体验和维护性 |
| Deferred-Commercial | 当前禁止实现，只保留设计说明 |

### 里程碑

| 里程碑 | 目标 |
|---|---|
| INT-M0 | 固化内部模式与工程治理 |
| INT-M1 | 关闭身份和数据正确性缺陷 |
| INT-M2 | 建立可靠共享部署 |
| INT-M3 | 完成内部操作体验 |
| INT-M4 | 建立测试、发布和恢复闭环 |
| COMM-M0+ | 未来商业化准备，当前冻结 |

---

# 9. INT-M0：内部模式与工程治理

## INT-001：建立 Deployment Profile 和 Capability 服务

**优先级：P0**

### 目标

以集中配置控制 Internal/Commercial 行为，避免未来商业化时全仓搜索和重写。

### 建议文件

```text
app/core/capabilities.py
app/config.py
app/__init__.py
tests/test_capabilities.py
docs/DEPLOYMENT_MODES.md
```

### 实现步骤

1. 定义 `DeploymentMode = Literal["internal", "commercial"]`。
2. 定义 Capability 枚举。
3. 将环境变量解析为明确布尔值，禁止用字符串真值。
4. 在 App Factory 中加载并验证配置。
5. 增加模板 context processor：
   ```python
   can("billing")
   ```
6. 所有路由通过服务端检查 Capability。
7. Internal Mode 默认：
   - public registration false；
   - billing false；
   - payment webhooks false；
   - invite only true；
   - inbound API false；
   - admin true。
8. Production 配置缺失关键变量时启动失败。

### 验收条件

- `DEPLOYMENT_MODE=internal` 时无法访问商业化路由；
- 修改模板 URL 不能绕过服务端；
- 测试覆盖每个 Capability；
- 未知 Deployment Mode 启动失败；
- 文档列出所有能力开关。

### 未来商业化预留

只通过 Capability 打开功能，不修改核心 CRM 数据模型。

---

## INT-002：禁用公开注册和商业化页面

**优先级：P0**

### 目标

内部版本采用邀请制，隐藏并禁止商业功能。

### 实现步骤

1. `GET/POST /register` 在 Internal Mode 返回 404 或重定向到内部登录说明。
2. 新增 Admin 创建用户或邀请用户流程。
3. 隐藏价格、试用、套餐、优惠券、支付入口。
4. 保留相关数据表和 migration，不删除支付模型。
5. 所有商业路由未启用时返回结构化 `feature_disabled`。
6. README 明确“非商业化内部系统”。

### 验收条件

- 未登录用户不能自行注册；
- 只有 System Admin/Owner 能创建团队账户；
- 不存在可直接调用的支付 webhook；
- UI 不展示 Upgrade/Plan/Payment；
- 现有账户正常登录。

### 未来商业化预留

公开注册恢复时必须走独立 Tenant Provisioning Service，而不是直接复用管理员创建用户逻辑。

---

## INT-003：建立 AI 工作协议，停用不可信批量验收

**优先级：P0**

### 目标

防止 AI 或脚本自动生成 PASS 并修改验收状态。

### 建议改动

```text
tools/batch_advance.py
tools/autopilot.py
AGENTS.md
docs/AI_ENGINEERING_WORKFLOW.md
```

### 实现步骤

1. `batch_advance.py` 默认直接退出并提示已弃用。
2. 如必须保留历史能力，要求显式：
   ```text
   --unsafe-bulk-state-mutation
   ```
3. 批量脚本不得写 `reviewer=... PASS`。
4. 自动 gate 只能产生 `GATES_PASSED` 状态。
5. Review 必须有独立 reviewer 标识。
6. `.autopilot/state.json` 不再作为产品发布证明。
7. 创建 `release-manifest.json`，记录：
   - commit SHA；
   - migration head；
   - test summary；
   - reviewer；
   - verifier；
   - deployment profile。
8. AI 任务采用后文统一 Task Packet。

### 验收条件

- 无法通过一次命令将多个任务标记 ACCEPTED；
- gate 与 review 分离；
- 脏工作区不能产生可发布证据；
- 所有发布证据绑定 commit SHA；
- 文档明确 AI 无权自行解除 Release Hold。

### 未来商业化预留

后续可将流程迁移到 GitHub PR Checks、required reviewers 和签名 release tag。

---

## INT-004：建立架构决策记录

**优先级：P1**

创建：

```text
docs/adr/0001-internal-product-mode.md
docs/adr/0002-shared-postgresql.md
docs/adr/0003-capability-service.md
docs/adr/0004-idempotency-transaction-boundary.md
docs/adr/0005-migration-immutability.md
```

每份 ADR 必须包含：

- Context；
- Decision；
- Alternatives；
- Consequences；
- Commercialization impact；
- Revisit trigger。

---

# 10. INT-M1：身份、数据正确性和核心 API

## INT-101：修复管理员会话撤销和强制改密

**优先级：P0**

### 当前问题

管理员 Guard 仅信任 session 中的 `is_admin`，未在每次请求确认管理员仍有效，也未强制执行 `must_change_password`。

### 设计

为 AdminUser 增加或确认：

```text
auth_version
disabled_at
must_change_password
last_login_at
password_changed_at
```

管理员登录 session 保存：

```text
admin_id
admin_auth_version
is_admin
```

每次受保护请求：

1. 必须存在 admin_id；
2. 查询管理员；
3. 拒绝 disabled；
4. 验证 auth_version；
5. 若 must_change_password，只允许：
   - 修改密码；
   - 登出；
   - 必要静态资源。

密码变化、禁用和“登出所有设备”必须递增 auth_version。

### 验收测试

- 禁用管理员后现有 session 失效；
- 修改密码后其他设备 session 失效；
- must_change_password 无法访问 Admin Console；
- session 只有 `is_admin=true` 不能访问；
- 管理员审计日志记录登录、失败、禁用和改密。

### 未来商业化预留

未来可将 Admin 身份与客户账户分离，并增加 MFA/SSO。

---

## INT-102：修复 Inbound 的邮箱精确查询

**优先级：P0**

### 当前风险

Inbound 使用通用模糊搜索查找邮箱，可能将新询盘关联到邮箱中包含相同片段的错误 Lead。

### 实现步骤

1. 在 `LeadRepository` 新增：
   ```python
   find_by_email(email, tenant_id)
   ```
2. 使用规范化：
   - strip；
   - lowercase；
   - 不随意修改合法邮箱本地部分。
3. Inbound 只调用精确邮箱方法。
4. 明确产品重复策略：
   - 默认：同一租户、同一标准化邮箱复用已有 Lead；
   - 每次新 Inbound 仍可增加新的 Activity；
   - 是否更新姓名/电话由显式策略决定。
5. 不要直接添加唯一约束，除非团队确认“同一邮箱永远只能一个 Lead”。
6. 增加模糊碰撞测试。

### 验收测试

```text
已有：sales-user@example.com
新增：user@example.com
结果：创建不同 Lead
```

并覆盖大小写和前后空格。

### 未来商业化预留

未来可以提供 Tenant 级重复策略配置，但 Repository 的精确方法保持不变。

---

## INT-103：保存幂等 replay 的原始 HTTP 状态码

**优先级：P1**

### 目标

首次返回 400 的请求，replay 仍返回 400，而不是固定 200。

### 数据模型

新增：

```text
InboundIdempotency.response_status Integer NOT NULL DEFAULT 200
```

使用新 Alembic revision，不得修改 0012。

### 实现步骤

1. `process_and_finalize()` 同时保存 response JSON 和 HTTP status。
2. `check_idempotency()` replay 返回：
   ```text
   status, response_json, response_status, claim_token
   ```
   或使用 dataclass，避免 tuple 继续增长。
3. 路由恢复原始状态码。
4. 只缓存明确可重放的业务响应。
5. 5xx 默认不标记 completed；根据错误类型决定 failed/retryable。

### 验收测试

- 首次 200，replay 200；
- 首次 400，replay 400；
- processing 仍 409；
- conflict 仍 409；
- response body 完全一致。

### 未来商业化预留

未来公开 API 应保存必要响应头和 API 版本，但不得保存敏感认证头。

---

## INT-104：完成 Inbound 并发验证

**优先级：P0**

### 目标

验证当前事务设计，而不是仅依赖代码推理。

### 测试矩阵

| 场景 | 预期 |
|---|---|
| 两个相同 key、相同 payload 并发 | 只产生一次业务副作用 |
| 两个相同 key、不同 payload | 一个处理，一个 conflict |
| 旧 claim 在新 claim 接管后 finalize | 旧事务失败并 rollback |
| processing lease 到期 | 只有一个接管者成功 |
| NULL lease | 只有一个接管者成功 |
| finalize rowcount=0 | Lead 和 Activity 均不提交 |
| 业务逻辑抛异常 | 幂等状态和业务写入均不提交 |
| 指纹 5 分钟内重复 | replay |
| 指纹超过 5 分钟 | 可重新处理 |
| SQLite 写锁 | 返回受控错误，不泄露堆栈 |
| PostgreSQL 行锁 | 结果符合设计 |

### 技术要求

- 使用文件 SQLite 才能进行多连接测试；
- PostgreSQL 测试通过 CI service container；
- 使用线程屏障或进程屏障，不使用 sleep 猜测顺序；
- 断言 Activity 数量；
- 断言幂等记录最终状态；
- 断言没有重复 Lead 或错误 Lead。

### 验收条件

至少在 PostgreSQL 上证明相同 key 只产生一个 Activity。

### 未来商业化预留

若未来加入外部副作用，采用 Transactional Outbox，不宣称数据库事务能覆盖外部服务。

---

## INT-105：统一 Inbound CORS 和 API 错误结构

**优先级：P1**

### 目标

POST 和 OPTIONS 使用统一策略；拒绝的 Origin 不获得 ACAO。

### 错误结构

```json
{
  "error": "rate_limited",
  "message": "Request limit exceeded",
  "request_id": "..."
}
```

### 实现步骤

1. 提取 Origin 验证函数；
2. 只对已允许 Origin 设置 ACAO；
3. 被拒绝 Origin 返回 403，但不回显 ACAO；
4. POST 和 OPTIONS 共用 allowlist；
5. `Vary: Origin` 仅在 Origin 相关响应中设置；
6. 所有 API 响应有 request_id；
7. 429、409、503 添加合理 Retry-After；
8. CORS 测试覆盖允许、拒绝、无 Origin。

### 未来商业化预留

未来根据客户配置支持多个精确 Origin；不要支持不受控通配符和 credentials 组合。

---

## INT-106：迁移前历史重复数据预检

**优先级：P0**

### 目标

确保 0011 的唯一约束在真实历史数据库上不会突然失败。

### 新增脚本

```text
tools/db_preflight.py
```

检查：

```sql
SELECT scope, bucket, COUNT(*)
FROM inbound_rate_limits
GROUP BY scope, bucket
HAVING COUNT(*) > 1;
```

```sql
SELECT tenant_id, token_digest, idempotency_key, COUNT(*)
FROM inbound_idempotency
GROUP BY tenant_id, token_digest, idempotency_key
HAVING COUNT(*) > 1;
```

### 处理规则

- 无重复：退出 0；
- 可自动合并的限流记录：输出建议，不默认写入；
- payload 相同的幂等重复：生成确定性合并报告；
- payload 不同：退出非零，要求人工决定；
- 未显式 `--apply` 时不得修改数据库；
- apply 前自动备份。

### 验收条件

- 脚本在空库和有数据数据库可运行；
- 发现冲突时明确退出；
- 报告包含主键和合并建议；
- migration runbook 强制先运行预检。

---

# 11. INT-M2：共享部署和运行可靠性

## INT-201：共享环境迁移到 PostgreSQL

**优先级：P0**

### 实现步骤

1. 更新 Compose：
   - 添加 PostgreSQL；
   - Web/Worker 使用同一 PostgreSQL；
   - SQLite 仅作为本地 profile。
2. 增加 `DATABASE_URL` 生产校验。
3. 增加 PostgreSQL driver。
4. 配置连接池：
   ```text
   pool_pre_ping=true
   pool_recycle
   pool_size
   max_overflow
   ```
5. 运行全量 migrations。
6. 建立 SQLite → PostgreSQL 数据迁移脚本或一次性导入流程。
7. 迁移前备份。
8. 迁移后验证表行数、租户、Lead、Activity、Job 和 Outbound 数据。

### 验收条件

- Web 与 Worker 在 PostgreSQL 上运行；
- CI 有 PostgreSQL 集成 job；
- 共享部署不再挂载 SQLite 数据文件；
- 备份和恢复流程通过。

### 未来商业化预留

生产数据库从一开始使用 PostgreSQL，为后续连接池、只读副本和高可用预留。

---

## INT-202：使用正式 WSGI 和 HTTPS

**优先级：P0**

### 实现步骤

1. 添加 Gunicorn 到生产依赖。
2. 创建：
   ```text
   deploy/gunicorn.conf.py
   ```
3. Docker CMD 改为 Gunicorn。
4. 添加 Caddy/Nginx 配置。
5. 强制 HTTPS。
6. 设置：
   - Secure Cookie；
   - ProxyFix；
   - trusted proxy 数量；
   - HSTS；
   - request size；
   - timeout。
7. 通过 `/health/live` 和 `/health/ready` 分离存活与依赖就绪。

### 验收条件

- 共享环境不显示 Flask development server 警告；
- HTTPS Cookie 正常；
- 代理后的客户端 IP 可信；
- 数据库不可用时 readiness 失败；
- live 不因短暂外部依赖失败而退出。

---

## INT-203：Worker 和 Job 可靠性

**优先级：P1**

### 设计要求

- Job 有明确状态；
- Worker 启动时处理遗留 running job；
- retry 次数和退避集中配置；
- 不对永久性错误无限重试；
- 每个 Job 有 correlation ID；
- 超时可配置；
- 失败日志可查看；
- 可以安全重新入队。

### 验收测试

- Worker 处理中崩溃；
- Redis 短暂断开；
- 数据库短暂断开；
- 重复 enqueue；
- Job 超时；
- 用户取消；
- 重试后不会重复产生业务记录。

### 未来商业化预留

后续增加客户队列隔离、配额、优先级和水平扩容。

---

## INT-204：Secrets 和配置管理

**优先级：P0**

### 实现步骤

1. 创建 `.env.example`，只放占位符。
2. Production 启动时验证所有必要变量。
3. 禁止日志输出完整 token、密码、API key。
4. 对 SecretStore 做密钥轮换文档。
5. 建立内部密钥轮换流程。
6. 将共享环境密钥放在：
   - Docker secrets；
   - GitHub Actions secrets；
   - 云 Secret Manager；
   - 至少是受权限控制的部署环境变量。
7. 删除仓库历史中的真实密钥。

### 验收条件

- 开发默认密钥在 Production 无法启动；
- 日志不包含 Secret；
- 密钥轮换后仍可读取旧加密数据；
- 旧密钥有明确淘汰流程。

---

## INT-205：备份、恢复和数据保留

**优先级：P0**

### 默认策略

| 类型 | 频率 | 保留 |
|---|---|---|
| PostgreSQL 完整备份 | 每日 | 14 天 |
| 周备份 | 每周 | 8 周 |
| 月备份 | 每月 | 6 个月 |
| 上传/导出文件 | 每日同步 | 与数据库策略一致 |
| 配置清单 | 每次发布 | 至少保留最近 20 个版本 |

### 要求

- 备份加密；
- 备份不与生产主机位于同一磁盘；
- 每月至少一次恢复演练；
- 恢复到隔离环境；
- 验证 migrations、用户、Lead、Activity 和任务；
- 记录 RPO/RTO 实测结果；
- 恢复演练失败视为 P0。

### 未来商业化预留

未来按 SLA 升级连续归档、PITR、跨区域复制和客户级恢复策略。

---

## INT-206：日志、错误追踪和审计

**优先级：P1**

### 日志规范

结构化字段：

```json
{
  "timestamp": "...",
  "level": "INFO",
  "request_id": "...",
  "tenant_id": "...",
  "user_id": "...",
  "job_id": "...",
  "event": "...",
  "message": "..."
}
```

禁止记录：

- 密码；
- 完整 token；
- 加密密钥；
- 邮件正文全文，除非明确需要且受控；
- 原始支付签名；
- 敏感认证头。

### 错误追踪

可使用 Sentry 或同类内部工具：

- 捕获未处理异常；
- release 绑定 commit SHA；
- 环境分离；
- PII scrub；
- 不上传 Secret。

### 审计事件

至少记录：

- 登录成功/失败；
- 用户创建/禁用；
- 管理员改密；
- Token 轮换；
- Lead 批量操作；
- Job 创建/取消/重试；
- Outreach 发送；
- 配置变更；
- 数据导入/导出；
- 备份和恢复操作。

---

# 12. INT-M3：内部产品体验

## INT-301：内部首页和导航精简

**优先级：P2**

### 目标

首页只呈现团队需要处理的工作。

建议卡片：

- Pending Review Leads；
- Failed Jobs；
- Running Jobs；
- 今日 Outreach；
- Inbound Errors；
- 最近导入；
- 系统健康状态。

不显示：

- MRR；
- Trial；
- Subscription；
- Upgrade；
- Coupon；
- Payment。

### 验收条件

- 不同角色只看到可访问入口；
- 卡片链接到已过滤列表；
- 空状态有下一步；
- 数据加载失败不影响整个页面。

---

## INT-302：Lead 工作台

**优先级：P1**

改进：

- 精确和模糊搜索区分；
- 状态与阶段筛选；
- 批量接受、拒绝、打标签、分配阶段；
- 操作前确认；
- 操作后摘要；
- 错误行可重试；
- Lead 时间线；
- 最近 Inbound/Outreach Activity；
- 数据导出。

设计必须清晰区分：

```text
status = 数据审核状态
stage = 销售流程阶段
```

---

## INT-303：Jobs 运维界面

**优先级：P1**

显示：

- 队列；
- Job 类型；
- 创建者；
- 创建时间；
- 开始时间；
- 完成时间；
- 尝试次数；
- 错误摘要；
- correlation ID；
- retry/cancel 按钮。

危险操作必须确认，并记录 AuditEvent。

---

## INT-304：Outreach 内部安全模式

**优先级：P1**

功能：

- Dry Run；
- 测试发送；
- allowlist 模式；
- 日发送上限；
- 每批上限；
- 预览；
- 退订状态；
- 抑制名单；
- 错误报告；
- 停止发送开关。

未来商业化前不得实现“无限批量发送”。

---

## INT-305：内部帮助和操作手册

**优先级：P2**

创建：

```text
docs/USER_GUIDE_INTERNAL.md
docs/ADMIN_RUNBOOK.md
docs/JOB_TROUBLESHOOTING.md
docs/OUTREACH_SAFETY.md
docs/INBOUND_INTEGRATION.md
docs/BACKUP_RESTORE.md
docs/RELEASE_RUNBOOK.md
```

文档必须与 UI 名称一致。

---

# 13. INT-M4：质量、发布和验收

## INT-401：CI 分层

**优先级：P0**

### Blocking Job

- Python 3.12；
- Ruff；
- Format；
- Pytest；
- Alembic fresh upgrade；
- 0011 → head；
- PostgreSQL integration；
- `git diff --check`；
- migration drift check。

### Non-blocking Compatibility Job

- Python 3.11；
- 依赖安全检查；
- 慢速浏览器测试；
- 静态类型检查，如后续引入。

内部生产运行时建议固定 Python 3.12。保持 3.11 兼容可作为非阻断目标，未来商业化前重新决定正式支持矩阵。

---

## INT-402：最小 Playwright 冒烟集

**优先级：P1**

只覆盖关键流程，不追求全页面自动化：

1. 登录；
2. Lead 列表和详情；
3. 创建或导入 Lead；
4. 创建 Job；
5. 查看 Job 状态；
6. Outreach Dry Run；
7. Inbound 设置；
8. Admin 禁用用户；
9. 登出；
10. CSRF 表单。

浏览器必须在 CI 安装，禁止 silently skip。

---

## INT-403：内部发布清单

每次共享环境发布必须生成：

```json
{
  "version": "internal-YYYYMMDD.N",
  "commit_sha": "...",
  "migration_head": "...",
  "deployment_mode": "internal",
  "database": "postgresql",
  "tests": {
    "unit": "...",
    "integration": "...",
    "migration": "...",
    "browser": "..."
  },
  "backup_id": "...",
  "reviewer": "...",
  "verifier": "..."
}
```

发布步骤：

1. 冻结目标 commit；
2. 创建备份；
3. 运行数据库预检；
4. 运行 migration dry run；
5. 部署；
6. 运行 smoke test；
7. 观察错误；
8. 记录 release manifest；
9. 有问题优先 roll forward；
10. 如必须 rollback，先确认 migration 可安全降级。

---

## INT-404：内部发布验收标准

内部版本可以发布，必须同时满足：

- 无开放 P0；
- 无会导致错误 Lead、数据丢失或跨租户访问的 P1；
- Admin session revocation 完成；
- 公共注册和 Billing 完全禁用；
- PostgreSQL 共享环境通过；
- 正式 WSGI + HTTPS；
- Production 密钥校验；
- 备份成功；
- 恢复演练成功；
- Migration 路径测试通过；
- Inbound 并发测试通过，或 Inbound API 保持禁用；
- 核心 Playwright 冒烟通过；
- 发布 manifest 绑定 commit；
- 独立 verifier 签字。

---

# 14. 当前明确延期的商业化工作

以下项目在 Internal Mode **禁止 AI 自行实现**。只能维护设计文档和接口边界。

## COMM-001：公众注册和租户自助开通

未来需要：

- email verification；
- anti-abuse；
- tenant provisioning；
- slug/domain；
- onboarding；
- trial；
- terms acceptance；
- tenant lifecycle。

## COMM-002：套餐和 Entitlements

不要把权限判断直接写成：

```python
if tenant.plan == "pro":
```

未来应建立：

```text
Plan
Entitlement
TenantSubscription
UsageCounter
```

业务模块查询 Capability/Entitlement Service。

## COMM-003：支付适配器和 Webhook

未来重新实现：

- Provider Adapter；
- Stripe 或其他 Provider；
- 原始请求体验签；
- timestamp tolerance；
- event replay protection；
- PaymentEvent processing state；
- transactional outbox；
- amount/currency Decimal；
-退款；
- chargeback；
- reconciliation；
- webhook retry；
- dead-letter。

当前 Payment/Coupon 模型只视为预留草图，不代表功能完成。

## COMM-004：客户级配额和计量

包括：

- Lead 数；
- Job 数；
- Collection 次数；
- Outreach 次数；
- API 请求数；
- 存储；
- 成员数。

当前内部模式不做配额，只保留计量事件接口设计。

## COMM-005：SaaS 级权限和身份

未来：

- MFA；
- OIDC；
- SAML；
- SCIM；
- domain claim；
- session management；
- device history；
- customer admin；
- support access；
- impersonation 审计。

## COMM-006：隐私、合规和客户运维

未来：

- Privacy Policy；
- Terms；
- DPA；
- DSAR；
- retention；
- deletion；
- export；
- subprocessor list；
- audit export；
- incident response；
- vulnerability management。

## COMM-007：规模化和高可用

未来：

- 多 Web 实例；
- 多 Worker；
- 队列隔离；
- object storage；
- connection pooling；
- read replicas；
- autoscaling；
- HA Redis；
- PostgreSQL HA；
- metrics/SLO；
- capacity planning。

---

# 15. 为未来商业化现在必须保留的接口

即使暂时不实现，也必须保留以下设计边界：

| 边界 | 当前要求 |
|---|---|
| Tenant Scope | 所有租户数据显式 tenant_id |
| Capabilities | 集中服务判断功能是否开启 |
| Entitlements | 不在模板和路由硬编码套餐 |
| Billing Adapter | 未来 Provider 与业务模型隔离 |
| Outbox | 外部副作用未来通过事件/outbox |
| API Versioning | 新商业 API 使用 `/api/v1` |
| Audit | 高风险动作统一事件模型 |
| Migrations | 已发布 revision 不可变 |
| Identity | User/Admin session version 可撤销 |
| Storage | 不把本地磁盘路径写死在领域逻辑 |
| Logging | request_id、tenant_id、user_id 结构化 |
| Error Codes | 稳定机器错误码与用户消息分离 |
| Configuration | 环境变量解析集中、启动时验证 |

建议在代码中使用统一注释：

```python
# COMMERCIALIZATION_HOOK:
# Future external-customer behavior must be implemented behind CapabilityService.
```

此注释只标记真正的扩展点，不要在所有文件滥用。

---

# 16. AI 执行协议

## 16.1 每个 AI 任务必须使用以下 Task Packet

```markdown
# Task ID
INT-XXX

# Goal
一句话说明目标。

# Current Mode
Internal Mode

# Baseline Commit
<full SHA>

# Preconditions
必须先完成的任务和 migration。

# In Scope
允许修改的文件和行为。

# Out of Scope
明确禁止的扩展。

# Current Risk
当前缺陷、触发条件和影响。

# Required Design
必须遵循的架构原则。

# Implementation Steps
1.
2.
3.

# Tests
必须新增的测试。

# Migration
是否需要；revision 名称；历史数据策略。

# Security Review
需要检查的边界。

# UX States
Loading / Empty / Error / Success / Disabled。

# Commercialization Hook
未来如何打开功能而不重写。

# Acceptance Criteria
可机器验证的条件。

# Rollback
如何回退代码和数据。

# Deliverables
修改文件、命令、结果、风险和未完成项。
```

## 16.2 AI 的硬性限制

AI 不得：

- 修改任务范围之外的大量模块；
- 修改已发布 migration；
- 删除失败测试来让 CI 通过；
- 使用 `except Exception` 吞掉数据库错误；
- 通过 sleep 伪造并发测试；
- 将 UI 隐藏视为服务端授权；
- 自动推送 main；
- 自动标记审计 PASS；
- 自动解除 Release Hold；
- 将“代码存在”视为“功能验证完成”；
- 在未验证 PostgreSQL 时宣称并发正确；
- 在未执行恢复演练时宣称备份可用；
- 未经要求实现 Billing、Public Signup 或 Payment Webhook。

## 16.3 AI 输出格式

每次实现后必须输出：

```markdown
## Summary
## Files Changed
## Schema/Migration
## Security Impact
## UX Impact
## Tests Added
## Commands Run
## Exact Results
## Known Limitations
## Commercialization Compatibility
## Rollback Notes
```

---

# 17. 分支、提交和审查规范

### 分支

```text
int/INT-102-exact-email-lookup
int/INT-201-postgresql-deployment
comm/COMM-003-payment-webhooks
```

商业化任务未解冻前禁止创建 `comm/*` 实现分支。

### Commit

```text
fix(inbound): use tenant-scoped exact email lookup [INT-102]
feat(core): add internal deployment capability profile [INT-001]
test(db): cover 0011 to 0012 historical upgrade [INT-106]
```

### Pull Request

必须包含：

- Task ID；
- 基线 SHA；
- 问题复现；
- 改动前失败证据；
- 改动后测试；
- migration；
- 回滚；
- 商业化兼容；
- 独立 reviewer。

---

# 18. Definition of Done

一个任务只有同时满足以下条件才能完成：

1. 根因已明确；
2. 实现符合 Internal Mode；
3. 未破坏商业化预留边界；
4. 新增行为测试，而不只是修改 fixture；
5. 必要时新增 migration；
6. Migration 路径有历史数据测试；
7. 错误和边界状态已覆盖；
8. Security review 已完成；
9. UI 有 Loading/Empty/Error/Success；
10. 文档更新；
11. 全部门禁通过；
12. 独立 reviewer 通过；
13. 独立 verifier 重新运行；
14. 没有通过自动脚本伪造 PASS；
15. 发布 manifest 能绑定 commit SHA。

---

# 19. 建议实施顺序

严格按依赖执行：

```text
INT-001 Capability Service
→ INT-002 Disable Public/Commercial Surfaces
→ INT-003 AI Workflow Hardening
→ INT-101 Admin Session Revocation
→ INT-102 Exact Email Lookup
→ INT-103 Replay HTTP Status
→ INT-105 CORS/Error Contract
→ INT-106 DB Preflight
→ INT-201 PostgreSQL
→ INT-202 Gunicorn/HTTPS
→ INT-204 Secrets
→ INT-205 Backup/Restore
→ INT-104 Concurrency Verification
→ INT-203 Worker Reliability
→ INT-206 Logging/Audit
→ INT-301–305 Internal UX
→ INT-401–404 CI, Browser, Release
```

如果团队暂时不需要 Inbound API，可在完成 INT-001 后将其关闭，并把 INT-103、INT-104、INT-105 延后到重新启用前；但 INT-102 的精确 Lead 查询仍应完成，因为类似错误可能出现在其他导入路径。

---

# 20. 当前 Internal Release Blocker 清单

在共享团队正式使用前，至少关闭：

- [ ] Capability Service 和 Internal Mode；
- [ ] 公开注册禁用；
- [ ] Billing/Payment/Webhook 禁用；
- [ ] 管理员 session revocation；
- [ ] Inbound 精确邮箱查询；
- [ ] PostgreSQL 共享环境；
- [ ] 正式 WSGI；
- [ ] HTTPS 和 Production Cookie；
- [ ] Production Secrets；
- [ ] 数据库 migration 预检；
- [ ] 备份成功；
- [ ] 恢复演练成功；
- [ ] 核心 CI；
- [ ] 最小 Playwright；
- [ ] Inbound 禁用或并发验证通过；
- [ ] Autopilot 批量伪验收停用；
- [ ] 发布 manifest；
- [ ] 管理员操作审计。

---

# 21. 商业化重新启动检查点

未来决定商业化时，不要直接打开 `BILLING_ENABLED=true`。应先创建独立项目阶段：

```text
COMMERCIALIZATION READINESS REVIEW
```

输出：

1. 当前数据和租户模型审计；
2. 安全威胁模型；
3. 计费和 Entitlement 设计；
4. 支付 Provider 设计；
5. 合规差距；
6. SLA/SLO；
7. 容量计划；
8. 客户支持流程；
9. 隐私和法律文件；
10. 商业发布 Gate；
11. Internal 数据迁移或隔离方案；
12. 外部渗透测试和第三方审计。

只有该阶段通过后，才能实现 Public Signup、Billing 和 Payment Webhooks。

---

# 22. 最终目标状态

内部版本完成后，应具备以下特征：

- 团队账户全部邀请制和可撤销；
- 管理员权限可实时撤销；
- 核心 CRM 流程稳定；
- Inbound 若开启，具备正确幂等和并发行为；
- Web 与 Worker 使用 PostgreSQL；
- 生产使用 Gunicorn 和 HTTPS；
- 密钥无默认值；
- 每日自动备份；
- 恢复流程真实演练；
- 错误可追踪；
- 高风险操作有审计；
- 关键流程有浏览器测试；
- AI 工作不再能伪造验收；
- Billing、Payment、自助注册保持关闭；
- 商业化扩展点集中、明确且有文档；
- 未来可以通过独立商业化里程碑升级，而不是重写整个系统。

---

## 附录 A：建议新增环境变量

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

# Database
DATABASE_URL=postgresql+psycopg://...

# Redis
REDIS_URL=redis://...

# Security
SECRET_KEY=...
TENANT_SECRET_KEY=...
TRACKING_SIGNING_KEY=...
UNSUBSCRIBE_SIGNING_KEY=...
INBOUND_TOKEN_KEY=...

# Session
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=Lax

# Operations
LOG_FORMAT=json
LOG_LEVEL=INFO
ERROR_TRACKING_DSN=
RELEASE_SHA=
BACKUP_STORAGE_URL=
```

---

## 附录 B：内部模式与商业模式能力矩阵

| Capability | Internal | Commercial |
|---|---:|---:|
| Invite-only accounts | 开启 | 可选 |
| Public signup | 关闭 | 开启 |
| Single organization UX | 开启 | 关闭 |
| Multi-tenant data model | 保留 | 使用 |
| Billing | 关闭 | 开启 |
| Payment webhooks | 关闭 | 开启 |
| Coupons | 关闭 | 可选 |
| Trial | 关闭 | 可选 |
| Plan limits | 关闭 | 开启 |
| Inbound API | 按需 | 客户级配置 |
| Outreach limits | 内部安全限额 | 套餐和信誉限额 |
| Admin console | 内部运维 | 客服/平台运维 |
| SSO | 延后 | 企业套餐 |
| SLA | 无 | 定义 |
| Compliance program | 基础安全 | 正式合规 |
| HA/Autoscaling | 延后 | 按规模实施 |

---

## 附录 C：交给 AI 的首批任务建议

第一批只下发以下任务，不要同时并行修改相同模块：

1. `INT-001`：Deployment Profile 和 Capability Service；
2. `INT-002`：禁用公众注册、Billing 和 Payment Webhook；
3. `INT-101`：管理员 session revocation；
4. `INT-102`：Inbound 精确邮箱查找；
5. `INT-003`：停用 `batch_advance` 合成 PASS；
6. `INT-201`：PostgreSQL 共享部署设计和实现；
7. `INT-205`：备份恢复 Runbook。

建议由不同 AI 分支实施，由独立 Codex/人工 Reviewer 交叉复审。
