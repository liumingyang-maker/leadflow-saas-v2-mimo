# LeadFlow SaaS V2 - AI 交接文档

**日期**: 2026-06-30  
**交接人**: MiMoCode  
**任务**: DeepSeek 审查集成 + 项目继续开发  
**状态**: DeepSeek 集成已完成，可直接使用

---

## 一、项目概述

**LeadFlow SaaS V2** 是一个外贸中小企业CRM系统，核心功能：
- 寻找潜在客户 (Google Search/Maps)
- 整理线索 (导入、清洗、去重)
- 跟进触达 (邮件)
- 接收询盘 (Inbound API)

### 技术栈
- **后端**: Python 3.12 + Flask + SQLAlchemy 2 + Alembic + PostgreSQL + Redis/RQ
- **前端**: Jinja + HTMX + Alpine.js + Tabler/Bootstrap 5
- **工具**: pytest + Ruff + mypy + Playwright + Docker

---

## 二、自动化架构（重要）

这个项目使用 **三模型协作** 的自动化开发流水线：

```
┌─────────────────────────────────────────────────────────────┐
│                    LeadFlow V2 Autopilot                     │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐     ┌──────────────┐     ┌──────────────┐     │
│  │  GLM     │────▶│    User      │────▶│   MiMoCode   │     │
│  │ (外部)   │     │  (手动转发)  │     │  Controller  │     │
│  └──────────┘     └──────────────┘     └──────┬───────┘     │
│                                               │              │
│                           ┌───────────────────┼──────────┐   │
│                           ▼                   ▼          │   │
│                    ┌──────────────┐    ┌──────────────┐   │   │
│                    │   DeepSeek   │    │    MiMo      │   │   │
│                    │   Reviewer   │    │   Worker     │   │   │
│                    │  (4轮审查)   │    │  (编码实现)  │   │   │
│                    └──────────────┘    └──────────────┘   │   │
└───────────────────────────────────────────────────────────┘
```

| 角色 | 模型 | 职责 |
|------|------|------|
| Controller/Architect | MiMoCode | 架构决策、任务拆分、协调、发布 |
| Worker | MiMo | 功能代码、测试、迁移、返工 |
| Reviewer | DeepSeek | 架构/安全/UI/发布四轮审查 |
| External | GLM | 用户手动转发任务 |

---

## 三、当前进度

### 已完成

| 里程碑 | 状态 | 完成情况 |
|--------|------|----------|
| V2-01 Foundation | ✅ 已完成 | 10/10 任务 |
| V2-02 Accounts & Tenants |   进行中 | 6/10 任务 |

### V2-02 已完成任务
- V2-02-001: Tenant, user, admin and plan models
- V2-02-002: Registration, verification and login
- V2-02-003: Password reset and session rotation
- V2-02-004: Tenant isolation policies and repositories
- V2-02-005: Tenant state and plan guards
- V2-02-006: Administrator lifecycle and console foundation

### V2-02 待完成任务
- V2-02-007: Secret encryption and rotation service
- V2-02-008: CSRF, cookie and trusted proxy configuration
- V2-02-009: Account, onboarding and admin UI
- V2-02-010: Account and tenant E2E acceptance

---

## 四、DeepSeek 审查集成（已完成）

### 任务状态：✅ 已完成

### 已创建的文件

| 文件 | 状态 | 说明 |
|------|------|------|
| `.env` | ✅ 已创建 | API Key 配置 |
| `tools/deepseek_reviewer.py` | ✅ 已创建 | DeepSeek API 封装 |
| `tools/review_prompts/architecture.txt` | ✅ 已创建 | 架构审查提示词 |
| `tools/review_prompts/security.txt` | ✅ 已创建 | 安全审查提示词 |
| `tools/review_prompts/ui.txt` | ✅ 已创建 | UI审查提示词 |
| `tools/review_prompts/release.txt` | ✅ 已创建 | 发布审查提示词 |
| `tools/autopilot.py` | ✅ 已修改 | 添加 review-deepseek 命令 |
| `requirements.txt` | ✅ 已修改 | 添加 openai 依赖 |

### 需要创建的文件

#### 1. `.env` 文件
**位置**: `C:\Users\97020\Desktop\leadflow-saas-v2-main\leadflow-saas-v2-main\.env`

```env
DEEPSEEK_API_KEY=your-api-key-here
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

#### 2. `tools/deepseek_reviewer.py`
**位置**: `C:\Users\97020\Desktop\leadflow-saas-v2-main\leadflow-saas-v2-main\tools\deepseek_reviewer.py`

```python
import os
import json
from openai import OpenAI
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ReviewResult:
    round: str
    verdict: str  # PASS or FAIL
    notes: str
    issues: list[str]

