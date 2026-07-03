# V1.1.0 Alpha 9 Candidate Company Research MVP Plan

## 1. Goal

v1.1.0-alpha.9 的目标是设计并实现第一版候选公司深度背调 MVP。

用户在目标客户候选列表中打开一个候选公司后，可以点击：

```text
AI 深度背调
```

系统生成结构化研究报告，帮助用户判断这个候选是否值得加入 CRM、继续人工确认，或后续生成开发信。

报告应包含：

- company summary
- why this company may be a buyer
- product fit
- buyer type
- country / region
- possible use cases
- positive signals
- risk signals
- suggested next action
- suggested outreach angle
- source links
- clear disclaimer: 未验证，需要人工确认

alpha.9 是“AI 外贸员”从找客户进入研究客户的第一步。

## 2. Why Now

当前生产状态：

- v1.1.0-alpha.8.1 已部署。
- Brave advanced web search provider works.
- App pipeline filtering/scoring PASS.
- Query generation 已转为 buyer-oriented，并带 negative operators。
- Domain blacklist 和 candidate scoring 已验证。
- Packaging / LED 适合 limited beta。
- Hardware / metal fittings 暂时 restricted 或 low-confidence。
- Provider disabled by default。
- 普通客户不受影响。

当前用户旅程：

1. 用户告诉 AI 自己卖什么。
2. Product profile 保存为 AI 外贸员产品记忆。
3. AI 生成目标客户搜索策略。
4. Advanced web search 生成候选公司。
5. 用户审核候选。
6. 下一步缺口：AI company research / 深度背调。
7. 后续再做 AI outreach email draft。

现在做 alpha.9 的原因：

- 用户看到候选公司后，需要快速判断“这家公司是否真的值得跟进”。
- 仅靠 search snippet 和 match reason 不足以建立信任。
- 深度背调是后续 AI 开发信的关键上下文。
- 当前 provider 和 ledger/gating 已经具备基础，可以在安全边界内做 MVP。

## 3. Scope

alpha.9 只做候选公司研究 MVP：

1. 候选公司 detail page。
2. “AI 深度背调”触发入口。
3. 基于已有 candidate metadata + product profile 生成结构化研究报告。
4. 可选使用 Brave Search API 获取少量额外 search snippets。
5. 保存 sanitized structured report。
6. 显示 report card。
7. 继续遵守 AI gating、tenant gating、quota、ledger。
8. 不成功不扣费。
9. alpha 阶段 `credits_charged=0`，但 ledger 记录 estimated usage。

Suggested event / feature name:

```text
candidate_company_research
```

Suggested user-facing package wording:

```text
1 次深度背调体验
```

Future production price:

```text
5 credits / report
```

Alpha behavior:

```text
credits_charged = 0
```

## 4. Out of Scope

alpha.9 明确不做：

- no website crawling
- no webpage body fetching
- no browser automation
- no LinkedIn / Facebook scraping
- no customs data
- no B2B directory scraping
- no email / phone enrichment
- no private email / phone collection
- no email sending
- no OutreachMessage creation
- no automatic outreach
- no automatic follow-up
- no new provider
- no Qwen Web Search
- no MiMo Web Search
- no SerpAPI
- no Maps / Places
- no billing automation
- no public beta enablement

## 5. User Journey

### Main Flow

1. 用户进入 `/collection`。
2. 用户看到 target customer candidates。
3. 用户点击某个 candidate。
4. 进入 candidate detail page。
5. 页面展示：
   - candidate summary
   - source URL
   - source provider
   - country
   - buyer type
   - score
   - match reason
   - unverified disclaimer
6. 用户点击 `AI 深度背调`。
7. 系统检查：
   - login
   - tenant owns candidate
   - global AI enabled / provider configured
   - tenant AI enabled
   - quota available
8. 系统使用 candidate metadata + product profile 生成 report。
9. Report 保存并显示。
10. 用户决定：
    - add to CRM
    - regenerate later
    - discard / keep reviewing

### If No Report Exists

Show CTA:

```text
AI 深度背调
```

Helper copy:

```text
AI 会根据候选公司信息和你的产品记忆，生成一份未验证的背调建议。请人工确认官网、采购需求和联系人。
```

### If Report Already Exists

Show latest report.

Allow regenerate only when:

- tenant AI enabled
- quota available
- provider available

Regeneration still follows ledger and failure no charge.

### If Candidate Has No Domain

Generate a limited report from available metadata:

- company name
- country
- buyer type
- match reason
- product profile

Set confidence low and show:

```text
该候选缺少官网，背调结果可信度较低。
```

## 6. Data Model

Add migration for:

```text
candidate_research_reports
```

Recommended fields:

- `id`
- `tenant_id`
- `candidate_id`
- `status`
- `research_type`
- `provider`
- `search_provider`
- `company_name`
- `company_domain`
- `country`
- `buyer_type`
- `fit_score`
- `confidence_score`
- `summary`
- `product_fit`
- `buyer_signals_json`
- `risk_signals_json`
- `suggested_next_action`
- `suggested_outreach_angle`
- `sources_json`
- `ai_model`
- `ai_usage_ledger_id`
- `error_code`
- `created_at`
- `updated_at`

### Status Values

```text
pending
completed
failed
```

### Research Type

```text
ai_company_research
```

### Provider Fields

`provider`:

- `fake`
- `mimo`
- `openai_compatible`

`search_provider`:

- `none`
- `fake`
- `brave`

### JSON Fields

`buyer_signals_json`:

```json
[
  {
    "signal": "Importer/distributor wording appears in source snippet",
    "source": "candidate_snippet",
    "confidence": "medium"
  }
]
```

`risk_signals_json`:

```json
[
  {
    "risk": "Could be a supplier or manufacturer",
    "source": "candidate_snippet",
    "severity": "medium"
  }
]
```

`sources_json`:

```json
[
  {
    "title": "Candidate source",
    "url": "https://example.com",
    "snippet": "Short sanitized snippet",
    "source_provider": "brave"
  }
]
```

### Do Not Store

- full prompt
- full AI response
- reasoning_content
- raw Brave response
- raw webpage text
- private email
- private phone
- private personal contact data

### SQLite / PostgreSQL Notes

- Store JSON fields as `Text` for SQLite compatibility.
- Keep report rows append-only enough for review, but alpha.9 can show latest report only.
- Do not mutate candidate schema unless absolutely necessary.
- Candidate table remains the source of candidate ownership and metadata.

## 7. AI / Provider Flow

Business logic must not call MiMo/OpenAI directly.

Required path:

```text
routes -> service layer -> app/modules/ai/service.py -> app/integrations/ai/*
```

Inputs to AI:

- candidate company name
- candidate URL/domain
- candidate country
- candidate buyer type
- candidate match reason
- candidate confidence score
- candidate sanitized raw metadata
- product profile extracted JSON
- optional sanitized Brave snippets

Prompt rules:

- Use only supplied candidate metadata, product profile, and optional source snippets.
- Do not invent verified facts.
- Do not claim procurement intent unless source snippet supports it.
- Do not output private emails or phone numbers.
- If evidence is weak, state uncertainty.
- Output strict JSON.
- Include source references by URL/snippet only.
- Include disclaimer fields.

Suggested structured AI output:

```json
{
  "summary": "",
  "why_potential_buyer": "",
  "product_fit": "",
  "buyer_type": "",
  "country_region": "",
  "possible_use_cases": [],
  "positive_signals": [],
  "risk_signals": [],
  "fit_score": 0,
  "confidence_score": 0,
  "suggested_next_action": "",
  "suggested_outreach_angle": "",
  "disclaimer": "未验证，需要人工确认"
}
```

Validation:

- Malformed JSON -> failed report + failed ledger + user-friendly error.
- Missing optional fields -> normalize to empty strings/arrays.
- Score fields clamped to 0-100.

## 8. Optional Brave Source Snippet Flow

Default research should use existing candidate metadata first.

Optional Brave flow:

1. Check acquisition provider settings.
2. Check provider enabled and configured.
3. Check test tenant/admin use only.
4. Run at most 1 to 2 Brave search queries.
5. Use company name + domain query, for example:
   - `{company_name} official website`
   - `{company_name} distributor importer`
