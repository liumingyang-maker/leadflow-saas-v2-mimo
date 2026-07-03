# v1.1.0-alpha.6 Acquisition Channel Hub and Basic AI Search Plan

## 1. Product Objective

v1.1.0-alpha.5 建立了第一版 target customer discovery foundation：

- `target_customer_discovery_runs`
- `target_customer_candidates`
- fake/example candidates
- explicit add-to-CRM
- no email
- no OutreachMessage
- no private email/phone
- no verified buyer claims

v1.1.0-alpha.6 的目标是把 `/collection` 从单一采集入口升级为可持续扩展的获客渠道中心。

用户侧概念：

> AI 外贸员可以通过不同渠道帮你找客户。当前可用：AI 普通搜索。高级渠道后续开放。

关键区别：

- **AI 普通搜索**：MiMo 帮用户生成搜索策略、搜索词、搜索链接，并解析用户粘贴的搜索结果。
- **高级自动搜索**：未来由付费搜索 API、地图、B2B 目录、展会目录、海关数据等自动获取候选公司。

MiMo 是 AI brain，不是原始数据源。alpha.6 不接入新的外部数据渠道。

## 2. User Flow

### With Confirmed Product Profile

```text
用户已有 confirmed product profile
→ 打开 /collection
→ 看到获客渠道中心
→ 选择 AI 普通搜索
→ MiMo 生成搜索策略和关键词组
→ 系统生成可点击搜索链接
→ 用户手动打开搜索链接或复制搜索词
→ 用户把搜索结果文本粘贴回系统
→ MiMo 解析粘贴内容为候选客户
→ 系统规范化和安全过滤候选客户
→ 保存到 target_customer_candidates
→ 用户审核候选客户
→ 用户显式加入 CRM
```

### Without Confirmed Product Profile

```text
用户没有 confirmed product profile
→ /collection 显示“请先训练你的 AI 外贸员”
→ 链接到 /onboarding/product-profile
→ 不调用 provider
→ 不写 AI success ledger
→ 不扣 credits
```

### With AI Disabled

```text
global AI disabled 或 tenant AI disabled
→ 不调用 provider
→ 显示友好提示
→ 写 disabled ledger
→ 不扣 credits
```

## 3. Route / Page Strategy

### Recommendation

继续复用 `/collection`，不要新增顶层 `/target-customers`。

理由：

- `/collection` 已经是生产导航里的“寻找客户”入口。
- alpha.5 已经把 target discovery 放入 `/collection`。
- alpha.6 的核心是让 `/collection` 成为 acquisition hub，而不是增加新导航层级。
- 避免重复 beta.7 的路由/导航回归风险。

### Proposed Routes

Recommended least-disruptive route set:

```text
GET  /collection
POST /collection/channels/basic-search/strategy
POST /collection/channels/basic-search/parse-results
POST /collection/channels/basic-search/save-candidates
```

Keep existing alpha.5 routes:

```text
POST /collection/target-plan
POST /collection/target-match
POST /collection/candidates/<candidate_id>/add-to-crm
```

Implementation recommendation:

- Keep alpha.5 routes working.
- Add basic-search routes for clearer channel semantics.
- Internally, these routes can reuse the same discovery run and candidate service layer.
- Do not create separate pages for placeholder channels.

## 4. Channel Registry Architecture

alpha.6 should introduce a small static/config-driven channel registry, not a DB-backed registry.

Suggested structure:

```text
app/integrations/acquisition/
  __init__.py
  base.py
  registry.py
  basic_ai_search.py
  fake.py
```

Future folders can be planned but not implemented:

```text
app/integrations/acquisition/search_api/
app/integrations/acquisition/maps/
app/integrations/acquisition/directories/
app/integrations/acquisition/customs/
app/integrations/acquisition/contact_enrichment/
app/integrations/acquisition/social/
```

### Channel Metadata

Each channel entry should define:

```text
channel_key
channel_name
status
tier
description
requires_api_key
requires_paid_api
enabled
planned_version
risk_level
compliance_note
```

Status values:

```text
enabled_basic
enabled_advanced
requires_config
coming_soon
planned
disabled
```

Tier values:

```text
basic
advanced
premium
planned
```

alpha.6 should not create an acquisition channel database table. A static registry is enough and easier to review.

## 5. Data Model Strategy

Recommendation: no new migration in alpha.6.

Reuse alpha.5 tables:

```text
target_customer_discovery_runs
target_customer_candidates
```

Store channel-specific information in existing fields:

```text
filters_json
generated_plan_json
raw_data_json
source_channel
```

For AI 普通搜索:

```text
source_channel = basic_ai_search
source_channel = pasted_search_results
source_channel = manual_search
```

Why no migration:

- alpha.5 candidate foundation is sufficient.
- alpha.6 does not need a new persisted channel registry.
- production SQLite Alembic has shown sensitivity in alpha.2/alpha.4.
- Avoiding migration reduces deployment risk.

