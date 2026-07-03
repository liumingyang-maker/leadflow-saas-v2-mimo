# v1.1.0-alpha.8 高级搜索质量评估与 Brave Live Smoke 计划

## 1. Product Objective

v1.1.0-alpha.8 不是新功能发布，而是第一个高级付费获客 API 渠道的质量、成本和安全验证里程碑。

alpha.7 已实现高级自动网页搜索渠道、Brave Search provider、`acquisition_provider_settings`、`/admin/acquisition` 和 `/collection` 渠道中心。alpha.8 的目标是用极小流量验证一个核心问题：

> Brave Search 是否能为 SOHO、小工厂、小外贸团队产生有用的目标客户候选？

本阶段要评估：

- search result quality
- candidate usefulness
- cost per useful candidate
- latency
- failure rate
- duplicate rate
- safety / compliance
- Brave 是否继续作为 primary advanced search provider
- query generation / candidate scoring 是否需要在扩大 beta 前调优

alpha.8 不新增 Maps、B2B directories、customs data、email enrichment、Company Research 或 Deep Research。

## 2. Scope

alpha.8 范围：

1. 制定 Brave Search 小流量 live smoke 方案。
2. 定义内部测试租户设置。
3. 定义 3 个测试产品画像。
4. 定义 query/result 限制。
5. 定义候选客户质量评分标准。
6. 定义成本、延迟、失败率、重复率等指标。
7. 定义 secret handling 和安全规则。
8. 定义 DB / ledger 检查。
9. 定义 PASS / NEEDS_TUNING / STOP 阈值。
10. 定义评估后的决策路径。

alpha.8 非目标：

- no new acquisition channels
- no Maps / Places
- no B2B directory integration
- no trade fair directory integration
- no customs data
- no social scraping
- no email / phone enrichment
- no deep research
- no automatic outreach
- no automatic email sending
- no public beta enablement
- no billing automation
- no real customer data testing

## 3. Test Setup

### Test Tenant

- 仅使用一个内部测试租户。
- 测试租户必须显式启用 tenant AI。
- acquisition provider 只为测试启用。
- 测试结束后关闭 provider，除非明确决定保留给内部测试租户继续使用。
- 普通客户不得访问真实 Brave provider。

### Provider

- `provider=brave`
- 使用 platform-owned Brave test key。
- key 只能通过 `/admin/acquisition` 或本机安全终端输入。
- key 不发送到 chat。
- key 不写入 `production.env`。
- UI 只显示 masked last4。
- 测试前后默认 provider disabled，除非明确决定继续内部测试。

### Limits

初始限制：

- `daily_spend_cap_cents = 100`
- `query_limit_per_run = 1`
- `result_limit_per_run = 3`
- `timeout_seconds = 10`
- no automatic retry
- no batch runs
- no ordinary customer access

如果第一轮安全且质量可评估，可扩大到：

- `query_limit_per_run = 3`
- `result_limit_per_run = 10`
- 最多 3 个测试产品画像

### Data

- 使用 fake/internal product profiles。
- 不使用真实客户数据。
- 不使用个人隐私数据。
- 不测试邮件发送。
- 不创建 OutreachMessage。

## 4. Test Product Profiles

### Profile A: Eco-Friendly Packaging Bags

Product:

- eco-friendly packaging bags
- custom packaging
- compostable / recyclable packaging

Required product memory fields:

- `product_keywords_en`: eco-friendly packaging bags, custom packaging, compostable bags
- `buyer_types`: importer, distributor, private label brand, wholesaler
- `target_countries`: US, UK, Germany
- `target_industries`: retail, food packaging, cosmetics packaging
- `search_keywords`: eco-friendly packaging importer, compostable packaging distributor

Expected search query examples:

- `eco-friendly packaging bags importer`
- `custom packaging distributor US`
- `compostable packaging private label UK`
- `recyclable packaging wholesaler Germany`

Expected good candidate type:

- packaging importer
- packaging distributor
- private label packaging brand
- wholesale packaging supplier that buys from factories

Obvious bad candidates:

- another packaging factory selling the same product
- packaging industry news/blog
- generic directory page with no company detail
- retail consumer shop with no B2B procurement signal

### Profile B: LED Lighting / Decorative Lighting

Product:

- LED lighting
- decorative lighting
- commercial / home lighting

Required product memory fields:

- `product_keywords_en`: LED lighting, decorative lighting, pendant lights
- `buyer_types`: distributor, wholesaler, retailer, contractor
- `target_countries`: US, UAE, Australia
- `target_industries`: lighting retail, interior design, electrical distribution
- `search_keywords`: LED lighting distributor, decorative lighting wholesaler

Expected search query examples:

- `LED lighting distributor US`
- `decorative lighting wholesaler UAE`
- `pendant lights retailer Australia`
- `commercial lighting contractor procurement`

Expected good candidate type:

- lighting distributor
- electrical wholesaler
- lighting showroom / retailer
- contractor procurement company

Obvious bad candidates:

- LED manufacturer competitor
- home decoration blog
- job posting
- Amazon/product marketplace listing

### Profile C: Hardware Parts / Metal Fittings / OEM Components

Product:

- hardware parts
- metal fittings
- OEM components

Required product memory fields:

- `product_keywords_en`: metal fittings, hardware parts, OEM metal components
- `buyer_types`: industrial distributor, manufacturer, procurement company
- `target_countries`: Germany, Mexico, Poland
- `target_industries`: industrial equipment, construction hardware, manufacturing
- `search_keywords`: metal fittings distributor, OEM hardware procurement

Expected search query examples:

- `metal fittings distributor Germany`
- `hardware parts procurement Mexico`
- `OEM metal components buyer Poland`
- `industrial hardware wholesaler`

Expected good candidate type:

- industrial distributor
- hardware importer
- OEM buyer
- manufacturer with component procurement need

Obvious bad candidates:

- metal parts manufacturer competitor
- industry news article
- directory-only page
- unrelated retail hardware store

## 5. Query Design

For each product profile:

- run 1 to 3 queries
- request 3 to 10 results per query
- no batch execution
- no automatic retry

Query pattern examples:

- `{product_keyword} importer`
- `{product_keyword} distributor`
- `{product_keyword} wholesaler`
- `{product_keyword} private label`
- `{product_keyword} procurement`
- `{product_keyword} buyer {country}`

Track for every query:

- query text
- country / region filter
- result count requested
- provider returned count
- generated candidate count
- duplicate count
- invalid / noisy count
- usable candidate count

## 6. Quality Evaluation Rubric

Each candidate should be manually scored.

### 1. Is it a real company?

- yes
- maybe
- no

### 2. Is it likely a buyer rather than supplier?

- buyer
- maybe buyer
- supplier / competitor
- directory / media / irrelevant

### 3. Product fit

- high
- medium
- low
- irrelevant

### 4. Buyer type fit

- importer
- distributor
- wholesaler
- retailer
- brand
- manufacturer
- unclear

### 5. Region fit

- matches target
- acceptable
- irrelevant

### 6. Website quality

- good official website
- weak website
- directory page only
- unreachable

### 7. Match reason quality

- useful
- generic
- wrong

### 8. Recommended next action

- add to CRM
- deep research later
- discard
- needs manual review

### 9. Safety

- no private email / phone shown
- no personal data
- no fake verified claim

### Score categories

- usable candidate
- needs review
- bad candidate
- duplicate
- unsafe candidate

## 7. Metrics

### Operational

- provider success rate
- provider failure rate
- timeout rate
- average latency
- max latency
- query count
- result count
- generated candidate count

### Quality

- valid company rate
- usable candidate rate
- duplicate rate
- irrelevant / noisy rate
- supplier / competitor false-positive rate
- unsafe data rate

### Cost

- estimated cost per query
- estimated cost per returned result
- estimated cost per usable candidate
- daily spend used
- credits_estimated
- credits_charged

### UX

- Are results understandable?
- Are match reasons useful?
- Does the UI clearly say candidates are unverified?
- Is the review and add-to-CRM workflow clear?

## 8. Decision Thresholds

### Operational PASS

Required:

- no API key leak
- no authorization leak
- no `production.env` change
- provider disabled after test or only test tenant enabled
- no email sent
- no OutreachMessage created
- health remains 200
- no ordinary customer impact

### Quality GO

Proceed if:

- usable candidate rate >= 30%
- unsafe data rate = 0
- duplicate rate manageable
- average latency acceptable
- cost per usable candidate acceptable for future pricing

### NEEDS_TUNING

Tune before wider testing if:

- usable candidate rate is 10% to 30%
- match reasons are too generic
- too many suppliers / competitors appear
- query patterns need tuning
- candidate scoring needs improvement

### STOP / REWORK

Stop or rework provider/channel if:

- usable candidate rate < 10%
- unsafe data appears
- API cost too high
- latency too slow
- provider unstable
- too many irrelevant results
- provider terms or cost are unsuitable

## 9. Execution Runbook

This runbook is for later MimoCode execution. This document does not execute it.

### Precheck

1. Confirm production version is v1.1.0-alpha.7 or later.
2. Backup production SQLite.
3. Confirm `/health/live` and `/health/ready`.
4. Confirm acquisition provider disabled by default.
5. Confirm one internal test tenant exists.
6. Confirm test tenant AI is explicitly enabled.
7. Confirm a confirmed product profile exists for the test tenant.

