# V1.1.0 Alpha 13 MiMo Basic Search Intelligence and Rate Limit Plan

## 1. Goal

alpha.13 的目标是打磨“AI 基础搜索 / MiMo 获客智能化”，让火客雷达更像一个会思考、会改进搜索策略的 AI 外贸员。

当前产品闭环已经跑通：

```text
产品画像 -> 候选客户 -> AI 深度背调 -> AI 开发信草稿
```

alpha.13 不接更多付费搜索 API，不做爬虫平台，不做联系人采集平台。它聚焦：

- MiMo 更好理解“我卖什么”。
- MiMo 生成更聪明的搜索词矩阵。
- 用户手动搜索并粘贴结果。
- MiMo 解析、分类、打分候选客户。
- MiMo 根据用户反馈优化下一轮 query。
- 为未来多用户并发设计 MiMo rate limit、queue、batch、cache、dedup。

Product positioning:

```text
火客雷达 = 雇佣一个 AI 外贸员
```

## 2. Why now

已知状态：

- `v1.1.0-alpha.10.1` 已部署，fresh login tenant context P0 hotfix 已修复。
- alpha.10 已实现基于深度背调生成 AI 开发信草稿。
- alpha.11 fake provider full path PASS。
- alpha.11B real MiMo full path quality smoke PASS。
- alpha.12 beta readiness plan 已提交。
- alpha.12A beta materials 已提交。
- packaging / LED 是当前最适合 limited beta 的行业。

当前最大质量杠杆不在新增 provider，而在“搜索前的策略智能”和“粘贴结果后的判断智能”：

- Brave / paid search 只能提供原始候选结果。
- 对 SOHO、小工厂、小外贸团队来说，最难的是知道搜什么、怎么排除供应商、如何判断 buyer / supplier / directory / article。
- alpha.6 已经定义 AI 普通搜索：MiMo 生成搜索策略，用户手动搜索，MiMo 解析粘贴结果。
- alpha.13 应在 alpha.6 基础上增强 search intent、query matrix、classifier、scoring、feedback learning。

## 3. Current capability inventory

| Capability | Current status | MiMo-powered / rule-based / provider-powered | Current limitation | alpha.13 improvement opportunity |
| --- | --- | --- | --- | --- |
| Tenant product profile / 产品记忆 | Implemented | MiMo-powered extraction + stored profile | Profile is useful but not yet expanded into rich search intent | Generate search intent profile: synonyms, use cases, buyer roles, negative terms, language packs |
| AI product profile extraction | Implemented | MiMo-powered via `product_profile_extraction` | Extracts core product fields, not full search taxonomy | Add search-intent derived fields without changing core profile first |
| Collection / acquisition channel hub | Implemented | Rule-based registry | Channels exist but AI basic search panel is simple | Make AI basic search the primary guided search assistant |
| AI 普通搜索 | Implemented | MiMo-powered strategy + manual user action | Query templates are limited and mostly flat | Query matrix by buyer type, country, industry, language, use case, negatives |
| Basic search strategy generation | Implemented | MiMo-powered via `basic_search_strategy_generation` | Output keys are basic: buyer_types, countries, keywords, negatives, templates | Expand prompt/output to matrix rows, rationale, query quality self-check |
| Pasted search result parsing | Implemented | MiMo-powered via `pasted_search_result_parsing` | Handles snippets but classification taxonomy is shallow | Add buyer/supplier/directory/marketplace/article classification and risk reason |
| Advanced web search provider architecture | Implemented | Provider-powered with gating | Useful but should stay optional and disabled by default | Keep provider path separate; let MiMo improve queries before paid search |
| Brave provider | Implemented | Provider-powered | Cost/quality sensitive; packaging/LED works better than hardware | Use alpha.13 strategy to improve Brave query quality later |
| Query tuning / negative keywords | Partially implemented | Rule-based in advanced search | Static negative terms; not user-feedback-aware | Learn suggested negatives from bad candidates and user feedback |
| Target customer candidates | Implemented | Stored DB model | Candidate model has one confidence score and raw_data summary | Candidate Scoring v2 can add fit, buyer likelihood, source quality in sanitized JSON first |
| Candidate filtering / scoring | Partially implemented | Rule-based for advanced search, MiMo for pasted parse | Scoring is mixed and not transparent enough | Standard scoring rubric: fit_score, confidence, buyer_likelihood, source_quality, risk_reason |
| Add candidate to CRM | Implemented | Rule-based explicit user action | Safe boundary already good | Preserve explicit action; do not auto-create leads from parser |
| Candidate detail | Implemented | Rule/template | Detail is useful after candidate exists | Show richer classification and why/why-not signals |
| AI company research / 深度背调 | Implemented | MiMo-powered via `candidate_company_research` | Depends on candidate metadata quality | Better candidate scoring upstream improves research quality |
| AI outreach draft / 开发信草稿 | Implemented | MiMo-powered via `candidate_outreach_draft` | Depends on research quality | Better research context from stronger candidate parsing improves drafts |
| Tenant gating | Implemented | Rule-based | Strong enough for alpha.13 | Keep all new AI actions behind existing tenant AI gating |
| Quota / ledger | Implemented | Rule-based | Ledger exists, but no global MiMo RPM queue yet | Design queue/rate-limit events; alpha.13A can keep direct ledger path |
| Fake provider | Implemented | Fake deterministic provider | Needs updates for any new feature | Add deterministic fake output in implementation milestones |
| Safety boundaries | Implemented in prompts/tests | Rule + prompt + tests | Boundaries need to remain visible as features expand | Explicitly preserve no crawl, no private contact, no send, no raw response |

