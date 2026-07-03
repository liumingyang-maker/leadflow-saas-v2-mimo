# v1.1.0-alpha.5 Target Customer Discovery Implementation Plan

## 1. Product Objective

v1.1.0-alpha.4 让用户完成“训练你的 AI 外贸员”，并确认 tenant 级产品记忆。
alpha.5 的目标是进入下一步：

> AI 已经理解你卖什么，下一步要帮你理解应该卖给谁。

alpha.5 应建立第一版“AI 找客户”体验，但不能过度承诺真实全球买家数据库，也不能一次性建设复杂多渠道获客系统。它应该让用户看到：

- 适合的买家类型
- 适合的国家/地区
- 可用搜索关键词
- 首批目标客户候选长什么样
- 未来一次匹配会消耗多少目标客户额度

alpha.5 的重点是产品体验和数据契约，而不是大规模自动抓取。

## 2. User Flow

### With Confirmed Product Profile

```text
用户已有 confirmed product profile
→ 打开 寻找客户 /collection
→ 页面展示产品记忆摘要
→ AI 展示推荐买家画像、国家、行业、关键词
→ 用户可选择基础筛选条件
→ 用户点击“匹配 10 个目标客户”
→ 系统生成示例/搜索候选客户
→ 用户审核候选客户
→ 用户选择候选客户
→ 用户显式点击“加入 CRM”
→ 系统创建 Company / Lead
→ 用户进入 CRM 跟进
```

### Without Confirmed Product Profile

```text
用户没有 confirmed product profile
→ 打开 /collection
→ 显示空状态：请先训练你的 AI 外贸员
→ 链接到 /onboarding/product-profile
→ 不调用 provider
→ 不扣 credits
```

## 3. Routes / Page Strategy

### Recommendation

优先复用现有 `/collection` 页面作为“寻找客户”入口。

理由：

- 生产导航已经把“寻找客户”指向 `/collection`。
- beta.7 曾经出现 `/collect`、`/crm` 路由回归，新增顶层 `/target-customers` 会增加导航分裂风险。
- 当前 collection 模块已经承载 Google Search、Google Maps、collection job 概念。
- alpha.5 可以在 `/collection` 页面上增加一个 product-profile-powered 的 AI 找客户 section，不必重写 collection 模块。

### Proposed Routes

Recommended least-disruptive route set:

```text
GET  /collection
POST /collection/target-plan
POST /collection/target-match
POST /collection/candidates/<candidate_id>/add-to-crm
```

Behavior:

- `GET /collection`
  - shows existing collection workspace
  - adds AI target customer discovery panel
  - if no confirmed product profile, shows train AI prompt

- `POST /collection/target-plan`
  - generates or refreshes target customer plan from confirmed product memory
  - writes ledger
  - stores run metadata if discovery run table is adopted

- `POST /collection/target-match`
  - creates first batch candidates from fake/example mode, or safe existing search adapter if explicitly configured
  - alpha.5 should not require real external search
  - writes ledger

- `POST /collection/candidates/<candidate_id>/add-to-crm`
  - requires explicit user action
  - creates/links Company and Lead
  - does not send email
  - does not create OutreachMessage

Optional future route:

```text
GET /target-customers
```

This should wait until the product navigation is intentionally renamed from “寻找客户 / Collection” to a dedicated “目标客户” module.

## 4. Data Model

### Options Considered

#### Option A: No New Table

Generate plan and candidates on demand, then post selected candidate payload directly to CRM.

Pros:

- lowest complexity
- no migration

Cons:

- harder to audit candidate generation
- harder to prevent tampering unless signed payloads are added
- difficult to show candidate history
- awkward for “review before add to CRM”

#### Option B: `target_customer_discovery_runs`

Store run metadata, filters, generated plan, status, requested count, generated count, and credits.

Pros:

- useful audit trail
- ties provider/ledger behavior to a user-visible run
- simple tenant isolation

Cons:

- does not by itself support per-candidate review/add actions

#### Option C: `target_customer_candidates`

Store candidates before user adds them to CRM.

Pros:

- supports explicit candidate review
- gives stable `candidate_id`
- allows `added_lead_id`
- enables duplicate handling and status tracking

Cons:

- one more table
- must avoid storing private scraped data or raw provider output

### Recommended Alpha.5 Model

Use two lightweight tables:

1. `target_customer_discovery_runs`
2. `target_customer_candidates`

This is still small and avoids rewriting the lead pipeline. The candidate table is justified because alpha.5 includes “user reviews candidates” and “add selected candidates to CRM”.

### `target_customer_discovery_runs`

Fields:

```text
id
tenant_id
product_profile_id
filters_json
generated_plan_json
status
requested_count
generated_count
credits_estimated
credits_charged
created_at
updated_at
```

Status values:

```text
draft
planned
matched
failed
```