6. Store only sanitized snippets and source URLs in `sources_json`.

Constraints:

- no website crawling
- no page body fetching
- no browser automation
- no raw Brave response stored
- no private email / phone extraction
- no automatic retry explosion
- timeout respected
- spend cap respected

If Brave is disabled:

- research still runs with candidate metadata only.
- `search_provider=none`.
- confidence may be lower.

## 9. Routes

Proposed routes:

```text
GET  /collection/candidates/<candidate_id>
POST /collection/candidates/<candidate_id>/research
GET  /collection/candidates/<candidate_id>/research
```

### GET /collection/candidates/<candidate_id>

Shows candidate detail page:

- candidate summary
- source URL
- country
- buyer type
- source channel
- provider/source metadata
- match reason
- confidence score
- latest research report if available
- AI 深度背调 CTA
- Add to CRM CTA if not already added

### POST /collection/candidates/<candidate_id>/research

Behavior:

- requires tenant login
- candidate must belong to current tenant
- checks AI gating
- checks quota
- runs AI research
- writes ledger
- saves report
- redirects to candidate detail or report view

### GET /collection/candidates/<candidate_id>/research

Shows latest report.

Can be implemented as:

- dedicated report page, or
- redirect/anchor into candidate detail page

Recommendation:

Start with candidate detail page showing latest report to avoid page sprawl.

## 10. UI

Candidate detail page sections:

1. Candidate summary
2. Source URL
3. Score / buyer type / country
4. Match reason
5. AI 深度背调 CTA
6. Report result card

Report card sections:

1. 公司概览
2. 为什么可能适合你
3. 买家类型判断
4. 产品匹配度
5. 积极信号
6. 风险/不确定点
7. 建议下一步
8. 开发信切入角度
9. 来源链接
10. 免责声明

Safety copy:

```text
未验证
建议人工确认官网、采购需求和联系人
系统不会自动发送邮件
不会保存私人邮箱/手机号为可信字段
```

Failure copy:

```text
系统繁忙，请稍后重试
```

AI disabled copy:

```text
AI 功能暂未开启
```

Quota blocked copy:

```text
额度不足
```

## 11. Credit / Ledger Behavior

Suggested feature name:

```text
candidate_company_research
```

Alpha behavior:

- `credits_estimated = 5`
- `credits_charged = 0`
- failure charges 0
- disabled tenant charges 0
- quota block charges 0
- provider failure charges 0

Future production behavior:

- 5 credits / report
- regenerate may cost 5 credits
- metadata-only research may be cheaper if desired later

Ledger statuses:

- `success`
- `failed`
- `disabled`
- `blocked_quota`

Ledger should include:

- tenant_id
- user_id
- feature_name
- provider
- model
- credits_charged
- status
- error_code
- latency_ms if available

Do not store in ledger:

- full prompt
- full response
- reasoning_content
- raw Brave response
- API key
- Authorization header

## 12. Safety / Privacy

Hard boundaries:

- no crawling
- no scraping
- no webpage body fetching
- no browser automation
- no social scraping
- no customs scraping
- no B2B directory scraping
- no email / phone enrichment
- no private personal data storage
- no email sending
- no OutreachMessage
- no verified buyer claim
- no purchase intent guarantee

Sanitization:

- strip email-like strings
- strip phone-like strings
- strip private contact-like fields
- cap field lengths
- only store source snippets, not raw provider responses

Report language:

- must say unverified
- must say manual confirmation required
- must distinguish evidence from inference

## 13. Access Control

Required:

- tenant login required
- candidate belongs to current tenant
- report belongs to current tenant
- no cross-tenant candidate/report access
- tenant AI enabled required
- global AI enabled/provider configured required
- quota required

If candidate missing:

```text
404
```

If candidate belongs to another tenant:

```text
404 or 403, following existing tenant isolation convention
```

Normal tenant users cannot see:

- provider API key
- provider base URL
- other tenant reports
- other tenant candidates

## 14. Error Handling

### AI disabled

No provider call.

User sees:

```text
AI 功能暂未开启
```

Ledger:

```text
status=disabled
credits_charged=0
```

### Quota blocked

No provider call.

User sees:

```text
额度不足
```

Ledger:

```text
status=blocked_quota
credits_charged=0
```

### Candidate missing

Return 404.

No provider call.

### Provider failure

User sees:

```text
系统繁忙，请稍后重试
```

Ledger:

```text
status=failed
credits_charged=0
error_code=<sanitized code>
```

### Malformed AI JSON

Create failed report or no report, following implementation choice.

Ledger:

```text
status=failed
error_code=malformed_response
credits_charged=0
```

### Existing report

Show latest report.

Regenerate should require explicit user action and gating.

## 15. Tests

Add tests for:

- research route requires login
- candidate detail route requires login
- tenant isolation for candidate detail
- tenant isolation for research report
- candidate missing returns 404
- AI disabled blocks provider call
- quota blocked blocks provider call
- successful research creates report
- successful research writes ledger
- failed AI provider writes failed ledger and charges 0
- malformed AI JSON handled safely
- candidate without domain can produce low-confidence report
- report displays unverified disclaimer
- no OutreachMessage created
- no email sent
- no private email stored
- no private phone stored
- no full prompt stored
- no full response stored
- no reasoning_content stored
- no raw provider response stored
- optional Brave snippet flow stores only sanitized snippets
- existing target discovery tests still pass
- existing advanced web search tests still pass
- existing AI control tests still pass
- existing outreach draft tests still pass

Suggested files:

- `tests/test_candidate_company_research.py`
- update existing i18n tests if new translation keys are added

Required validation commands:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .

PYTHONPATH=$PWD .venv/bin/python -m pytest -q \
  tests/test_candidate_company_research.py \
  tests/test_advanced_web_search_channel.py \
  tests/test_acquisition_provider_settings.py \
  tests/test_acquisition_channel_hub.py \
  tests/test_target_customer_discovery.py \
  tests/test_onboarding_product_profile.py \
  tests/test_ai_control_plane.py \
  tests/test_ai_outreach_draft.py \
  tests/test_i18n.py \
  tests/test_navigation.py \
  tests/test_resend_verification.py

PYTHONPATH=$PWD .venv/bin/python -m pytest -q -k "not playwright and not browser_acceptance"

git diff --check
```

Security grep:

```bash
grep -RInE "requests\.|httpx|urlopen|urllib.request|BeautifulSoup|selenium|playwright|scrap|crawl|customs|linkedin|facebook|whatsapp|telegram|SMTP|send_email|OutreachMessage" \
  app/integrations/acquisition app/modules/acquisition app/modules/jobs app/templates/collection app/templates/admin app/modules/ai app/integrations/ai || true

git diff | grep -iE "tp-|sk-|Authorization:|Bearer |SMTP_PASSWORD|SECRET_KEY|TENANT_SECRET_KEY|INBOUND_TOKEN_KEY|OUTREACH_SIGNING_KEY" || true
```

Allowed:

- variable names
- fake test keys
- placeholder text
- existing provider code header names without actual key values

Forbidden:

- real API key
- real Authorization header
- real SMTP password
- real secret keys

## 16. Migration / Deployment Notes

Production uses SQLite, and previous migrations sometimes required manual SQL fallback.

### Alembic Migration

Create a new migration, likely:

```text
0015_candidate_research_reports.py
```

Migration should:

- create `candidate_research_reports`
- use `Text` columns for JSON
- use simple check constraints for status where compatible
- create indexes on:
  - `tenant_id`
  - `candidate_id`
  - `status`
  - `created_at`
- add FK to `target_customer_candidates.id`
- add FK to `tenants.id`
- optionally add nullable FK to `ai_usage_ledger.id`

Downgrade:

- drop indexes
- drop table

### Local Migration Gate

Run:

```bash
rm -f /tmp/leadflow-alpha9-company-research.sqlite3