## 4. MiMo-only customer discovery methods

These methods do not require a new paid search API and do not require crawling or scraping.

### A. Search Intent Understanding

- What it does: Converts product memory into search intent: product keywords, synonyms, use cases, target industries, buyer roles, buyer company types, target countries, negative keywords, competitor/supplier exclusion terms, and multilingual keyword seeds.
- User input: Confirmed product profile, optional country / buyer type / industry filters.
- MiMo output: Structured `search_intent_profile` JSON.
- Data stored: Prefer store inside existing `target_customer_discovery_runs.generated_plan_json` for alpha.13A.
- Whether migration needed: No for alpha.13A.
- Risk: MiMo may over-expand into irrelevant industries.
- Safety boundary: Strategy only; no verified buyer or purchase intent claims.
- Suggested alpha milestone: alpha.13A.

### B. Query Matrix Generator

- What it does: Generates buyer-type, country, industry, use-case, private label, distributor/importer/retailer/procurement, negative-operator, and multilingual queries.
- User input: Search intent profile, filters, target markets.
- MiMo output: Query matrix rows with query, language, buyer type, country, purpose, negative terms, quality note.
- Data stored: Existing discovery run plan JSON.
- Whether migration needed: No for alpha.13A.
- Risk: Too many queries may overwhelm users.
- Safety boundary: User manually searches; app does not fetch URLs.
- Suggested alpha milestone: alpha.13A.

Required query categories:

- English, German, Spanish, French, Arabic where relevant.
- Packaging patterns: eco-friendly packaging importer, custom packaging distributor, cosmetic packaging brand, coffee roaster packaging buyer, sustainable DTC packaging.
- LED patterns: LED lighting distributor, decorative lighting wholesaler, electrical wholesaler, hotel lighting project supplier, event lighting buyer.
- Hardware later only as low-confidence strategy due buyer/supplier ambiguity.

### C. Manual Search Assistant

- What it does: Guides the user through copying query terms, searching manually, and pasting results back.
- User input: Selected query matrix row and pasted search snippets.
- MiMo output: Parsed company candidates, country, buyer type, snippet, reason, risk, source, recommended next search.
- Data stored: Existing `target_customer_discovery_runs` and `target_customer_candidates`.
- Whether migration needed: No.
- Risk: Users may paste noisy pages or copied ads.
- Safety boundary: No automatic URL access; pasted text is user-provided.
- Suggested alpha milestone: alpha.13B.

### D. Search Result Paste Parser

- What it does: Parses Google / Brave / Bing style snippets, B2B directory snippets, exhibitor list text, PDF copied text, CSV copied rows, manual company lists, and supplier/competitor lists.
- User input: Textarea paste.
- MiMo output: Candidate rows with classification, fit score, source quality, risk reason.
- Data stored: Existing candidates; sanitized raw_data_json summary only.
- Whether migration needed: No initially.
- Risk: Private email/phone may appear in pasted text.
- Safety boundary: Strip email-like and phone-like strings; do not store private contact data.
- Suggested alpha milestone: alpha.13B.