class DeepSeekReviewer:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        )
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.prompts_dir = Path(__file__).parent / "review_prompts"
    
    def _load_prompt(self, round_name: str) -> str:
        return (self.prompts_dir / f"{round_name}.txt").read_text()
    
    def _call_api(self, system_prompt: str, user_content: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.1
        )
        return response.choices[0].message.content
    
    def review(self, round_name: str, diff: str, context: str, strict: bool = True) -> ReviewResult:
        prompt = self._load_prompt(round_name)
        strictness = "严格审查，任何问题都必须FAIL" if strict else "中等严格度，只关注严重问题"
        
        user_content = f"""
## 严格度
{strictness}

## 代码变更
```diff
{diff}
```

## 任务上下文
{context}

请返回JSON格式:
{{
  "verdict": "PASS或FAIL",
  "notes": "审查说明",
  "issues": ["问题1", "问题2"]
}}
"""
        
        response = self._call_api(prompt, user_content)
        result = json.loads(response)
        
        return ReviewResult(
            round=round_name,
            verdict=result["verdict"],
            notes=result["notes"],
            issues=result.get("issues", [])
        )
    
    def review_all(self, diff: str, context: str) -> dict[str, ReviewResult]:
        rounds = {
            "architecture": True,   # 严格
            "security": True,       # 严格
            "ui": False,            # 中等
            "release": True         # 严格
        }
        
        results = {}
        for round_name, strict in rounds.items():
            results[round_name] = self.review(round_name, diff, context, strict)
        
        return results
```

#### 3. `tools/review_prompts/` 目录
**位置**: `C:\Users\97020\Desktop\leadflow-saas-v2-main\leadflow-saas-v2-main\tools\review_prompts\`

创建4个文件：

**architecture.txt**
```
你是LeadFlow V2的架构审查员。审查以下代码变更是否符合架构规范。

## 架构规范
- 依赖方向: blueprint → service → repository → database
- 模块可包含: blueprint.py, models.py, repository.py, service.py, forms.py, schemas.py, policies.py, events.py
- 模板禁止直接查数据库
- 所有租户表有 tenant_id NOT NULL
- Repository 对外暴露 get_for_tenant, list_for_tenant 等明确接口
- 禁止微服务、Kubernetes、GraphQL、React/Next.js重写、Celery、隐藏全局状态和过度抽象

## 审查重点
1. 依赖方向是否正确
2. 模块边界是否清晰
3. 是否引入不必要的抽象
4. 租户隔离是否完整
5. 是否违反禁止的技术选型

返回JSON: {"verdict": "PASS/FAIL", "notes": "说明", "issues": ["问题列表"]}
```

**security.txt**
```
你是LeadFlow V2的安全审查员。审查以下代码变更是否存在安全漏洞。

## 安全规范
- Auth/Session 必须安全处理
- CSRF 保护必须完整
- 所有输入必须验证
- Secret 不能明文存储或泄露
- 所有租户数据查询必须带 tenant_id scope
- 重定向必须验证目标
- 需要 rate limiting 的端点必须有
- 错误信息不能泄露内部细节

## 审查重点
1. 认证和会话管理
2. CSRF保护
3. 输入验证和SQL注入
4. XSS防护
5. 租户隔离绕过
6. Secret泄露
7. 权限提升
8. 信息泄露

返回JSON: {"verdict": "PASS/FAIL", "notes": "说明", "issues": ["问题列表"]}
```

**ui.txt**
```
你是LeadFlow V2的UI审查员。审查以下代码变更是否符合UI规范。

## UI规范
- 色彩: Canvas #F5F7FA, Surface #FFFFFF, Primary cobalt #246BFD
- 禁止默认紫色AI渐变
- 字体: Inter或系统sans, 正文不小于14px
- 组件必须具备: default/loading/empty/error/disabled/focus状态
- 动效: 克制、快速、专业, 遵守prefers-reduced-motion
- 可访问性: WCAG 2.2 AA

## 审查重点
1. Design system一致性
2. 组件状态完整性
3. 响应式设计
4. 可访问性
5. 动效克制
6. 色彩使用

返回JSON: {"verdict": "PASS/FAIL", "notes": "说明", "issues": ["问题列表"]}
```

**release.txt**
```
你是LeadFlow V2的发布审查员。审查以下代码变更是否可以发布。

## 发布规范
- diff必须干净，无调试代码
- 测试必须覆盖新功能
- 数据库迁移必须可回滚
- CI必须通过
- 不能有secret泄露
- PR范围必须合理

## 审查重点
1. 代码质量
2. 测试覆盖
3. 迁移安全
4. 依赖变更
5. 配置变更
6. 文档更新

