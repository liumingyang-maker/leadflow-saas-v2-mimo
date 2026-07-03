# V1.1.0-alpha.7 高级自动网页搜索渠道 Research and Implementation Plan

Status: READY_FOR_REVIEW

This document is research and implementation planning only. It does not approve code
implementation, migrations, provider account creation, paid API calls, deployment, or production
configuration changes.

Product direction:

火客雷达 = 雇佣一个 AI 外贸员

Alpha.7 definition:

v1.1.0-alpha.7 = 高级自动网页搜索渠道

## 1. Research Conclusion

Recommended alpha.7 provider:

Primary: Brave Search API

Backup: SerpAPI

Not recommended as primary:

- Google Custom Search JSON API / Programmable Search, because Google states the API is closed to
  new customers and existing customers must transition by January 1, 2027.
- Bing Web Search API, because Microsoft states public Bing Search and Bing Custom Search APIs were
  retired on August 11, 2025.

Reserved for later Company Research / Deep Research:

- Exa
- Tavily

Optional later alternatives:

- DataForSEO, if we need broad SERP, maps, local, and SEO-oriented coverage with a larger API
  surface.
- Serper.dev, if low-cost Google SERP access is more important than enterprise controls.

Why Brave first:

- Official Web Search API is simple and directly fits alpha.7's "automatic web search" channel.
- Pricing is clear: $5 per 1,000 Search requests, with free monthly credits and 50 requests per
  second capacity on the listed Search plan.
- It supports web search plus news, video, image, and place search families, while alpha.7 can start
  with web only.
- It supports country and language targeting.
- Response fields map cleanly to `SearchResult`: title, url, description/snippet, and optional
  extra snippets.
- It avoids tying alpha.7 to Google SERP scraping-style providers for the first paid channel.

## 2. Official Source Links

Brave Search API:

- Docs: https://api-dashboard.search.brave.com/app/documentation/web-search/get-started
- Pricing: https://api-dashboard.search.brave.com/documentation/pricing
- Product page: https://brave.com/search/api/

SerpAPI:

- Google Search API docs: https://serpapi.com/search-api
- Pricing: https://serpapi.com/pricing

Google Custom Search JSON API:

- Overview: https://developers.google.com/custom-search/v1/overview
- Introduction: https://developers.google.com/custom-search/v1/introduction

Bing Search APIs:

- Official docs landing page: https://learn.microsoft.com/en-us/bing/search-apis/
- Bing Web Search overview: https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/overview

Tavily:

- Search endpoint docs: https://docs.tavily.com/documentation/api-reference/endpoint/search
- Pricing: https://www.tavily.com/pricing

Exa:

- Search docs: https://exa.ai/docs/reference/search
- Pricing: https://exa.ai/pricing

DataForSEO:

- SERP API docs: https://docs.dataforseo.com/v3/serp/overview/
- Pricing overview: https://dataforseo.com/pricing
- Google Organic SERP pricing: https://dataforseo.com/pricing/serp/google-organic-serp-api

Serper.dev:

- Product/pricing page: https://serper.dev/

## 3. Provider Research Summary

### Brave Search API

Official docs/pricing findings:

- Web Search searches Brave's index and returns human-readable URLs and text snippets.
- Listed Search plan is $5 per 1,000 requests.
- Listed plan includes free $5 credits every month.
- Listed Search plan capacity is 50 requests per second.
- Web Search supports country, search language, and UI language targeting.
- Web Search response includes `web.results[]` with fields such as `title`, `url`,
  `description`, and optional `extra_snippets`.
- Search API family includes Web, LLM Context, News, Video, Image, Summarizer, and Place Search.
- Local place data exists, but alpha.7 should not enable it; Maps/Places should remain a separate
  future channel.

SaaS suitability:

- Good for commercial backend SaaS if terms are accepted and usage remains within plan.
- Platform-owned key is the best first model.
- BYOK is possible later but not necessary for alpha.7.

Risks:

- Result coverage may differ from Google.
- China server outbound access to Brave endpoints must be smoke tested.
- Need daily spend cap and timeout.

Recommendation:

Good for alpha.7 primary provider.

### SerpAPI

Official docs/pricing findings:

- Provides Google Search API and many other SERP engines.
- Google Search response includes `organic_results[]` with `position`, `title`, `link`,
  `displayed_link`, `snippet`, and sitelinks.
- Pricing page lists a free plan with 250 searches per month and 50 throughput per hour.
- Paid plans include Starter at $25/month for 1,000 searches, Developer at $75/month for 5,000,
  Production at $150/month for 15,000, and Big Data at $275/month for 30,000.