DATABASE_URL=sqlite:////tmp/leadflow-alpha9-company-research.sqlite3 \
APP_ENV=testing \
SECRET_KEY=test-secret \
TENANT_SECRET_KEY=test-tenant-secret \
INBOUND_TOKEN_KEY=test-inbound-secret \
OUTREACH_SIGNING_KEY=test-outreach-secret \
REDIS_URL=redis://127.0.0.1:6379/15 \
LOWMEM_ALLOW_SQLITE=true \
PYTHONPATH=$PWD .venv/bin/alembic upgrade head

DATABASE_URL=sqlite:////tmp/leadflow-alpha9-company-research.sqlite3 \
APP_ENV=testing \
SECRET_KEY=test-secret \
TENANT_SECRET_KEY=test-tenant-secret \
INBOUND_TOKEN_KEY=test-inbound-secret \
OUTREACH_SIGNING_KEY=test-outreach-secret \
REDIS_URL=redis://127.0.0.1:6379/15 \
LOWMEM_ALLOW_SQLITE=true \
PYTHONPATH=$PWD .venv/bin/alembic downgrade -1

DATABASE_URL=sqlite:////tmp/leadflow-alpha9-company-research.sqlite3 \
APP_ENV=testing \
SECRET_KEY=test-secret \
TENANT_SECRET_KEY=test-tenant-secret \
INBOUND_TOKEN_KEY=test-inbound-secret \
OUTREACH_SIGNING_KEY=test-outreach-secret \
REDIS_URL=redis://127.0.0.1:6379/15 \
LOWMEM_ALLOW_SQLITE=true \
PYTHONPATH=$PWD .venv/bin/alembic upgrade head
```

### Production Deploy Verification

Before deploy:

1. Backup SQLite.
2. Confirm current revision.
3. Run migration.
4. Verify table exists:

```sql
SELECT name FROM sqlite_master WHERE type='table' AND name='candidate_research_reports';
```

5. Verify app starts.
6. Verify health endpoints.
7. Run fake provider smoke.
8. Verify ordinary customers unaffected.

### Manual SQL Fallback

Prepare reviewed manual SQL before deployment in case Alembic fails on production SQLite.

Fallback SQL should:

- create `candidate_research_reports`
- create necessary indexes
- not mutate existing data

Manual SQL should only be executed after:

- backup exists
- Alembic failure is confirmed
- table absence is confirmed
- MimoCode / operator approval is given

### Rollback Plan

If app fails after migration:

1. Disable AI provider.
2. Disable acquisition provider.
3. Roll back app code.
4. Keep new table if harmless.
5. Only drop table if rollback procedure explicitly approves and no useful test reports need retention.

## 17. Acceptance Criteria

alpha.9 is done when:

- user can open candidate detail page
- user can generate company research report from a candidate
- report is structured and useful
- report includes unverified/manual confirmation disclaimer
- no email sent
- no OutreachMessage created
- no private email / phone stored
- no crawling / scraping
- no webpage body fetch
- no full prompt stored
- no full response stored
- no reasoning_content stored
- no raw provider response stored
- AI gating respected
- tenant AI gating respected
- quota respected
- ledger written
- provider failure charges 0
- quota block charges 0
- tenant isolation enforced
- candidate without domain can produce limited low-confidence report
- existing tests pass
- migration upgrade/downgrade works

## 18. Risks and Mitigations

### Risk: AI invents facts

Mitigation:

- prompt requires uncertainty
- report labels inference vs evidence
- UI says unverified
- no verified buyer claims

### Risk: Candidate source snippets are too thin

Mitigation:

- generate limited report from metadata
- lower confidence when no domain/snippet
- optional Brave snippets only when provider enabled

### Risk: Users treat report as verified due diligence

Mitigation:

- visible disclaimer
- suggested next action includes manual confirmation
- no “verified buyer” wording

### Risk: Secret leakage

Mitigation:

- no API key in report
- no raw provider response in tenant UI
- no auth headers in logs
- tests and grep checks

### Risk: SQLite migration friction

Mitigation:

- simple additive table
- local upgrade/downgrade/upgrade gate
- production table existence check
- manual SQL fallback prepared but not used without approval

### Risk: Scope creep into scraping or enrichment

Mitigation:

- no crawling
- no email / phone enrichment
- no social/B2B/customs scraping
- only source snippets from existing candidate metadata and optional official Brave API