返回JSON: {"verdict": "PASS/FAIL", "notes": "说明", "issues": ["问题列表"]}
```

#### 4. 修改 `tools/autopilot.py`
**位置**: `C:\Users\97020\Desktop\leadflow-saas-v2-main\leadflow-saas-v2-main\tools\autopilot.py`

在 `parser()` 函数中添加新命令：

```python
def cmd_review_deepseek(args: argparse.Namespace) -> int:
    """调用 DeepSeek 进行审查"""
    from deepseek_reviewer import DeepSeekReviewer
    
    cfg = config()
    s = state()
    _, task = current_task(cfg, s)
    
    # 获取 diff
    diff_result = run(["git", "diff", "HEAD"])
    diff = diff_result.stdout
    
    # 获取任务上下文
    packet_path = STATE_DIR / "packets" / f"{task['id']}.md"
    context = packet_path.read_text() if packet_path.exists() else ""
    
    reviewer = DeepSeekReviewer()
    
    if args.round == "all":
        results = reviewer.review_all(diff, context)
        all_pass = all(r.verdict == "PASS" for r in results.values())
        
        for round_name, result in results.items():
            print(f"{round_name}: {result.verdict}")
            if result.issues:
                for issue in result.issues:
                    print(f"  - {issue}")
        
        verdict = "PASS" if all_pass else "FAIL"
        notes = "\n".join(f"{r.round}: {r.notes}" for r in results.values())
    else:
        strict = args.round in ("architecture", "security", "release")
        result = reviewer.review(args.round, diff, context, strict)
        verdict = result.verdict
        notes = result.notes
        print(f"{args.round}: {verdict}")
        if result.issues:
            for issue in result.issues:
                print(f"  - {issue}")
    
    # 记录审查结果
    review = {
        "task": task["id"],
        "verdict": verdict,
        "notes": notes,
        "reviewer": "deepseek",
        "at": now()
    }
    path = STATE_DIR / "reviews" / f"{task['id']}-deepseek-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    save_json(path, review)
    s["last_verdict"] = review
    s["phase"] = "ACCEPTED" if verdict == "PASS" else "WORKER_FIX"
    write_state(s)
    
    return 0 if verdict == "PASS" else 1
```

在 `parser()` 函数中注册命令：

```python
# 在 sub.add_parser("advance") 之后添加
ds = sub.add_parser("review-deepseek")
ds.add_argument("--round", required=True, choices=["architecture", "security", "ui", "release", "all"])
ds.set_defaults(func=cmd_review_deepseek)
```

---

## 五、项目目录结构

```
leadflow-saas-v2-main/
├── .agents/                    # Agent skills
│   ├── skill-lock.json
│   └── skills/
├── .autopilot/                 # 自动化状态
│   ├── evidence/               # 门禁证据
│   ├── packets/                # 任务包
│   ├── reviews/                # 审查记录
│   └── state.json              # 当前状态
├── app/                        # 应用代码
│   ├── __init__.py
│   ├── config.py               # 配置
│   ├── extensions.py           # Flask扩展
│   ├── core/                   # 核心模块
│   │   ├── security.py
│   │   ├── errors.py
│   │   ├── request_id.py
│   │   └── tenancy.py
│   ├── modules/                # 业务模块
│   │   ├── accounts/
│   │   ├── admin/
│   │   ├── audit/
│   │   ├── inbound/
│   │   ├── jobs/
│   │   ├── leads/
│   │   ├── outreach/
│   │   └── settings/
│   ├── integrations/           # 外部集成
│   ├── templates/              # Jinja模板
│   └── static/                 # 静态资源
├── config/                     # 配置文件
│   ├── autopilot.json          # 自动化配置
│   └── skill_sources.json
├── docs/                       # 文档
│   ├── ARCHITECTURE.md         # 架构文档
│   ├── MILESTONES.md           # 里程碑
│   ├── PRODUCT_PLAN.md         # 产品计划
│   └── UI_SYSTEM.md            # UI规范
├── migrations/                 # Alembic迁移
├── milestones/                 # 任务定义
│   ├── V2-01.json
│   ├── V2-02.json
│   └── ...
├── scripts/                    # 脚本
├── tests/                      # 测试
├── tools/                      # 工具
│   ├── autopilot.py            # 自动化工具
│   └── install_ui_skills.py
├── AGENTS.md                   # Agent治理规则
├── MASTER_AUTOPILOT_PROMPT.md  # 主控Prompt
└── README_FIRST.md             # 快速开始
```

---

## 六、关键文件说明

### 配置文件

| 文件 | 说明 |
|------|------|
| `config/autopilot.json` | 自动化配置，包含里程碑、门禁命令、Git策略 |
| `.autopilot/state.json` | 当前状态：阶段、任务索引、审查结果 |
| `AGENTS.md` | Agent角色定义、流程、规则 |
| `MASTER_AUTOPILOT_PROMPT.md` | 主控Prompt，指导Codex如何工作 |

### 里程碑文件

| 文件 | 说明 |
|------|------|
| `milestones/V2-01.json` | Foundation任务 (已完成) |
| `milestones/V2-02.json` | Accounts & Tenants任务 (进行中) |
| `milestones/V2-03.json` | Leads & CRM任务 |
| `milestones/V2-04.json` | Collection & Jobs任务 |
| `milestones/V2-05.json` | Outreach & Inbound任务 |
| `milestones/V2-06.json` | Admin & Launch任务 |

### 文档文件

| 文件 | 说明 |
|------|------|
| `docs/ARCHITECTURE.md` | 技术架构、目录结构、模块契约 |
| `docs/UI_SYSTEM.md` | UI规范、色彩、组件、动效 |
| `docs/PRODUCT_PLAN.md` | 产品功能、核心闭环 |
| `docs/AUTOMATION_WORKFLOW.md` | 自动化状态机、审查流程 |

---

## 七、执行流程

### 标准任务流程

```
READY → PLANNING → WORKER_BUILD → VERIFYING → REVIEWING
      → WORKER_FIX (循环) → ACCEPTED → PR_OPEN → CI → MERGED → DONE