### E. Buyer/Supplier Classifier

- What it does: Classifies each result as buyer, maybe buyer, distributor, importer, wholesaler, retailer, private label brand, procurement company, supplier/competitor, manufacturer, directory, marketplace, article/blog/news, irrelevant, unsafe/needs review.
- User input: Candidate metadata and snippet.
- MiMo output: `classification`, `buyer_likelihood`, `risk_reason`, `manual_review_note`.
- Data stored: In candidate raw_data_json first; later dedicated fields if proven.
- Whether migration needed: No for alpha.13C if JSON is enough.
- Risk: Misclassification can hide usable candidates.
- Safety boundary: Keep “maybe” and “needs review”; do not auto-delete.
- Suggested alpha milestone: alpha.13C.

### F. Candidate Scoring v2

- What it does: Scores candidate fit using product profile, country, buyer type, snippet, source domain, user feedback, blacklist, and negative keywords.
- User input: Candidate + profile + previous feedback.
- MiMo output: `fit_score`, `confidence_score`, `buyer_likelihood`, `source_quality`, match reason, risk reason, next action.
- Data stored: Existing `confidence_score`; additional detail in sanitized raw_data_json first.
- Whether migration needed: Not initially; maybe later if querying by score dimensions becomes important.
- Risk: Score may look too authoritative.
- Safety boundary: Display as unverified ranking aid only.
- Suggested alpha milestone: alpha.13C.

### G. Feedback Learning

- What it does: Turns user labels into next-round query improvements.
- User input: good candidate, bad candidate, supplier, directory, wrong country, wrong industry, low quality source.
- MiMo output: New negative keywords, query patterns, domain blacklist suggestions, buyer term suggestions, country/language adjustment, industry-specific search tips.
- Data stored: `candidate_feedback_events` is recommended once implemented.
- Whether migration needed: Yes if durable feedback learning is implemented.
- Risk: One user’s feedback can overfit.
- Safety boundary: Tenant-scoped feedback only; no global learning without review.
- Suggested alpha milestone: alpha.13D.

### H. Lookalike Search Strategy

- What it does: Uses a good candidate to generate search strategy variants for similar buyer company types, keywords, countries, use cases, and procurement terms.
- User input: One selected good candidate and product profile.
- MiMo output: Lookalike query variants and exclusion terms.
- Data stored: Discovery run plan JSON or future `query_matrix_runs`.
- Whether migration needed: No initially.
- Risk: User may think the system found that company’s actual customers.
- Safety boundary: State this is search strategy only, not known relationship data.
- Suggested alpha milestone: alpha.13D.

### I. Exhibition / Directory Paste Mode

- What it does: Parses user-copied trade fair exhibitor lists, association member lists, or directory text.
- User input: Pasted public list text or copied CSV rows.
- MiMo output: Candidate list with directory/source label, buyer/supplier classification, risk notes.
- Data stored: Existing candidates with source_channel `directory_paste` or `exhibition_paste`.
- Whether migration needed: No initially.
- Risk: Directory terms and exhibitors may be suppliers.
- Safety boundary: No automatic directory crawling; user-provided paste only.
- Suggested alpha milestone: alpha.15.

### J. Multi-language Buyer Terms

- What it does: Generates local-language buyer terms for importer, distributor, wholesaler, retailer, procurement, purchasing, private label, supplier wanted.
- User input: Product profile and target countries.
- MiMo output: Local phrase pack by language and country with risk notes.
- Data stored: Query matrix JSON.
- Whether migration needed: No.
- Risk: Local phrase may be unnatural or too broad.
- Safety boundary: Mark terms as search aids requiring user review.
- Suggested alpha milestone: alpha.13A.

### K. Competitor-to-Buyer Search Strategy

- What it does: Uses user-provided competitor/company name or description to generate likely buyer types and search terms for similar distributors/importers.
- User input: Competitor name, website URL as text, or user description.
- MiMo output: Strategy, not scraped facts: likely channels, buyer terms, exclusions to avoid suppliers.
- Data stored: Discovery run plan JSON.
- Whether migration needed: No.
- Risk: Can drift into claims about competitor customers.
- Safety boundary: Do not crawl website; do not claim actual competitor buyers.
- Suggested alpha milestone: alpha.13D.