- Pricing FAQ states only successful searches count toward monthly searches; cached, errored, and
  failed searches do not.
- It has broad SERP coverage including maps, images, news, shopping, and many other engines.

SaaS suitability:

- Strong Google SERP backup.
- Platform-owned key is suitable.
- BYOK can be considered later for advanced users, but not alpha.7.

Risks:

- Higher cost than Brave for small-volume testing.
- SERP-provider compliance and resale terms must be reviewed before paid production.
- Search result quality may be better for Google-like behavior, but operational/legal surface is
  larger.

Recommendation:

Backup provider if Brave quality is not enough or Google SERP coverage is required.

### Google Custom Search JSON API / Programmable Search

Official docs/pricing findings:

- Google states Custom Search JSON API is closed to new customers.
- Existing customers must transition to an alternative by January 1, 2027.
- Pricing for existing customers is 100 free queries per day, then $5 per 1,000 queries up to
  10,000 queries per day.
- API requires a configured Programmable Search Engine and API key.

SaaS suitability:

- Not suitable for alpha.7 as a new integration.

Risks:

- Closed to new customers.
- Sunset date for existing customers.

Recommendation:

Do not use as alpha.7 primary or backup.

### Bing Web Search / Microsoft Search APIs

Official docs findings:

- Microsoft Learn landing page states public Bing Search and Bing Custom Search APIs were retired
  on August 11, 2025.
- Bing Web Search docs are under previous versions.

SaaS suitability:

- Not suitable for new alpha.7 implementation.

Recommendation:

Do not use.

### Tavily

Official docs/pricing findings:

- Tavily Search is designed for AI agents and returns `results[]` with `title`, `url`, `content`,
  `score`, optional raw content, favicon, images, and usage credits.
- Search depth options include basic, fast, ultra-fast, and advanced.
- Basic/fast/ultra-fast cost 1 API credit; advanced costs 2 API credits.
- `max_results` can return up to 20 results.
- Search topic includes general, news, and finance.
- Country parameter can boost results from a selected country.
- Pricing page lists 1,000 free API credits per month and pay-as-you-go at $0.008 per credit.

SaaS suitability:

- Good for AI research workflows.
- Less ideal for first "raw web SERP acquisition" channel because it is optimized around AI agent
  search content rather than simple SERP candidate retrieval.

Risks:

- Cost model is credit-based and can increase with advanced depth or auto parameters.
- Some features can include raw content extraction; alpha.7 should avoid crawling/content extraction.

Recommendation:

Reserve for Company Research / Deep Research or later research-agent workflows.

### Exa

Official docs/pricing findings:

- Search endpoint returns results with `title`, `url`, `publishedDate`, `author`, `text`,
  highlights, summary, entities, and cost fields.
- Search supports include/exclude domains, dates, result count, search type, category hints
  including company, and user location.
- Pricing page lists a free tier up to 20,000 requests per month.
- Search pricing is listed at $7 per 1,000 requests, with base pricing up to 10 results and
  additional result pricing.
- Exa also has Contents, Deep Search, Agent, Monitors, and contact enrichment pricing.

SaaS suitability:

- Good for future company search, company research, deep research, enrichment, and structured
  outputs.
- For alpha.7 basic web search acquisition, it may be more powerful than needed and has broader
  feature surface than Brave.

Risks:

- Some products include website crawling, contents, deep search, and contact enrichment; those must
  be explicitly disabled or postponed.
- Product surface is broad; easy to over-scope.

Recommendation:

Maybe later, especially for Company Research / Deep Research.

### DataForSEO

Official docs/pricing findings:

- Broad SERP API family: Google organic, maps, local finder, news, images, jobs, autocomplete,
  Bing, YouTube, Baidu, Yahoo, Naver, Seznam, and more.
- Pricing overview says pay-as-you-go with a $50 minimum payment.
- Google Organic SERP pricing is per SERP of 10 results:
  - Standard queue: $0.0006 per SERP / $0.60 per 1,000 SERPs.
  - Priority queue: $0.0012 per SERP / $1.20 per 1,000 SERPs.
  - Live mode: $0.002 per SERP / $2 per 1,000 SERPs.
- Additional parameters can multiply cost.

SaaS suitability:

- Strong later provider for advanced multi-channel search, SEO-style SERP, and maps/local.
- More complex than needed for alpha.7.

Risks:

- Large API surface and pricing complexity.
- Queue modes complicate UX if not carefully designed.
- Some products are closer to scraping/SEO tooling and require careful compliance review.

Recommendation:

Maybe later. Not first alpha.7 provider unless Brave fails and low cost becomes the deciding
factor.