```

### 命令序列

```bash
# 1. 查看当前状态
python tools/autopilot.py status

# 2. 准备任务包
python tools/autopilot.py prepare

# 3. 运行门禁
python tools/autopilot.py verify

# 4. DeepSeek审查 (新功能)
python tools/autopilot.py review-deepseek --round architecture
python tools/autopilot.py review-deepseek --round security
python tools/autopilot.py review-deepseek --round ui
python tools/autopilot.py review-deepseek --round release
python tools/autopilot.py review-deepseek --round all

# 5. 记录审查结果
python tools/autopilot.py review --verdict PASS --notes "..."

# 6. 推进到下一任务
python tools/autopilot.py advance
```

---

## 八、待完成工作

### DeepSeek 集成（已完成）

✅ 所有文件已创建，可直接使用

### 后续任务

1. **完成 V2-02** (4个任务待完成)
   - V2-02-007: Secret encryption and rotation service
   - V2-02-008: CSRF, cookie and trusted proxy configuration
   - V2-02-009: Account, onboarding and admin UI
   - V2-02-010: Account and tenant E2E acceptance

2. **V2-03**: Leads & CRM (10个任务)
3. **V2-04**: Collection & Jobs (10个任务)
4. **V2-05**: Outreach & Inbound (10个任务)
5. **V2-06**: Admin & Launch (10个任务)

---

## 九、注意事项

### 安全规则
- 禁止明文存储secret
- 所有租户查询必须带 tenant_id
- 禁止自动生产部署
- 禁止 `git add .` 或 `git add -A`

### 代码规范
- Python 3.12+
- Ruff格式化
- 类型注解
- 测试覆盖

### UI规范
- 禁止紫色AI渐变
- 组件必须有完整状态
- 遵守 WCAG 2.2 AA
- 动效克制

---

## 十、快速开始（给下一个AI）

### 第一步：安装依赖

```bash
cd C:\Users\97020\Desktop\leadflow-saas-v2-main\leadflow-saas-v2-main
pip install -r requirements.txt
```

### 第二步：查看当前状态

```bash
python tools/autopilot.py status
```

### 第三步：准备下一个任务

```bash
python tools/autopilot.py prepare
```

### 第四步：让 MiMo (Worker) 实现任务

阅读 `.autopilot/packets/V2-02-007.md` 任务包，按照要求实现代码。

### 第五步：运行门禁

```bash
python tools/autopilot.py verify
```

### 第六步：DeepSeek 审查

```bash
# 运行全部四轮审查
python tools/autopilot.py review-deepseek --round all

# 或单独运行某一轮
python tools/autopilot.py review-deepseek --round architecture
python tools/autopilot.py review-deepseek --round security
python tools/autopilot.py review-deepseek --round ui
python tools/autopilot.py review-deepseek --round release
```

### 第七步：推进到下一任务

```bash
python tools/autopilot.py advance
```

---

## 十一、联系方式

如有问题，请查阅：
- `AGENTS.md` - Agent治理规则
- `docs/` - 完整文档
- `.autopilot/state.json` - 当前状态
- `HANDOFF.md` - 本交接文档

---

**祝开发顺利！**