### L. Product Use-case Expansion

- What it does: Expands product profile into buyer use-case maps.
- User input: Product profile.
- MiMo output: Use-case buyer map.
- Data stored: Search intent or query matrix JSON.
- Whether migration needed: No.
- Risk: Some use cases may not fit factory capability.
- Safety boundary: Display as ideas for manual selection.
- Suggested alpha milestone: alpha.13A.

Examples:

- Packaging: cosmetic packaging brands, coffee roasters, pet food brands, boutique retailers, sustainable DTC brands.
- LED: lighting distributors, interior design firms, hotel project suppliers, event production companies, electrical wholesalers.

### M. Country Market Phrase Pack

- What it does: Builds country-specific local buyer terms, distributor terms, procurement phrases, search operators, and language-specific negative terms.
- User input: Target country list.
- MiMo output: Phrase pack by country and language.
- Data stored: Query matrix JSON.
- Whether migration needed: No.
- Risk: Regulatory or market terminology may be imperfect.
- Safety boundary: Phrase suggestions only; no market guarantee.
- Suggested alpha milestone: alpha.13A.

### N. Query Quality Self-check

- What it does: Reviews generated query rows for being too broad, supplier-biased, marketplace-heavy, directory-heavy, missing country, or missing buyer role.
- User input: Query matrix draft.
- MiMo output: Improved query rows with `quality_score`, `issue`, and `fix`.
- Data stored: Query matrix JSON.
- Whether migration needed: No.
- Risk: Over-optimizing may remove useful broad discovery queries.
- Safety boundary: Show alternatives rather than silently deleting all broad queries.
- Suggested alpha milestone: alpha.13A.

## 5. Market / GitHub pattern review

These are architecture patterns to learn from, not dependencies to add in alpha.13.

| Pattern | Useful idea | Safe now? | Out of scope now | Future phase |
| --- | --- | --- | --- | --- |
| SalesGPT-like sales agents | Sales stage awareness, product knowledge base, conversation objective, human-in-the-loop reasoning | Yes, as prompt and workflow inspiration | Automatic sending, payment link, calendar automation, autonomous outbound agent | Later sales assistant workflow |
| AI FindCustomer / lead generation tools | Profile -> ICP -> lead ideas -> qualification flow, staged scoring | Yes, as product flow inspiration | Uncontrolled scraping, private contact enrichment, auto-outreach | Candidate scoring v2 and feedback learning |
| Sales outreach automation / cold email tools | Email draft structure, personalization angle, follow-up angle as suggestion | Already partly used in alpha.10 | Automatic campaigns, SMTP sending, sequence automation | Manual draft polish only |
| ScrapeGraphAI / Crawl4AI-like extraction pipelines | Structured extraction, source-aware extraction, text normalization concept | Partially, for user-pasted text only | Crawler, browser automation, website scraping, Playwright crawl, social crawling | alpha.14 lightweight website research only after separate approval |
| LangGraph-like workflow engines | State machine, durable workflow, human-in-the-loop, recoverable long-running jobs | Conceptually useful | Adding LangGraph dependency or rewriting jobs | Later if DB job state becomes too complex |
| AI lead scoring / qualification | Scoring rubric, ICP-like qualification, risk flags, reasoned score | Yes | Claiming purchase intent, verified buyer claims, private data enrichment | alpha.13C scoring v2 |

Current strategy:

- alpha.13 should use existing DB job/state patterns, ledger, tenant gating, and target candidate tables.
- Do not introduce LangGraph, crawler frameworks, or new external data providers.
- Reuse ideas as architecture language and prompts, not as new dependencies.

## 6. Official MiMo API rate-limit facts

The plan must assume these MiMo limits and behaviors:

- RPM = Requests Per Minute.
- TPM = Tokens Per Minute.
- Calling the same model under one account merges request counts across all API keys for RPM.
- Calling the same model under one account merges token totals across all API keys for TPM.
- Server load can cause response latency or `429`.
- Requests need retry and backoff strategy.
- `mimo-v2.5-pro`: 100 RPM / 10M TPM.
- `mimo-v2.5`: 100 RPM / 10M TPM.
- Do not split traffic across API keys to bypass account-level limits.
- Do not run at the full 100 RPM ceiling.
- Recommended default safe cap: 80 RPM.
- After `429`, automatically slow down to 50-60 RPM and gradually recover.