### Serper.dev

Official public page findings:

- Google SERP API with top-up credit model.
- Starter listed at $50 for 50,000 credits, or $1 per 1,000 queries, 50 queries per second.
- Higher tiers list lower per-1,000-query prices.
- Page states real-time results and country/language customization.
- Page states credits are deducted on successful responses.

SaaS suitability:

- Potential low-cost Google SERP fallback.

Risks:

- Public docs visible through browser are less detailed than Brave/SerpAPI/DataForSEO docs.
- Need terms/compliance review before production use.
- More limited enterprise controls than SerpAPI based on public page.

Recommendation:

Maybe later as cost-optimized Google SERP provider. Not alpha.7 primary.

## 4. Provider Comparison

| Provider | Best use | Commercial SaaS suitability | Pricing clarity | Free/trial | Country/language support | API simplicity | Response quality | BYOK suitability | Platform-key suitability | Main risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Brave Search API | First paid automatic web search | Good | Clear | Monthly free credits | Country + language params | High | Good independent index | Later | Strong | Coverage differs from Google | Primary alpha.7 |
| SerpAPI | Google SERP backup | Good if terms accepted | Clear monthly plans | 250/month free | Strong Google location params | Medium | Strong Google-like results | Later | Strong | Cost and SERP compliance | Backup |
| Google Custom Search JSON API | Existing legacy customers only | Poor for new integration | Clear but legacy | Existing only | PSE-dependent | Medium | Google/PSE constrained | No | No | Closed to new customers | Not recommended |
| Bing Web Search API | Legacy Bing search | Not suitable | Retired | No | Legacy only | N/A | N/A | No | No | Retired public APIs | Not recommended |
| Tavily | AI research/search for agents | Good | Clear credits | 1,000 credits/month | Country boosting | High | Good for AI summaries | Later | Good | Can drift into research/crawl scope | Later research |
| Exa | Company/deep research | Good | Clear enough | 20,000 requests/month | User location/category | Medium | Strong for company/research | Later | Good | Broad features can over-scope | Later research |
| DataForSEO | Large-scale SERP/maps/local | Good | Detailed but complex | Try/free account | Extensive | Medium/low | Strong SERP breadth | Later | Good | Complexity and compliance | Maybe later |
| Serper.dev | Low-cost Google SERP | Likely, pending terms | Simple | Top-up model | Country/language | High | Google SERP | Later | Good | Public docs/terms need review | Maybe later |

## 5. Recommended Alpha.7 Provider Decision

Primary provider: Brave Search API

Backup provider: SerpAPI

Do not implement in alpha.7:

- Google Custom Search JSON API
- Bing Web Search
- Tavily
- Exa
- DataForSEO
- Serper.dev

Rationale:

Alpha.7 needs a small, safe, paid web-search channel, not a full research engine or SEO platform.
Brave gives the cleanest path to one provider, one request shape, predictable pricing, and useful
web result fields.

## 6. Alpha.7 Product Scope

User-facing channel:

自动网页搜索

Scope:

1. Search provider adapter interface.
2. Brave provider implementation plan.
3. Fake search provider for local tests and smoke tests.
4. Search query generation from product memory.
5. Automatic search result retrieval from the configured provider.
6. Normalize search results.
7. Candidate scoring.
8. Save candidates to existing `target_customer_candidates`.
9. User reviews candidates.
10. User explicitly adds selected candidates to CRM.
11. Credits and ledger records.
12. Provider disabled by default.
13. Only test tenants enabled initially.

Non-goals:

- Google Maps / Places real integration.
- B2B directory crawling.
- Trade fair crawling.
- Customs data.
- Social scraping.
- Email/phone enrichment.
- Deep research.
- Automatic outreach.
- Automatic follow-up.
- Verified buyer guarantee.
- Purchase intent guarantee.
- Automatic bulk lead generation.
- Automatic email sending.

## 7. Architecture Recommendation

Current alpha.6 structure:

```text
app/integrations/acquisition/
  base.py
  registry.py
  basic_ai_search.py
  fake.py
```

Recommended alpha.7 addition:

```text
app/integrations/acquisition/search_api/
  __init__.py
  base.py
  brave.py
  fake.py
  serpapi.py        # optional stub only if useful; do not enable by default
```

Suggested interface:

```python
class SearchProvider:
    def search(
        self,
        query: str,
        *,
        country: str | None = None,
        language: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        ...
```

SearchResult fields:

```text
title
url
snippet
source_provider
rank
country
language
raw_data
```

Rules:

- Provider registry remains static/config-driven in alpha.7.
- Advanced provider remains disabled unless configured.
- Advanced channel requires global provider config plus tenant-level AI/acquisition enablement.
- Continue using `target_customer_discovery_runs`.
- Continue using `target_customer_candidates`.
- Do not add new candidate tables.
- If config table is added, keep it singleton/admin-level, not tenant-owned.

## 8. Provider Config / BYOK Recommendation

Options:

### Option A: Environment variables only

Pros:

- No migration.
- Simple smoke test.
- Lower risk on production SQLite migration.

Cons:

- Requires production env edits.
- Harder to switch provider from admin UI.
- No admin-visible spend cap/config status.
- Not tenant-specific.

### Option B: Admin-level acquisition provider settings table

Pros:

- Matches existing AI provider settings pattern.
- Supports encrypted platform-owned key.
- Supports provider switching.
- Supports daily spend cap, timeout, query limit, and enabled flag.
- Better SaaS control.

Cons:

- Requires migration.
- Production SQLite Alembic has shown sensitivity in earlier alpha releases.

### Option C: Tenant-level BYOK

Pros:

- Tenant pays own provider cost.
- Useful for advanced customers later.

Cons:

- More complex UX and support.
- Tenants must understand provider accounts and key rotation.
- Harder to enforce consistent compliance/spend controls.

Recommendation:

Use Option B for alpha.7 if migration gate is stable:

```text
acquisition_provider_settings
- id
- provider
- enabled
- api_key_encrypted
- api_key_last4
- daily_spend_cap_cents
- daily_query_cap
- timeout_seconds
- max_results_per_query
- created_at
- updated_at
```

Use platform-owned key first.

Postpone tenant-level BYOK.

Migration fallback:

- If SQLite Alembic predeployment gate fails, defer the settings table and run a test-only
  environment-variable prototype behind a hard disabled-by-default flag.
- Do not modify production env without a separate deployment instruction.
- Do not enable the advanced channel for production users until config storage is stable.

## 9. Credits and Billing Recommendation

Recommended alpha.7 mode:

Test phase free for selected test tenants, with ledger and cost telemetry.

Why:

- We need quality/cost validation before charging users.
- Search result quality may vary heavily by industry/country/query.
- Provider failure and duplicates are likely during early testing.

Alpha.7 behavior:

- Provider disabled: no provider call, disabled ledger, 0 credits.
- Tenant disabled: no provider call, disabled ledger, 0 credits.
- Insufficient credits: no provider call, blocked ledger, 0 credits.
- Provider failure: failed ledger, 0 credits.
- Provider timeout: failed ledger, 0 credits.
- Provider quota exceeded: failed ledger, 0 credits.
- Success: success ledger, 0 credits in test phase, estimated credits recorded in run metadata.

Future charging rule:

- 1-3 target customer credits per generated valid candidate.
- Duplicate candidates: no charge.
- Invalid candidates: no charge.
- Accepted candidate charging can be evaluated later, but may not cover API cost.

Ledger/run metadata should include:

```text
provider
query_count
requested_count
generated_count
duplicate_count
invalid_count
credits_estimated
credits_charged
provider_status
timeout_ms
```

Do not log API key.

## 10. Query Generation and Candidate Pipeline

Pipeline:

```text
confirmed product profile
→ MiMo generates query set
→ search provider returns results
→ normalize results
→ remove obvious non-company results
→ dedupe domain/company
→ optional MiMo classification/scoring
→ save candidates
→ user reviews
→ add to CRM
```

Inputs from product memory:

- `product_keywords_en`
- `buyer_types`
- `target_countries`
- `search_keywords`
- `negative_keywords`
- `target_industries`
- `factory_type`
- `price_positioning`
- `oem_odm_capability`

Query patterns:

- `{product_keyword} importer`
- `{product_keyword} distributor`
- `{product_keyword} wholesaler`
- `{product_keyword} private label`
- `{product_keyword} procurement`
- `{product_keyword} buyer {country}`

Candidate must not include:

- Private email.
- Private phone.
- Personal data.
- Verified buyer claim.
- Purchase intent claim.

## 11. UI / UX Plan

Page:

`/collection`

Channel card:

自动网页搜索

Before configured:

```text
高级渠道，需要管理员配置
```

After provider configured and test tenant enabled:

```text
高级渠道，可用
```

User options:

- Country/region.
- Buyer type.
- Industry.
- Result count.

Show:

- Provider name.
- Estimated target customer credits.
- 搜索结果仅为候选，请审核后使用.
- 不会自动发送邮件.
- 不保证采购意向.

Actions:

- 自动搜索目标客户.
- 查看搜索策略.
- 加入 CRM.