If implementation review finds a missing field, prefer using sanitized JSON fields first. Only add migration if there is a clear persistence requirement that cannot be safely represented in existing tables.

## 6. Basic AI Search Algorithm

### Input

Use:

- confirmed tenant product profile
- target country/region filter
- buyer type filter
- industry filter
- result count

### Step 1: Generate Search Strategy

Feature name:

```text
basic_search_strategy_generation
```

Output:

```text
buyer types
target countries
search keywords
negative keywords
query templates
query rationale
match scoring hints
```

### Step 2: Generate Clickable Search Links

No external API call.

Generate links for:

```text
Google
Bing
optional country-specific query
optional site:directory query
```

Allowed:

- generating URLs
- showing links
- letting user manually open links

Not allowed:

- fetching search links
- hidden requests to search engines
- automatic scraping

### Step 3: User Pastes Search Results

Accept pasted text:

```text
titles
snippets
URLs
company names
copied search result text
CSV-like textarea content
```

Limit pasted text length server-side.

### Step 4: MiMo Parses Pasted Results

Feature name:

```text
pasted_search_result_parsing
```

Output candidate JSON:

```text
company_name
website
country
industry
buyer_type
source_channel
match_reason
confidence_score
suggested_next_action
```

### Step 5: Rule + AI Scoring

Use simple rule score factors:

```text
product keyword match
buyer type match
industry match
country match
website/domain quality
source reliability
AI match reason
```

Penalty factors:

```text
obvious supplier
news/blog/directory-only page
competitor/factory
insufficient info
duplicate domain
```

Feature name:

```text
candidate_fit_scoring
```

For alpha.6 this can be a simple service helper plus AI-provided match reason. Do not build a complex ranking engine.

### Step 6: Save Candidates

Use `target_customer_candidates`.

User must review before add-to-CRM.

## 7. AI Service Integration

All AI calls must use the current AI Control Plane:

```text
app/modules/ai/service.py
app/integrations/ai/*
tenant AI gating
quota / ledger
```

Feature names:

```text
basic_search_strategy_generation
pasted_search_result_parsing
candidate_fit_scoring
```

Rules:

- global AI disabled: no provider call
- tenant AI disabled: no provider call
- provider missing: no provider call
- failure: failed ledger, charge 0
- success: success ledger
- alpha.6 basic search: 0 credits for test stage, but must write ledger
- no full prompt stored
- no full response stored
- no reasoning_content stored
- no provider/base_url/api_key exposed

Future official credits:

```text
strategy generation: 1 credit
parse up to 10 search results: 3 credits
candidate saved: 1 credit each
advanced paid API search: 2-3 credits per candidate
```

### Model Policy

Do not implement complex model routing in alpha.6 unless it is already trivial.

Recommended future model use:

```text
mimo-v2.5      normal strategy and parse tasks
mimo-v2.5-pro  complex scoring and deep research
mimo-v2.5-asr  future voice product input
mimo-v2.5-tts  future AI 外贸员 voice/report features
```

## 8. Channel Hub UI

Design `/collection` as the acquisition channel hub.

### Available Channels

1. AI 普通搜索
   - Status: 可用
   - Description: 让 AI 外贸员根据你的产品，生成海外买家搜索词、搜索链接，并帮你整理搜索结果。

2. CSV 导入
   - Status: 可用 / 已有
   - Description: 导入展会名单、老客户名单或自己整理的公司表。

3. 手动添加
   - Status: 可用 / 已有
   - Description: 手动添加你已经知道的公司。

### Future / Placeholder Channels

4. 自动网页搜索
   - Status: 高级渠道，后续开放
   - Description: 系统自动调用搜索 API 获取候选公司。

5. 地图商家
   - Status: 即将开放
   - Description: 适合寻找本地经销商、批发商、门店和服务商。

6. B2B 目录
   - Status: 规划中
   - Description: 面向 Europages、Kompass、Thomasnet 等目录。

7. 展会目录
   - Status: 规划中
   - Description: 发现行业展会和参展商名单中的潜在客户。

8. 海关数据
   - Status: 高级渠道，规划中
   - Description: 发现有进口记录的买家，后续接入合规数据源。

9. 联系方式补充
   - Status: 高级渠道，后续开放
   - Description: 为已审核公司补充公开联系方式，单独扣额度。

10. 社媒公开资料
    - Status: 规划中
    - Description: 谨慎接入公开资料，不做未授权抓取。

UI rules:

- placeholder channels must not be executable as real actions
- disabled/future cards can show detail text or waitlist copy
- no paid API secrets in UI
- no false claims that channels are active
- keep `/collection` maintainable and not cluttered
- use existing Signal Workspace panels/cards, not a homepage redesign

## 9. Basic Search UI

Add AI 普通搜索 panel inside `/collection`.

Sections:

1. Product memory summary
2. Search strategy
3. Generated search keywords
4. Generated search links
5. Paste search results
6. Parse into candidates
7. Candidate review list
8. Add to CRM

Copy:

```text
AI 普通搜索
生成搜索策略
复制搜索词
打开搜索链接
粘贴搜索结果
整理为候选客户
测试阶段不扣额度
AI 结果可能不准确，请审核后使用
```

Textarea:

- user can paste search result text
- server-side input length limit required

Not allowed:

- automatic website fetch
- hidden requests to search engines
- scraping
- treating email/phone-like text as trusted contact data

## 10. Candidate Normalization and Safety

Allowed fields:

```text
company_name
website
country
industry
buyer_type
source_channel
match_reason
confidence_score
suggested_next_action
```

Remove or ignore:

```text
personal emails
private phone numbers
contact names unless user supplied and clearly public
social profile URLs if risky
claims of verified buyer
claims of purchase intent
```

Normalize:

```text
domain from website
company name trim
confidence_score 0-100
source_channel = basic_ai_search or pasted_search_results
```

Dedupe:

```text
tenant + domain
tenant + normalized company name
existing leads/companies
existing candidates
```

Duplicates should be marked duplicate or warned.

## 11. Credits

Alpha.6 test stage:

```text
strategy generation: 0 credits + ledger
pasted result parsing: 0 credits + ledger
candidate saving: 0 credits
add-to-CRM: 0 credits
```

Future:

```text
strategy generation: 1 credit
parse up to 10 results: 3 credits
saved candidate: 1 credit each
advanced paid API search: 2-3 credits per candidate
```

Frontend:

```text
测试阶段不扣额度
未来预计消耗目标客户额度
```

Avoid confusing users: if alpha.6 charges 0, say so clearly.

## 12. i18n

Required zh-CN/en-US keys:

```text
Acquisition channels
AI basic search
Available
Advanced channel
Coming soon
Planned
Generate search strategy
Search keywords
Search links
Paste search results
Parse into candidates
Open search link
Copy keyword
Basic search does not automatically crawl websites
Test phase does not charge credits
Advanced automatic search
Map businesses
B2B directories
Trade fair directories
Customs data
Contact enrichment
Social public profiles
Please review AI results before use
```

Existing i18n parity tests must remain passing.

## 13. Security / Compliance

Alpha.6 must enforce:

- no automatic search API calls
- no website crawling
- no social scraping
- no B2B crawling
- no customs data access
- no email/phone enrichment
- no automatic email
- no OutreachMessage
- no full prompt stored
- no full response stored
- no reasoning_content stored
- no provider/base_url/api_key exposure
- user-provided pasted data only
- user review required
- candidate data labeled as unverified
- no private contact data extraction as trusted fields

## 14. Tests

Plan tests:

- `/collection` requires login
- channel hub displays available/basic/future channels
- placeholder channels are not executable
- no product profile shows train AI prompt
- disabled tenant cannot generate strategy
- enabled tenant can generate basic search strategy with fake provider
- strategy ledger success with 0 credits
- generated search links do not fetch URLs
- pasted search result parsing works with fake provider
- parser strips/ignores email/phone-like data
- candidates saved as unverified
- duplicate domain/company handled
- add-to-CRM still explicit
- no OutreachMessage
- no email sending
- no website crawling
- no new external API dependency
- i18n parity
- existing alpha.4 product profile tests pass
- existing alpha.5 target discovery tests pass
- existing AI/outreach/auth/navigation tests pass

Suggested new tests:

```text
tests/test_acquisition_channel_hub.py
tests/test_basic_ai_search.py
```

## 15. Acceptance Criteria

Alpha.6 is done when:

- `/collection` shows acquisition channel hub
- only AI 普通搜索 is active among new channels
- future paid API channels are shown as future/advanced/planned
- AI can generate search strategy from product memory
- AI can generate search keywords and search links
- system does not fetch search links
- user can paste search results
- AI parses pasted results into candidates
- candidates are sanitized and tenant-isolated
- duplicates are handled
- user can add candidates to CRM
- ledger records AI actions
- no full prompt/response/reasoning_content stored
- no website crawling
- no private email/phone extraction
- tests pass

## 16. Open Decisions

1. Does alpha.6 need any migration?
   - Recommendation: no. Reuse alpha.5 tables.

2. Exact route names for basic search?
   - Recommendation:
     - `POST /collection/channels/basic-search/strategy`
     - `POST /collection/channels/basic-search/parse-results`
     - `POST /collection/channels/basic-search/save-candidates`

3. Create acquisition registry now or static helper only?
   - Recommendation: create static registry module, no DB table.

4. Should CSV/manual cards link to existing pages?
   - Recommendation: CSV links to existing import; manual links to existing manual lead creation if present, otherwise show available/manual guidance.

5. Charge credits in alpha.6?
   - Recommendation: 0 credits for test stage, ledger only.

6. Store parsed pasted results in run `raw_data_json`?
   - Recommendation: no new field. Store sanitized parsed candidates in `target_customer_candidates.raw_data_json`.

7. How much pasted text to allow?
   - Recommendation: server-side max 10,000 characters in alpha.6.

8. Do future advanced channels need an admin config table?
   - Recommendation: likely yes later, but not in alpha.6.