Implications:

- Early beta can keep direct synchronous calls for interactive features.
- Multi-tenant growth needs an account/model-level queue before traffic approaches the safe cap.
- Token budget is high but not infinite; batching must estimate tokens, not only count items.

## 7. Rate-limit architecture

### A. Constraints

- MiMo account-level RPM applies across all API keys.
- Model-level RPM and TPM apply across all tenants using the same model.
- TPM is high but not infinite.
- Provider may fail, delay, or return `429`.
- Current production is a low-memory SQLite deployment.
- Early beta user count is small, but future multi-tenant concurrency needs fairness.
- Login and normal page render must never depend on AI queue availability.

### B. Token bucket / leaky bucket design

Recommended architecture:

- Account-level bucket: global MiMo account cap, default configured `max_rpm=80`.
- Model-level bucket: one bucket per model, e.g. `mimo-v2.5`, `mimo-v2.5-pro`.
- Tenant-level quota: existing tenant AI quota remains the first user-facing gate.
- Feature-level quota: expected credits and priority per AI feature.
- Per-tenant burst limit: prevent one tenant from filling the queue.
- 429 backoff with jitter: reduce effective max RPM to 50-60 after 429.
- Cool-down mode: if repeated 429 or latency spike occurs, pause background jobs.
- Gradual recovery: increase by small increments after a quiet period.

Do not:

- Use multiple API keys to bypass account-level limits.
- Let low-priority batch jobs starve interactive research/draft actions.
- Make `/login`, `/workbench`, or `/collection` wait on AI queue.

### C. Queue design options

Option 1: Reuse existing ledger + job state first.

- Pros: no migration, lower SQLite risk, faster alpha.13A.
- Cons: not enough for multi-worker fair scheduling or provider backoff history.
- Best for: alpha.13A through alpha.13D while traffic is tiny.

Option 2: Add dedicated AI queue/rate-limit tables.

- Pros: durable scheduling, fairness, retries, batch tracking, cache introspection.
- Cons: several migrations, more operational complexity on SQLite.
- Best for: alpha.13E when beta traffic or batching requires it.

Recommendation:

- alpha.13A should not add queue tables.
- alpha.13E should implement a minimal queue if real usage shows concurrency pressure.

## 8. Queue / batching design

Potential future tables:

### `ai_request_queue`

- Purpose: Durable per-item AI work queue.
- Minimal fields: `id`, `tenant_id`, `feature_name`, `model`, `priority`, `status`, `payload_json`, `payload_hash`, `batch_key`, `not_before`, `attempts`, `last_error_code`, `created_at`, `updated_at`.
- Status values: `queued`, `running`, `waiting_provider`, `completed`, `failed`, `cancelled`.

### `ai_batch_jobs`

- Purpose: Track one provider call that handles multiple items.
- Minimal fields: `id`, `model`, `feature_name`, `status`, `item_count`, `estimated_input_tokens`, `estimated_output_tokens`, `request_started_at`, `request_finished_at`, `provider_status`, `error_code`, `created_at`, `updated_at`.

### `ai_cache_entries`

- Purpose: Cache deterministic structured AI outputs by normalized input hash.
- Minimal fields: `id`, `tenant_id nullable`, `feature_name`, `model`, `input_hash`, `prompt_version`, `output_json`, `expires_at`, `created_at`.

### `ai_rate_limit_events`

- Purpose: Audit rate-limit behavior and incidents.
- Minimal fields: `id`, `model`, `feature_name`, `event_type`, `rpm_snapshot`, `queue_length`, `error_code`, `created_at`.

### Feature priority

1. Product profile extraction.
2. Interactive candidate research.
3. Outreach draft.
4. Search result paste parsing.
5. Candidate scoring.
6. Feedback learning.
7. Batch report regeneration.

Rules:

- Login and page rendering do not enter AI queue.
- Interactive user actions take priority.
- Background/batch jobs can wait.

### Batching

Initial batch window:

- alpha initial: 3-5 seconds.
- Low traffic: do not wait too long just to fill a batch.
- High traffic: auto-batch within the window.
- Later tuning: 500ms-2s if UX requires faster turnarounds.

Suggested batch sizes:

- Search result parsing: 20-50 snippets per call.
- Candidate scoring: 30-50 candidates per call.
- Company research: 5-10 candidates per call.
- Outreach drafts: 5-10 drafts per call.
- Product profile strategy: 1-5 profiles per call.

Required batching rules:

- Use token estimates to split batches.
- Do not split only by item count.
- Every item must have stable `item_id`.
- Provider response must map output by `item_id`.
- A single item failure must not destroy the whole batch.
- Store only structured sanitized output, not full prompt/raw response/reasoning.

## 9. Cache / dedup design

Cache targets:

- Product profile extraction cache.
- Search strategy cache.
- Query matrix cache.
- Pasted search result parse cache.
- Candidate scoring cache.
- Company research cache.
- Outreach draft cache.

Dedup fingerprints:

- Normalized product profile hash.
- Query fingerprint.
- Pasted text hash.
- Source URL/domain fingerprint.
- Company name/domain fingerprint.
- Candidate hash.
- Prompt version hash.

Strategy:

- Exact hash hit can reuse output if prompt version and safety version match.
- Similar profile semantic reuse should not be used in alpha.13 because it can misfit tenant context.
- User-confirmed good candidates can increase confidence for tenant-local future query suggestions.
- Do not cache private contact data.
- Do not cache full prompt, raw provider response, reasoning content, or full AI response.
- Cache entries should have TTL and be tenant-scoped unless the input is clearly generic.

## 10. Degradation strategy

Degradation levels:

- L1 normal: AI parse + score + report + draft.
- L2 light: AI only top candidates; lower-ranked candidates get basic rule-based hints.
- L3 heavy: rule-based extraction first, AI queued for later enrichment.
- L4 circuit breaker: pause new AI jobs and show safe busy state.

User-facing copy:

```text
系统繁忙，请稍后重试。
任务已排队，预计稍后完成。
已先生成基础候选，AI 分析稍后补充。
测试阶段不扣额度。
```

Operational behavior:

- Provider `429`: enter cool-down, reduce RPM to 50-60, add jittered retry.
- Repeated provider failure: stop background jobs, keep interactive UI available.
- Queue backlog: show queued state and estimated position.
- Tenant quota blocked: no provider call, ledger records blocked/disabled according to existing pattern.

## 11. UX / task state design

Users should not see RPM, TPM, token bucket, or provider internals.

Users should see:

- 任务已提交。
- AI 正在分析。
- 前面还有几个任务。
- 预计完成时间。
- 结果完成后刷新。
- 失败可重试。
- 测试阶段不扣额度。

Search assistant page should include:

- Product profile summary.
- Recommended buyer types.
- Recommended countries/languages.
- Search intent summary.
- Search query matrix.
- Copy query button.
- Paste search result textarea.
- AI parse button.
- Candidate result cards.
- Feedback buttons: 好候选 / 差候选 / 供应商 / 目录站 / 国家不对 / 行业不对.

Task states:

- `queued`
- `running`
- `waiting_ai`
- `waiting_user_paste`
- `completed`
- `failed`
- `needs_review`

MVP note:

- alpha.13A can stay synchronous and store planned query matrix in existing discovery run.
- Queue/task UI becomes more important in alpha.13E/G.

## 12. Safety boundaries

alpha.13 must keep these hard boundaries:

- No automatic email sending.
- No `OutreachMessage` creation.
- No private email/phone enrichment.
- No website crawling now.
- No candidate website body fetch.
- No LinkedIn / Facebook / WhatsApp / Telegram scraping.
- No customs scraping.
- No B2B directory scraping.
- No Maps scraping.
- No verified buyer claim.
- No purchase intent claim.
- No confirmed contact person claim.
- No full prompt storage.
- No full response storage.
- No `reasoning_content` storage.
- No raw provider response storage.
- Ledger required for AI actions.
- Tenant gating required.
- User review required before adding candidate to CRM.

Allowed:

- User manually searches public search engines.
- User pastes text they copied.
- MiMo parses user-provided text into sanitized structured summaries.
- MiMo suggests queries and risk flags.
- MiMo stores sanitized candidate metadata and source summaries.

