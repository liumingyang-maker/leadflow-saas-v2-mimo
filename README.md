# LeadFlow SaaS V2 - MiMo 版本

> **由 Xiaomi MiMo (mimo-v2.5-pro) 实现**

B2B 外贸获客与 CRM SaaS 系统，面向中国外贸中小企业。

## 技术栈

- **后端**: Python 3.12, Flask (Application Factory), SQLAlchemy 2, Alembic, Redis + RQ
- **前端**: Jinja2 + HTMX + Tabler/Bootstrap 5, Alpine.js
- **测试**: pytest, Playwright E2E
- **部署**: Docker, docker-compose

## 架构

模块化单体架构：

- `app/modules/` — 领域模块 (accounts, leads, jobs, outreach, inbound, audit, admin, settings)
- `app/core/` — 基础设施 (health, security, request_id, errors, pages, proxy, design_system)
- `app/integrations/` — 外部集成适配器

## 功能模块

- **Leads**: 线索收集、导入、标签、活动记录
- **CRM Pipeline**: 销售管道管理
- **Outreach**: 外联邮件发送、追踪、退订
- **Inbound**: 入站线索接收、CORS、速率限制
- **Jobs**: 后台任务队列 (RQ/Redis)
- **Audit**: 审计日志
- **Admin**: 管理后台
- **Settings**: 租户配置

## 快速开始

```bash
# 复制配置
cp config/autopilot.example.json config/autopilot.json

# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python tools/autopilot.py init

# 运行测试
pytest

# 启动应用
flask run
```

## 项目状态

- **版本**: v1.0.0-rc1
- **测试**: 273+ pytest 测试通过
- **里程碑**: 6 个里程碑已合并

## 治理

本项目采用三方治理架构：

- **Qingyan (GLM)** — 控制器/架构师/发布经理
- **MiMo** — 实现工人
- **DeepSeek** — 审查员

详见 [AGENTS.md](AGENTS.md) 和 [MASTER_AUTOPILOT_PROMPT.md](MASTER_AUTOPILOT_PROMPT.md)。

## 许可

私有项目
