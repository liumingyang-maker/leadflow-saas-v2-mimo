# LeadFlow SaaS V2 — RC2 验收材料

请作为资深软件工程师和安全审查员，审查以下代码变更。这是 LeadFlow SaaS V2 从 v1.0.0-rc1 到 v1.0.0 的收尾工作。

## 项目背景

- **技术栈**: Python 3.12, Flask, SQLAlchemy 2, Alembic, Redis/RQ, Jinja2, HTMX, Tabler/Bootstrap 5
- **架构**: 模块化单体 SaaS，多租户隔离
- **当前状态**: 6个里程碑已合并，273+测试通过，处于 rc1 阶段

## 本次变更概要（30个文件，+3442行，-63行）

### 1. 安全加固

**Dockerfile** — 添加非root用户:
```dockerfile
RUN groupadd -r leadflow && useradd -r -g leadflow -d /app -s /sbin/nologin leadflow
RUN mkdir -p /data && chown -R leadflow:leadflow /app /data
USER leadflow
```

**app/core/security.py** — 添加 CSP 基线头:
```python
"Content-Security-Policy": (
    "default-src 'self'; script-src 'self' 'unsafe-inline';"
    " style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
    " font-src 'self'; connect-src 'self'; frame-ancestors 'none'"
),
```

**app/config.py** — 生产配置验证（已有，新增测试确认）:
- 生产环境拒绝缺失/弱 SECRET_KEY
- 生产环境拒绝缺失/弱 TENANT_SECRET_KEY
- 错误信息不泄露密钥值

### 2. 真实 Provider 适配器

**app/modules/outreach/mailer.py** — 新增 SmtpMailer:
```python
class SmtpMailer:
    def __init__(self, *, host, port, user, password, from_email, use_tls=True):
        ...
    def send(self, *, to_email, subject, body_text, body_html) -> MailerResult:
        # 使用 smtplib.SMTP + STARTTLS
        # 错误处理不泄露凭据
```

**app/integrations/collection/adapters.py** — 新增 GoogleSearchAdapter 和 GoogleMapsAdapter:
- GoogleSearchAdapter: 使用 Custom Search JSON API
- GoogleMapsAdapter: 使用 Places API Text Search
- 两者都有：输入验证、速率限制感知、安全错误处理、API key 不泄露

**app/modules/jobs/worker.py** — 适配器注册重构:
- 环境变量驱动选择：有 API key 用真实适配器，否则用 Fake/NotConfigured
- 支持 csv_import/xlsx_import

### 3. 运维工具

**scripts/backup.py** — 备份脚本:
- SQLite: 文件复制 + 验证
- PostgreSQL: pg_dump
- 时间戳命名，dry-run 模式

**scripts/restore.py** — 恢复脚本:
- SQLite: 文件替换 + 恢复前备份
- PostgreSQL: psql
- dry-run 模式

**scripts/migration_rollback.py** — 迁移回滚:
- upgrade → downgrade → upgrade 循环
- SQLite 备份/恢复
- dry-run 模式

**scripts/staging_smoke.py** — Staging 冒烟测试:
- 健康端点检查
- 数据库连接验证
- 登录页面可访问性
- 安全头验证

**scripts/release.py** — 发布脚本:
- 质量门禁验证
- 创建 release 分支
- 生成发布笔记
- 创建 git tag

**scripts/rollback.py** — 回滚脚本:
- 备份当前数据库
- checkout 指定版本
- 数据库降级
- 重启服务
- 健康检查验证

### 4. Docker 加固

**docker-compose.staging.yml** — 新建:
- PostgreSQL 替代 SQLite
- Redis 持久化
- 环境变量引用密钥（无硬编码）
- 所有服务有 healthcheck 和 restart policy

### 5. 治理文档

- docs/AGENT_ALLOCATION_V3.md — 三方角色映射
- docs/ROLE_MATRIX_V3.md — 责任矩阵
- docs/REMAINING_WORK_V3.md — 12张任务卡
- docs/V1.0.0_RELEASE_EVIDENCE.md — 发布证据

### 6. 测试（新增 ~100 个测试）

- test_production_config.py — 7个测试
- test_security_hardening.py — 6个测试
- test_docker_hardening.py — 11个测试
- test_smtp_adapter.py — 8个测试
- test_google_adapters.py — 9个测试
- test_migration_rollback.py — 9个测试
- test_backup_restore.py — 10个测试
- test_staging_smoke.py — 8个测试
- test_acceptance_matrix.py — 23个测试
- test_release_rollback.py — 12个测试

## 验收清单

请检查以下方面：

### 安全
- [ ] CSP 策略是否合理？是否太宽松？
- [ ] SMTP 适配器是否有凭据泄露风险？
- [ ] Google API 适配器是否有 SSRF 风险？
- [ ] API key 是否在错误消息中泄露？
- [ ] 非 root Docker 用户是否正确配置？
- [ ] 生产配置验证是否足够严格？

### 架构
- [ ] 适配器注册逻辑是否合理？
- [ ] 环境变量驱动选择是否有边界情况？
- [ ] Fake → Real 适配器切换是否平滑？
- [ ] 是否有循环依赖风险？

### 代码质量
- [ ] 错误处理是否一致？
- [ ] 是否有未处理的异常？
- [ ] 类型注解是否完整？
- [ ] 是否有代码重复？

### 测试
- [ ] 测试覆盖是否充分？
- [ ] 是否有遗漏的边界情况？
- [ ] 测试是否独立（不依赖外部状态）？
- [ ] Mock/Stub 是否合理？

### 运维
- [ ] 备份脚本是否可靠？
- [ ] 回滚脚本是否安全？
- [ ] Staging 冒烟测试是否覆盖关键路径？
- [ ] 发布脚本是否有防护措施？

## 请输出

1. **总体评价**: PASS / FAIL / CONDITIONAL_PASS
2. **发现的问题**: 按严重程度排列（Critical / High / Medium / Low）
3. **建议改进**: 具体的代码修改建议
4. **安全审查结论**: 是否有安全漏洞
5. **架构审查结论**: 是否符合模块化单体架构原则