## 13. Data model proposals

These are proposals only; do not implement all at once.

| Table | Purpose | Minimal fields | Whether alpha.13A needs it | SQLite risk | Migration timing |
| --- | --- | --- | --- | --- | --- |
| `search_intent_profiles` | Persist product-derived search taxonomy | `id`, `tenant_id`, `product_profile_id`, `intent_json`, `prompt_version`, `created_at`, `updated_at` | No; use discovery run JSON first | Medium | Later if query history needs reuse |
| `query_matrix_runs` | Store generated query matrix and self-check | `id`, `tenant_id`, `product_profile_id`, `filters_json`, `matrix_json`, `status`, `ai_usage_ledger_id`, `created_at` | No; reuse `target_customer_discovery_runs.generated_plan_json` | Medium | Only if matrix needs independent history |
| `pasted_search_parse_runs` | Track pasted parser runs separately from candidate runs | `id`, `tenant_id`, `run_id`, `pasted_hash`, `status`, `candidate_count`, `created_at` | No | Medium | Later if parser analytics needed |
| `candidate_feedback_events` | Store user feedback labels | `id`, `tenant_id`, `candidate_id`, `feedback_type`, `note`, `created_by`, `created_at` | Not for alpha.13A | Low-medium | alpha.13D |
| `ai_request_queue` | Durable AI scheduling | See section 8 | No | Medium-high | alpha.13E |
| `ai_batch_jobs` | Provider batch call tracking | See section 8 | No | Medium | alpha.13E |
| `ai_cache_entries` | Reuse deterministic output | See section 8 | No | Medium | alpha.13F |
| `ai_rate_limit_events` | Rate-limit observability | See section 8 | No | Low-medium | alpha.13E/F |

Recommendation:

- alpha.13A should reuse `target_customer_discovery_runs` and `target_customer_candidates`.
- Store query matrix and search intent in `generated_plan_json`.
- Store scoring/classification details in candidate `raw_data_json` until the schema need is proven.
- Avoid multiple migrations in one alpha on production SQLite.

## 14. Implementation roadmap

### alpha.13A: MiMo Search Intent + Query Matrix

- Goal: Improve AI basic search quality before users manually search.
- Data model: No migration; store search intent and query matrix in `target_customer_discovery_runs.generated_plan_json`.
- Route/UI: Reuse `/collection` and basic search strategy route; show matrix and copy buttons.
- Service logic: Add feature or extend `basic_search_strategy_generation` output to include intent, matrix, language, negative terms, quality self-check.
- Tests: strategy generation, no crawling, tenant gating, disabled AI no provider call, ledger 0 charged, matrix rendered.
- Migration need: No.
- Risk: Prompt output shape changes may break template; keep backwards compatibility with current keys.

### alpha.13B: Manual Search Paste Parser v2

- Goal: Better parser for copied Google/Brave/Bing snippets, CSV rows, directory text, PDF copied text, and manual lists.
- Data model: No migration initially.
- Service logic: Expand parser output with classification and risk fields.
- Tests: private contact stripping, noisy directory classification, supplier classification, candidate storage safety.
- Risk: Pasted text can be messy; keep safe fallback.

### alpha.13C: Buyer/Supplier Classifier + Candidate Scoring v2

- Goal: Explicitly distinguish buyer, maybe buyer, supplier, manufacturer, directory, marketplace, article, irrelevant.
- Data model: Use candidate raw_data_json first.
- Tests: classifier labels, score ranges, low-confidence hardware behavior, no verified claims.
- Risk: Misclassification; keep user override.

### alpha.13D: Feedback Learning / Query Refinement

- Goal: Let user feedback improve next search.
- Data model: Add `candidate_feedback_events` if approved.
- Tests: feedback tenant isolation, suggested negatives, no global leakage.
- Risk: Overfitting and tenant data leakage.

### alpha.13E: Rate-limit Queue + Batch Architecture MVP

- Goal: Add durable AI request queue and rate-limit events if traffic requires.
- Data model: `ai_request_queue`, maybe `ai_rate_limit_events`.
- Tests: quota blocks before enqueue, 429 backoff, priority order, no provider call when disabled.
- Risk: SQLite locking and operational complexity.

### alpha.13F: Cache / Dedup MVP