### Fake Smoke First

1. Configure fake acquisition provider.
2. Run one advanced web search fake smoke.
3. Verify candidates are created.
4. Verify ledger row is created.
5. Verify no email / OutreachMessage.
6. Disable provider.

### Brave Live Smoke

1. User enters Brave test key locally or via `/admin/acquisition`.
2. Never send key to chat.
3. Set `provider=brave`.
4. Set `daily_spend_cap_cents=100`.
5. Set `query_limit_per_run=1`.
6. Set `result_limit_per_run=3`.
7. Set `timeout_seconds=10`.
8. Run one profile only.
9. Evaluate results manually.
10. Expand to the other two profiles only if first run is safe.

### Post-Test

1. Disable provider unless explicitly keeping it for internal test tenant.
2. Verify ordinary tenants cannot use real provider.
3. Check logs for secret leaks.
4. Check DB records.
5. Summarize quality metrics without secrets or private data.

## 10. DB / Ledger Checks

Tables:

- `acquisition_provider_settings`
- `target_customer_discovery_runs`
- `target_customer_candidates`
- `ai_usage_ledger`

Verify:

- provider row exists only if configured
- `api_key_encrypted` is not empty if key is set
- `api_key_last4` is masked in UI
- no plaintext key in DB
- run records use `channel_key=advanced_web_search`
- candidates have `source_channel=advanced_web_search`
- candidates have `source_provider=brave` or `fake` in sanitized metadata
- `raw_data_json` is minimal and sanitized
- no email / phone in candidate fields or raw metadata
- ledger includes provider and safe status / error code

Expected alpha.7 ledger limitations:

- Current `ai_usage_ledger` records feature, provider, status, error_code, credits, tokens and latency.
- Query/result/duplicate/invalid counts are stored in discovery run JSON, not separate ledger columns.
- If alpha.8 requires structured metric reporting, add reporting later; do not alter schema for live smoke.

Track via run JSON:

- provider
- query_count
- requested_count
- generated_count
- duplicate_count
- invalid_count
- credits_estimated
- credits_charged
- error_code if failed

## 11. Security and Compliance

Alpha.8 must confirm:

- official Brave API only
- no scraping
- no website crawling
- no browser automation
- no social scraping
- no B2B / customs scraping
- no email / phone enrichment
- no automatic outreach
- no email sending
- no OutreachMessage
- candidates are unverified
- user review is required
- provider disabled by default
- test tenant only
- no API key in logs
- no Authorization header in logs
- no raw provider response exposed to tenant
- no full prompt / response stored
- no reasoning_content stored
- safe errors only

## 12. Future Execution Report Format

```text
# V1.1.0-ALPHA8-BRAVE-LIVE-SMOKE-AND-QUALITY-EVALUATION Report

## 1. Conclusion
PASS / PARTIAL_PASS / FAIL / NEEDS_TUNING

## 2. Environment
- production version
- provider
- test tenant
- limits
- SQLite backup

## 3. Provider configuration
- provider
- masked key
- daily cap
- query limit
- result limit
- timeout

## 4. Query runs
- product profile
- query
- country
- requested results
- returned results
- generated candidates
- duplicates
- invalid results

## 5. Candidate quality
- usable candidates
- needs review
- bad candidates
- duplicate candidates
- unsafe candidates
- examples with sanitized summaries

## 6. Cost / latency
- estimated cost
- latency
- cost per usable candidate

## 7. Ledger / DB
- provider records
- run records
- candidate records
- ledger records

## 8. Security check
- no key leak
- no auth header leak
- no private email/phone
- no raw prompt/response
- no outreach/email

## 9. End state
- provider enabled/disabled
- test tenant status
- ordinary customer impact
- test data status

## 10. Recommendation
- keep Brave as primary
- tune queries
- try SerpAPI backup
- move to Maps
- move to Company Research
- stop/rework
```

## 13. Open Decisions

Decisions required before live smoke:

1. Does the user have a Brave test key?
2. Which internal test tenant should be used?
3. Which 1 to 3 product profiles should be run?
4. Initial query limit: 1 or 3?
5. Initial result count: 3 or 10?
6. Disable provider after test, or keep enabled only for the internal test tenant?
7. What usable candidate rate is acceptable for this product stage?
8. Should quality evaluation remain manual, or be saved as internal notes?
9. Should alpha.8 remain a no-code operational milestone, or add a minor internal reporting UI later?

Recommended defaults:

- Use one internal test tenant.
- Start with Profile A only.
- `query_limit_per_run=1`.
- `result_limit_per_run=3`.
- Disable provider after the first live smoke.
- Treat alpha.8 as a no-code operational milestone unless evaluation reporting becomes repetitive.