Notes:

- `generated_plan_json` stores parsed, structured, whitelisted plan fields only.
- Do not store full prompt.
- Do not store full provider response.
- Tenant scoped.

### `target_customer_candidates`

Fields:

```text
id
tenant_id
run_id
company_name
website
country
industry
buyer_type
source_channel
match_reason
confidence_score
raw_data_json
added_lead_id
status
created_at
updated_at
```

Status values:

```text
pending_review
added_to_crm
dismissed
duplicate
failed
```

Notes:

- `raw_data_json` must be sanitized summary data, not raw scraped pages.
- Do not store unverifiable private emails or private phone numbers in alpha.5.
- `added_lead_id` links candidate to existing `leads.id` after explicit CRM add.

## 5. Target Customer Plan JSON

`target_customer_plan_generation` should parse product memory and return structured JSON:

```json
{
  "ideal_buyer_types": [],
  "target_industries": [],
  "recommended_countries": [],
  "search_keywords": [],
  "negative_keywords": [],
  "channel_recommendations": [],
  "buyer_pain_points": [],
  "match_scoring_rules": [],
  "first_batch_strategy": "",
  "disqualification_rules": []
}
```

Rules:

- Generate from `tenant_product_profiles.extracted_profile_json`.
- Do not invent factual buyer data.
- Treat output as strategy, not verified data.
- Store only parsed structured JSON.
- Missing values should become empty arrays or `"unknown"`.

## 6. Candidate JSON / Display Fields

Candidate card fields:

```text
company name
country/region
website
industry
buyer type
source channel
match reason
confidence / fit score
suggested next action
```

Do not show:

- unverifiable private emails
- unverifiable private phone numbers
- scraped personal data
- false certainty such as “verified buyer” unless verified by a real source

Candidate labels:

```text
示例客户
搜索候选
待确认客户
```

## 7. AI and Provider Architecture

All AI work must use the existing AI Control Plane:

```text
app/modules/ai/service.py
app/integrations/ai/*
tenant AI gating
quota / ledger
```

Feature names:

```text
target_customer_plan_generation
target_customer_candidate_matching
```

Rules:

- global AI disabled: no provider call
- tenant AI disabled: no provider call
- provider missing: no provider call
- failure: failed ledger, charge 0
- success: success ledger
- alpha.5 plan generation: 0 credits
- alpha.5 fake/example candidate matching: 0 credits but ledger
- future real candidate matching: 1 target customer = 1 credit
- no full prompt stored
- no full response stored
- no full reasoning_content stored
- no provider/base_url/api_key exposed to tenants

## 8. Credits Design

### Frontend Wording

Prefer user-friendly wording:

```text
赠送 10 个目标客户
本次预计消耗 10 个目标客户额度
深度背调和开发信后续单独扣额度
```

### Backend Mapping

```text
target customer candidate: 1 credit each in future
target customer plan generation: 0 credits
alpha.5 fake/example matching: 0 credits but ledger
alpha.6 real search matching: likely charge credits
```

### Why Alpha.5 Can Stay 0 Credits

- alpha.5 validates UX and matching quality first
- fake/example candidates should not consume paid credits
- real search cost and quality need alpha.6 validation
- ledger still records every action for future billing audit

## 9. Filters

### Alpha.5 First Filter Set

```text
country/region
buyer type
industry
result count
```

Default:

```text
global / all countries
10 candidates
no advanced filter required
```

### Future Advanced Filters

```text
company size
importer / distributor / wholesaler / brand / retailer
OEM / ODM fit
B2B / B2C
certification requirements
price positioning
```

## 10. Acquisition Channels

### Alpha.5

Allowed:

```text
fake/example provider
existing Google Search adapter if explicitly configured and safe
CSV import remains available
manual add remains available
```

Recommendation:

- Start alpha.5 with fake/example candidates.
- Allow existing Google Search adapter only behind explicit provider configuration.
- Do not require new external channel credentials.

### Future

```text
maps
B2B directories
trade fair directories
customs data
public/social data
```

Do not implement new channels in alpha.5.

## 11. CRM Integration

Selected candidates become existing CRM records only after explicit user action.

### Mapping to Existing Models

Current `Company` fields can receive:

```text
tenant_id       ← current tenant
name            ← candidate.company_name
domain          ← parsed domain from candidate.website, if available
industry        ← candidate.industry
country         ← candidate.country
notes           ← match reason + source channel summary
```

Current `Lead` fields can receive:

```text
tenant_id          ← current tenant
company_id         ← created or matched company
website            ← candidate.website
industry           ← candidate.industry
source             ← "collection"
status             ← "pending_review"
stage              ← "new"
confidence_score   ← candidate.confidence_score
notes              ← match reason + suggested next action
```

Important constraints:

- `Lead.source` currently allows only `manual/import/collection/inbound/api`; use `collection`.
- No OutreachMessage is created.
- No email is sent.
- Candidate duplicate handling should check tenant + company domain or website before creating new company/lead.
- If duplicate is suspected, warn the user or mark candidate status `duplicate`.

## 12. UI Design

Page title:

```text
AI 帮你寻找目标客户
```

Subtitle:

```text
基于你的产品记忆，AI 会推荐适合的买家类型、搜索关键词和首批目标客户候选。
```

Sections:

1. Product memory summary
2. Recommended buyer profile
3. Filters
4. Expected credit consumption
5. Generate target customers
6. Candidate list
7. Add to CRM

Empty state:

```text
请先训练你的 AI 外贸员。
```

Candidate card:

```text
company
country
website
buyer type
match reason
source
confidence
add to CRM button
```

Copy:

```text
匹配 10 个目标客户
加入 CRM
示例客户，仅供测试
搜索候选，请审核后使用
```

UI should be added to the current collection workspace without a large homepage redesign.

## 13. i18n

Required zh-CN/en-US keys:

```text
AI helps you find target customers
Based on your product memory
Recommended buyer profile
Target countries
Buyer types
Search keywords
Match target customers
Expected cost
target customer credits
Example customers for testing
Search candidates
Add to CRM
Please train your AI foreign trade operator first
System is busy, please try again later
```

Existing i18n parity tests must remain passing.

## 14. Security / Compliance

Alpha.5 must enforce:

- no private email scraping
- no private phone scraping
- no unauthorized scraping
- no social scraping
- no website crawling unless using an already-approved existing adapter
- no guarantee of data accuracy
- user must review before CRM add
- no full prompt stored
- no full response stored
- no reasoning_content stored
- no provider/base_url/api_key exposure
- no automatic email sending
- no OutreachMessage creation

Candidate labels should be conservative:

```text
示例客户
搜索候选
待确认客户
```

Avoid:

```text
verified buyer
guaranteed purchaser
confirmed contact
```

unless backed by a verified data source in a future version.

## 15. Tests

Plan tests for:

- target customers page requires login
- no product profile shows train AI prompt
- disabled tenant cannot generate target plan
- enabled tenant can generate plan with fake provider
- plan ledger success with 0 credits
- provider failure shows system busy
- candidate generation returns cards
- adding candidate to CRM requires explicit action
- tenant isolation
- no email sending
- no OutreachMessage creation
- no full prompt/response stored
- no full reasoning_content stored
- `/ai/quota` behavior unchanged
- i18n parity
- existing onboarding product profile tests pass
- existing AI/outreach/auth/navigation tests pass

Suggested new tests:

```text
tests/test_target_customer_discovery.py
tests/test_collection_target_customers.py
```

## 16. Migration Plan

Recommended migration:

```text
migrations/versions/0013_target_customer_discovery.py
```

Tables:

```text
target_customer_discovery_runs
target_customer_candidates
```

Compatibility:

- SQLite compatible
- PostgreSQL compatible
- JSON stored as Text for SQLite compatibility
- tenant scoped indexes
- downgrade drops candidate table first, then run table
- no data migration from existing tables

If implementation review decides alpha.5 should be demo-only, it may defer candidate table creation, but that weakens explicit review/add-to-CRM traceability.

## 17. Acceptance Criteria

Alpha.5 is done when:

- confirmed product profile is required
- no product profile shows train AI prompt
- AI can generate target customer plan
- user can see buyer profile and search strategy
- user can generate first candidate list using fake/example mode
- user can add selected candidate to CRM
- duplicate candidate handling is safe
- no email is sent
- no OutreachMessage is created
- no deep research is performed
- no new external channel is required
- quota/ledger records AI actions
- no full prompt/response/reasoning_content is stored
- i18n key parity passes
- migration upgrade/downgrade works if new tables are added
- existing alpha.4 product profile tests still pass

## 18. Open Decisions

1. Should alpha.5 definitely reuse `/collection`, or should the product introduce `/target-customers` now?
   - Recommendation: reuse `/collection`.

2. Should candidate matching charge 0 or 1 credit in alpha.5?
   - Recommendation: 0 credits for fake/example candidates; ledger only.

3. Should alpha.5 use Google Search adapter or fake/example only?
   - Recommendation: fake/example by default; Google Search only if explicitly configured and already safe.

4. Should discovery runs and candidates both be stored?
   - Recommendation: yes, two lightweight tables.

5. How should duplicates be handled?
   - Recommendation: tenant + domain/website check; warn or mark candidate `duplicate`.

6. Should selected candidates become `pending_review` or `accepted` leads?
   - Recommendation: `pending_review`, because candidates are not verified buyers yet.

7. Should target customer credits be a separate display unit or reuse AI credits?
   - Recommendation: frontend says “目标客户额度”; backend may continue ledger credits.