- Goal: Cache exact repeated AI outputs and dedup repeated pasted inputs/candidates.
- Data model: `ai_cache_entries`.
- Tests: hash match reuse, prompt version invalidation, no private contact cache, tenant scope.
- Risk: Stale or cross-tenant cache leakage.

### alpha.13G: UX task status / queued report

- Goal: Show queued/running/completed states and estimated wait.
- Data model: Depends on queue implementation.
- Tests: status render, retry affordance, no 500 on failed jobs.
- Risk: More UI states and localization work.

### alpha.14: Company Website Lightweight Research

- User-provided URL only.
- Public company-level pages only.
- No login, no bypassing restrictions, no social.
- No private contact enrichment.
- No raw full page storage.
- Separate approval required.

### alpha.15: Directory / Exhibition Paste Mode

- User pastes exhibitor/member/directory text.
- MiMo parses and scores.
- No automatic directory crawling.
- No bypassing access limits.

### alpha.16: Public Contact Channel MVP

- Contact page / general company email / contact form only.
- Manual confirmation required.
- No private email/phone enrichment.
- No automatic sending.

## 15. Recommended first milestone

Recommended first implementation:

```text
alpha.13A MiMo Search Intent + Query Matrix
```

Reasons:

- Biggest quality lift for AI basic search.
- Does not require new paid search API.
- Does not require crawling.
- Does not require contact enrichment.
- Fits existing product profile, collection hub, and pasted search flow.
- Low risk for packaging / LED beta.
- Can keep using existing ledger, tenant gating, fake provider, and discovery run tables.

alpha.13A should include:

- Generate search intent profile from confirmed product memory.
- Generate query matrix by buyer type / country / language / negative terms.
- Include packaging and LED use-case expansions.
- Include multilingual buyer terms.
- Include query quality self-check.
- Render matrix in existing collection page.
- Add copy button if simple and safe.
- Alpha stage `credits_charged=0` with ledger.
- Tenant AI gating and global AI gating.

alpha.13A should not include:

- Rate-limit queue implementation.
- Crawling.
- Contact enrichment.
- Provider expansion.
- Email sending.
- `OutreachMessage`.
- Brave/MiMo/Qwen web search provider changes.

## 16. Acceptance criteria

- Designs at least 12 MiMo-powered customer discovery methods.
- Does not require paid search API.
- Does not require crawling or scraping.
- Keeps no-email and no-`OutreachMessage` boundary.
- Keeps no private email/phone enrichment boundary.
- Accounts for MiMo 100 RPM / 10M TPM.
- Proposes queue and batching.
- Proposes cache and dedup.
- Proposes degradation strategy.
- Proposes phased implementation.
- Identifies market/GitHub-style ideas safe to reuse and out of scope.
- Recommends alpha.13A as first implementation milestone.
- Reuses current AI Control Plane, tenant gating, AI ledger, collection/acquisition hub, target candidates, candidate research, and candidate outreach draft architecture.

## 17. Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Query matrix becomes too broad | Users get noisy results | Query self-check, negative terms, packaging/LED-specific patterns |
| Supplier/competitor misclassification | Users waste time | Buyer/supplier classifier, risk reason, user feedback labels |
| Users think candidates are verified | Safety/product trust issue | Visible “未验证 / 人工确认” copy and no verified buyer claims |
| Users expect automatic search | Scope creep | Keep manual search assistant explicit; no hidden URL fetch |
| Pasted text contains private contact info | Privacy risk | Strip email/phone-like strings before storage and display |
| MiMo 429 / latency | Failed user actions | Safe 80 RPM cap design, backoff to 50-60 RPM, queue in alpha.13E |
| SQLite migration friction | Production risk | alpha.13A no migration; add tables only in later narrow milestones |
| Queue complexity too early | Delays beta polish | Keep alpha.13A synchronous; queue is architecture plan only |
| Cache leakage across tenants | Data isolation issue | Tenant-scope cache unless input is truly generic; no raw prompt/response |
| Overfitting from feedback | Lower future quality | Tenant-local suggestions; global rules require manual review |
| Hardware/OEM low quality | Bad beta experience | Keep hardware low-confidence/later-only; focus packaging/LED |
| Scope creep into crawler/contact/email | Safety and compliance risk | Hard boundaries in every milestone and test suite |