Do not show:

- API key.
- Provider secret.
- Private emails/phones.
- Guaranteed buyer wording.

## 12. Security / Compliance Plan

Alpha.7 must enforce:

- Official APIs only.
- No scraping.
- No browser automation.
- No website crawling.
- No social scraping.
- No private email/phone enrichment.
- No automated outreach.
- User review required.
- Candidates are unverified.
- Provider API key encrypted if stored.
- No API key in logs.
- No full prompt stored.
- No full provider response stored in tenant-visible fields.
- No raw provider response exposed to tenant.
- Rate limit.
- Timeout.
- Safe error messages.
- Daily spend cap.
- Tenant-level enablement.
- Provider disabled by default.

## 13. Tests Plan

Implementation tests should cover:

- Advanced channel disabled when not configured.
- Placeholder channel not executable.
- Configured provider shows executable state for enabled test tenant.
- Disabled tenant cannot call search provider.
- Insufficient credits does not call provider.
- Provider failure no charge.
- Provider timeout safe failure.
- Fake search provider returns results.
- Query generation uses product profile.
- Results normalized into candidates.
- Duplicate domain/company handled.
- No email/phone saved.
- No full provider raw data shown to tenant.
- No API key logged.
- Ledger records provider and credits.
- Add-to-CRM explicit.
- No OutreachMessage.
- No email sending.
- Existing alpha.6 basic search tests pass.
- Existing alpha.5 target discovery tests pass.
- Migration upgrade/downgrade if settings table is added.

## 14. Deployment / Operational Plan

Alpha.7 rollout:

1. Provider disabled by default.
2. Add fake provider path first.
3. Run local and staging smoke with fake provider.
4. Configure real provider only in admin settings or a separate test env gate.
5. Enable only one test tenant.
6. Real provider smoke with very small limit, e.g. 1 query and 3 results.
7. Use no real customer data during smoke.
8. Monitor provider error count, timeout count, result quality, duplicate rate, and estimated cost.

Operational controls:

- Timeout: 8-12 seconds for provider call.
- Query count limit: start with 1-3 queries per run.
- Result count limit: start with 3-10 results per run.
- Daily spend cap: default low cap for alpha.7.
- Retry policy: no automatic retry in alpha.7, or at most one retry for transient 5xx with capped
  timeout.
- Rollback: disable provider globally and tenant channel remains non-executable.

## 15. Implementation Scope

Alpha.7 implementation should include:

- Acquisition provider settings decision and migration if approved.
- Search provider base interface.
- Fake provider.
- Brave provider.
- Provider config validation.
- Query generation service.
- Search result normalization.
- Candidate scoring and dedupe.
- `/collection` advanced web search channel state.
- Explicit add-to-CRM flow reuse.
- Tests and safety checks.

Alpha.7 implementation should not include:

- SerpAPI active provider unless Brave is rejected before implementation.
- BYOK.
- Maps/places.
- Deep research.
- Website content extraction.
- Contact enrichment.
- Email sending.

## 16. Open Decisions Before Implementation

1. Confirm Brave Search API as selected provider.
2. Confirm platform-owned key first, BYOK postponed.
3. Decide whether alpha.7 adds `acquisition_provider_settings`.
4. Decide whether alpha.7 remains test-free or charges test credits.
5. Decide daily spend cap.
6. Decide query limit per run.
7. Decide result count limit per run.
8. Decide whether to store sanitized raw provider response in candidate `raw_data_json` or only
   normalized fields.
9. Decide how provider errors are exposed to admin.
10. Decide whether to include SerpAPI as interface-only backup or postpone entirely.
11. Decide whether Brave local/place features are explicitly postponed to Maps/Places.

Recommended decisions:

1. Select Brave.
2. Use platform-owned key.
3. Add admin-level settings table if migration gate is stable.
4. Keep alpha.7 test-free.
5. Daily cap: $1 or equivalent low internal cap for alpha.7 smoke.
6. Query limit: 1-3 per run.
7. Result count: 3-10 per run.
8. Store normalized fields plus minimal sanitized provider metadata only.
9. Admin sees sanitized provider error code and count, not raw response.
10. Postpone SerpAPI until Brave quality is measured.
11. Postpone Brave local/place to Maps/Places channel.

## 17. Final Recommendation

Proceed to MimoCode plan review with this recommendation:

```text
v1.1.0-alpha.7 should implement Brave Search API as the first advanced automatic web search
provider, disabled by default, enabled only for test tenants, with fake provider smoke first,
0-credit test mode, daily spend cap, and strict candidate safety.
```

Do not implement until the open decisions are accepted.

