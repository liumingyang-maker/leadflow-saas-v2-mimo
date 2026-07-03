# V1.1.0 Alpha 12 Packaging / LED Limited Beta Readiness Plan

## 1. Goal

v1.1.0-alpha.12 的目标不是开发新功能，而是制定 packaging / LED 行业小范围 beta 的准备计划。

当前产品主线已经跑通：

```text
产品画像 -> 候选客户 -> AI 深度背调 -> AI 开发信草稿
```

alpha.12 要回答的问题是：

```text
哪些用户可以试？
哪些行业可以试？
怎么开启？
怎么限制成本和风险？
怎么收集反馈？
出现问题怎么立刻关闭？
```

产品定位保持：

```text
火客雷达 = 雇佣一个 AI 外贸员
```

本计划只面向 packaging / LED limited beta，不开放硬件/五金行业，不扩展自动发信、联系人补充、海关、地图、B2B directory、国产联网搜索 provider。

## 2. Current readiness evidence

已知背景：

- v1.1.0-alpha.10 已部署。
- alpha.11 fake provider 完整人工路径 PASS。
- alpha.11B 真实 MiMo AI 完整路径质量 smoke PASS。
- 真实 MiMo AI 输出质量适合 packaging / LED 小范围 beta。
- 完整路径已经覆盖产品画像、候选客户、AI 深度背调、AI 开发信草稿。

本仓库内可引用的本地依据：

- `docs/product/AI_FOREIGN_TRADE_OPERATOR_BLUEPRINT.md`
  - 定义“火客雷达 = 雇佣一个 AI 外贸员”。
  - 明确核心闭环包含产品记忆、找客户、深度背调、生成开发信、用户手动发送。
- `docs/product/V1_1_0_ALPHA8_ADVANCED_SEARCH_QUALITY_EVALUATION_AND_BRAVE_LIVE_SMOKE_PLAN.md`
  - 已将 eco-friendly packaging bags 和 LED lighting 作为高级搜索质量评估 profile。
  - 已明确 hardware parts / metal fittings 质量风险更高，容易出现供应商/同行误判。
  - 已定义 usable candidate rate >= 30% 作为继续测试阈值。
- `docs/product/V1_1_0_ALPHA9_CANDIDATE_COMPANY_RESEARCH_MVP_PLAN.md`
  - 明确 packaging / LED 适合 limited beta。
  - 明确 hardware / metal fittings 暂时 restricted 或 low-confidence。
  - 定义 AI 深度背调的安全边界：未验证、人工确认、无抓取、无私人联系方式、无自动外联。
- `docs/product/V1_1_0_ALPHA10_OUTREACH_FROM_COMPANY_RESEARCH_MVP_PLAN.md`
  - 定义从 completed research report 生成 AI 开发信草稿。
  - 明确 draft-only：不发送邮件、不创建 `OutreachMessage`、不连接邮箱。
  - 定义开发信 prompt 和 UI 中必须保留的未验证、人工确认、不会自动发送安全文案。
- `.autopilot/evidence/FINAL_GO_NOGO_SANITIZED_20260701_174857.md`
  - 既有 controlled beta go/no-go evidence，可作为运营 checklist 和证据格式参考。
- `docs/LOW_MEMORY_BETA_DEPLOYMENT.md`
  - SQLite low-memory beta 适用于 1-3 concurrent users。
  - 强调备份、迁移、健康检查和低并发限制。

Notes:

- 本地未找到以 alpha.11 / alpha.11B 命名的报告文件；本计划将用户提供的 alpha.11 / alpha.11B PASS 结论作为运营质量依据。
- beta 前仍应将 alpha.11 / alpha.11B 的最终报告或 sanitized evidence 补入 `.autopilot/evidence/`，便于后续审计。

## 3. Beta scope

### Allowed industries

第一批只允许：

- eco-friendly packaging
- custom packaging
- packaging bags
- compostable / recyclable packaging
- LED lighting
- decorative lighting
- commercial LED
- pendant lights / lighting retail / lighting distributor 场景

### Allowed product flows

beta 用户可以使用：

- product profile
- target customer discovery
- advanced web search, only if provider is enabled for the beta tenant
- candidate list and candidate detail
- AI company research
- AI outreach draft
- manual copy of generated draft

### Allowed data sources

允许：

- 用户手动填写的产品画像。
- 已保存的 candidate metadata。
- 已保存的 source snippet / source URL。
- 已完成的 AI company research report。
- 已启用 provider 返回的搜索结果摘要。

不允许：

- 抓取 candidate website body。
- 抓取 LinkedIn / Facebook / WhatsApp / Telegram。
- 抓取 B2B directory 或海关数据。
- 私人邮箱/手机号 enrichment。

## 4. Out of scope

alpha.12 beta 明确不做：

- no automatic email sending
- no platform SMTP sending for candidate drafts
- no mailbox connection
- no Gmail / Outlook integration
- no `OutreachMessage` creation
- no sequences / campaigns
- no bulk sending
- no automatic follow-up
- no private email / phone enrichment
- no LinkedIn / Facebook / WhatsApp / Telegram scraping
- no website crawling
- no webpage body fetching
- no browser automation
- no customs scraping
- no B2B directory scraping
- no Maps expansion
- no Qwen Web Search provider implementation
- no MiMo Web Search provider implementation
- no SerpAPI provider implementation
- no hardware / metal fittings public beta
- no broad industry marketplace launch

暂不开放行业：

- hardware / metal fittings / OEM hardware
- customs-data-heavy industries
- buyer/supplier distinction unclear industries
- any industry requiring private contact enrichment

## 5. Beta user eligibility

### Priority beta users

优先邀请：

- SOHO 外贸人。
- 小工厂老板或业务员。
- 小外贸团队。
- 产品属于包装或 LED。
- 愿意手动审核候选客户。
- 愿意人工复制和修改开发信。
- 明白系统不会自动发信。
- 愿意反馈候选客户质量和开发信质量。

### Not suitable for this beta

暂不适合：

- 要求自动群发。
- 要求找私人邮箱/手机号。
- 要求海关数据。
- 要求大量行业覆盖。
- 要求实时大规模搜索。
- 要求 LinkedIn 联系人抓取。
- 不愿意人工确认 AI 结果。
- 把系统输出当作 verified buyer 或 confirmed purchase intent 的用户。

### User count limits

第一批建议：

- 1-3 个内部/熟人 beta 用户。
- 每个用户不超过 10 个候选客户体验。
- 每个用户不超过 3 次 AI 深度背调。
- 每个用户不超过 3 封 AI 开发信草稿。
- 每批 beta 至少收集一次结构化反馈后再决定是否扩大。

## 6. Tenant enablement and gating

原则：

- 默认不对普通客户开放。
- 只对指定 beta tenant 开启。
- AI tenant enabled 必须手动开启。
- Advanced search provider 默认 disabled。
- Acquisition provider 只在需要真实搜索时手动开启。
- Quotas 必须小且可恢复到 0。
- 所有 AI 和搜索行为必须记录 ledger / run record。
- 用户退出 beta 或测试完成后可关闭。

### How to identify beta tenant

推荐运营记录：

```text
beta_tenant_id
tenant company name
owner email
allowed industry: packaging | led
beta start date
beta end date
enabled features
quota limits
operator owner
```

如果当前产品没有显式 beta flag，不建议为 alpha.12 新增代码。使用人工白名单和 admin 配置记录即可。

### How to enable AI

For selected beta tenant only:

1. Admin 确认 tenant identity。
2. Admin 开启 tenant AI。
3. 设置低额度 included credits / usage allowance。
4. 验证 global AI provider 已配置但不暴露 provider secrets 给 tenant。
5. 记录开启时间和操作者。

普通 tenant:

- tenant AI remains disabled。
- provider settings 不应让普通 tenant 可见或可用。

### How to enable acquisition provider

Advanced web search 的 beta 策略：

- 默认 disabled。
- 如果 beta 用户需要真实搜索，由管理员为 beta 环境配置 provider。
- query limit per run 和 result limit per run 设置为低值。
- daily spend cap 设置为低值。
- 每轮测试结束后可关闭 provider。

### How to avoid ordinary customer misuse

Required controls:

- Tenant AI disabled by default。
- Acquisition provider disabled by default。
- Beta tenant 人工白名单。
- Beta quota 小于正式套餐。
- Admin 每日查看 usage。
- 不在公开页面宣称所有行业可用。
- 不向普通用户展示“自动联网找客户”承诺。

### Emergency close

最快关闭顺序：

1. Disable acquisition provider。
2. Disable tenant AI for beta tenant。
3. Set tenant quota to 0。
4. Disable global AI provider if provider-level issue exists。
5. Remove beta user access if account misuse exists。

## 7. Beta quotas and usage limits

Recommended free beta package:

```text
10 个目标客户候选
3 次 AI 深度背调
3 封 AI 开发信草稿
```

Advanced web search:

- 每天最多 3-5 次 query。
- 每次最多 5 条结果。
- 不做 batch。
- 不做 automatic retry。
- 测试结束后检查 spend cap 和 provider usage。

AI:

- beta 阶段可以继续 `credits_charged = 0`。
- ledger 必须记录 estimated usage / feature name / provider / model / status / error_code。
- failure charges 0。
- quota blocked 不调用 provider。
- disabled tenant 不调用 provider。

Suggested internal budget model:

```text
target customer candidate: 1 unit
AI company research: 5 units estimated
AI outreach draft: 3 units estimated
```

SQLite / low-memory beta limit:

- 适用于 1-3 个用户低并发试用。
- 不建议开放给并发团队或公开注册用户。
- 每日备份必须存在。

## 8. Beta user guide

用户看到的操作路径：

1. 告诉 AI 我卖什么。
2. 保存产品画像。
3. 选择目标市场。
4. 生成候选客户。
5. 打开候选客户详情。
6. 点击 `AI 深度背调`。
7. 看懂这个客户为什么可能适合。
8. 点击 `生成 AI 开发信`。
9. 人工修改/复制开发信。
10. 自己通过邮箱、WhatsApp、LinkedIn 或其他渠道手动发送。

必须给用户讲清楚：

- 系统不会自动发送邮件。
- AI 结果未验证。
- 发送前必须人工确认。
- 不会保存或生成私人邮箱/手机号。
- 不保证客户一定采购。
- 不保证候选公司一定是买家。
- beta 期间功能可能变化。
- 如果看到明显不相关候选、同行、供应商或夸大内容，应反馈。

Suggested Chinese onboarding copy:

```text
这次 beta 只测试“AI 外贸员帮你找候选客户、做深度背调、写开发信草稿”。
系统不会自动发送邮件，也不会帮你找私人邮箱或手机号。
所有候选客户和 AI 内容都需要你人工确认后再使用。
```

## 9. Feedback collection plan

反馈表建议按一次完整体验收集。每个用户最多 10-15 分钟。

### Product profile

- 填写是否容易？
- 哪些字段不知道怎么填？
- AI 是否理解产品？
- 产品卖点是否被提取准确？
- 目标市场是否清楚？
- 产品画像结果是否需要大量修改？

### Candidate discovery

- 候选客户是否像真实买家？
- 行业匹配度如何？
- 国家匹配度如何？
- 是否出现明显供应商/同行误判？
- 是否出现目录页、文章页、博客页噪音？
- 候选客户数量够不够？
- match reason 是否有帮助？

### Company research

- 是否看得懂？
- 是否有用？
- 是否说明了风险？
- 是否有不实/夸大？
- 是否帮助判断要不要开发？
- 是否能看出它是“未验证，需要人工确认”？
- 来源链接是否足够辅助判断？

### Outreach draft

- 英文是否自然？
- 是否像真人写的？
- 是否太模板化？
- 是否适合复制修改？
- 是否有夸大/骚扰感？
- 是否暗示对方已经采购？
- 是否明确不会自动发送？
- 是否需要更短版本、WhatsApp 版本或中文解释？

### UX

- 新手是否知道下一步？
- 页面是否卡住？
- 按钮是否清楚？
- 是否有不理解的词？
- 是否需要中文帮助提示？
- 是否知道怎么返回候选客户列表？
- 是否知道怎么人工复制开发信？

### Safety

- 是否以为系统已经发邮件？
- 是否看到私人邮箱/电话？
- 是否看到未经验证的断言？
- 是否误以为客户已确认采购意向？
- 是否看到敏感 provider/API 信息？

### Business

- 是否愿意继续用？
- 如果收费，愿意为什么付费？
- 更想要更多候选、更多背调，还是更多开发信？
- 最想补充什么功能？
- 这个工具像不像“雇佣一个 AI 外贸员”？

## 10. Success metrics

### Activation

目标：

- 80% beta 用户能完成产品画像。
- 70% 能生成至少 1 个候选客户。
- 60% 能生成至少 1 次深度背调。
- 50% 能生成至少 1 封开发信草稿。

### Quality

目标：

- packaging / LED 候选客户人工可用率 >= 30%。
- 深度背调用户认为“有用”比例 >= 60%。
- 开发信草稿用户认为“可修改后使用”比例 >= 60%。
- spammy / 夸大投诉 = 0。
- verified buyer / purchase intent 错误声称 = 0。
- 明显供应商/同行误判需记录并低于可接受阈值。

### Safety

必须为 0：

- 自动发送邮件。
- `OutreachMessage` 创建。
- 私人邮箱/手机号保存。
- 网站抓取/爬取。
- secret leak。
- 普通客户误用高级功能。
- prompt / raw provider response 泄露。

### Cost

目标：

- 每个 beta 用户 AI / 搜索成本可控。
- Brave query 不超过 daily cap。
- MiMo usage 可追踪。
- Ledger 完整。
- Provider failure rate 可解释。

### UX

目标：

- 主要路径无 500。
- 用户能理解“未验证”。
- 用户能理解“不会自动发送”。
- 用户能手动复制开发信。
- 用户能知道下一步是人工确认和人工发送。

## 11. Operating checklist

### Before beta

- Production health `/health/live` returns 200。
- Production health `/health/ready` returns 200。
- `alembic_version` is correct for deployed tag。
- `tenant_product_profiles` exists。
- `target_customer_candidates` exists。
- `candidate_research_reports` exists。
- `candidate_outreach_drafts` exists。
- `ai_usage_ledger` exists。
- Acquisition provider disabled by default。
- Global AI provider configured only through approved admin path。
- Beta tenant selected and recorded。
- AI enabled only for beta tenant。
- Acquisition provider configured only if needed。
- Quotas configured。
- SQLite backup created。
- Emergency disable steps documented。
- User guide and feedback form prepared。
- Operator knows where to check logs and ledger。

### During beta

- Check logs daily。
- Check `ai_usage_ledger` daily。
- Check acquisition provider run records daily if Brave is enabled。
- Check candidate quality for each user。
- Check no email sending occurred。
- Check no `OutreachMessage` was created by candidate draft flow。
- Check no private email/phone stored in candidate/research/draft fields。
- Collect user feedback after each session。
- Record bugs with reproduction steps。
- Turn off provider if not actively testing。

### After beta

- Disable beta access if needed。
- Disable acquisition provider if testing is complete。
- Summarize feedback。
- Categorize issues:
  - blocker
  - safety
  - quality
  - UX polish
  - future feature
- Decide:
  - continue beta
  - polish
  - expand industry
  - add provider
  - pause

## 12. Emergency rollback / kill switch

### Kill switches

Use the smallest effective switch first:

1. Disable acquisition provider。
2. Disable tenant AI for affected beta tenant。
3. Lower tenant quotas to 0。
4. Disable global AI if provider-level safety issue exists。
5. Remove beta tenant access if account misuse exists。
6. Roll back to previous tag if app bug causes repeated 500s or data corruption risk。
7. Leave additive tables intact unless manual approval to drop exists。

### Emergency triggers

Trigger immediate stop if any of these occur:

- Email sent unexpectedly。
- `OutreachMessage` created unexpectedly from candidate draft flow。
- Private email/phone stored。
- API key leak。
- Prompt/full response/raw provider response leak。
- Ordinary customer can access beta-only feature。
- Repeated 500s on core path。
- AI produces unsafe verified buyer / purchase intent claims。
- Cost spike or provider usage exceeds cap。
- Website crawling or scraping path is discovered。

### Rollback posture

- Prefer disabling providers and tenant AI over dropping data。
- Keep additive tables unless there is explicit rollback approval。
- Preserve logs and ledger for incident analysis。
- If rolling back app tag, verify DB migration compatibility before downgrade。

## 13. Safety and legal wording

### Chinese user-facing wording

Use these in beta guide, onboarding notes, or candidate detail help copy:

```text
AI 结果仅供参考，需要人工确认。
系统不会自动发送邮件。
开发信只是草稿，发送前请自行修改确认。
候选客户未验证，不代表对方一定是买家。
不要声称对方已有采购意向，除非你已人工确认。
系统不会保存或生成私人邮箱/手机号为可信字段。
Beta 期间功能和结果质量可能变化。
```

### English draft disclaimer

Every generated outreach draft should retain equivalent meaning:

```text
Draft only. Not sent.
AI-generated content is for reference and requires manual confirmation.
Do not claim confirmed purchasing intent unless you have verified it yourself.
```

### Operator wording

Operators must not promise:

- guaranteed buyers
- verified importers
- confirmed purchase intent
- private contact data
- automatic email sending
- customs data
- LinkedIn contact discovery

## 14. Data / ledger monitoring

Daily checks:

- Count beta tenant AI ledger rows by feature:
  - `product_profile_extraction`
  - `target_customer_plan_generation`
  - `target_customer_candidate_matching`
  - `basic_search_strategy_generation`
  - `pasted_search_result_parsing`
  - `candidate_company_research`
  - `candidate_outreach_draft`
- Count statuses:
  - `success`
  - `failed`
  - `disabled`
  - `blocked_quota`
- Confirm `credits_charged = 0` if beta pricing remains free.
- Confirm failures have safe `error_code`.
- Confirm no raw prompt/response is stored.
- Confirm no provider secret is visible to tenant.

Recommended SQL checks:

```sql
SELECT feature_name, status, COUNT(*), SUM(credits_charged)
FROM ai_usage_ledger
WHERE tenant_id = '<beta_tenant_id>'
GROUP BY feature_name, status;

SELECT COUNT(*)
FROM candidate_research_reports
WHERE tenant_id = '<beta_tenant_id>';

SELECT COUNT(*)
FROM candidate_outreach_drafts
WHERE tenant_id = '<beta_tenant_id>';
```

Safety spot checks:

```sql
SELECT COUNT(*)
FROM candidate_outreach_drafts
WHERE tenant_id = '<beta_tenant_id>'
  AND (body LIKE '%@%' OR body GLOB '*[0-9][0-9][0-9]*');
```

The phone/email SQL is only a coarse spot check. Manual review is still required.

## 15. Risks and mitigations

### Risk: Candidate quality varies by industry

Mitigation:

- Limit beta to packaging / LED.
- Keep hardware / metal fittings closed.
- Use manual candidate quality feedback after each session.
- Stop or tune if usable candidate rate < 30%.

### Risk: User believes output is verified

Mitigation:

- Visible “未验证” copy.
- User guide repeats manual confirmation.
- Outreach draft disclaimer says draft only and not sent.
- Success metrics require verified buyer / purchase intent false claims = 0.

### Risk: User expects automatic email sending

Mitigation:

- Do not add send button.
- Do not create `OutreachMessage`.
- Explain manual copy workflow before beta.
- Safety feedback asks whether user thought email was sent.

### Risk: Private contact data leakage

Mitigation:

- No enrichment features in beta.
- No social scraping.
- No website body fetch.
- Daily spot check candidate/research/draft fields.
- Stop beta if private email/phone is stored.

### Risk: Provider cost spike

Mitigation:

- Acquisition provider disabled by default.
- Daily spend cap.
- Low query/result limits.
- Tenant quotas.
- Daily ledger/provider usage review.

### Risk: MiMo output quality regresses

Mitigation:

- Start with 1-3 trusted users.
- Capture examples.
- Keep unsafe/hallucinated claim threshold at 0.
- Disable global AI or tenant AI if unsafe output repeats.

### Risk: SQLite low-memory deployment friction

Mitigation:

- Limit to 1-3 users.
- Avoid concurrent public beta.
- Daily SQLite backup.
- Verify tables exist after deploy.
- Plan PostgreSQL migration before broader launch.

### Risk: Scope creep into unsupported channels

Mitigation:

- Do not implement Qwen/MiMo Web Search, SerpAPI, Maps, B2B, customs, social scraping in this beta.
- Keep beta feedback categorized as future feature, not immediate implementation.
- Require a new approved BLOCK for any new feature.

## 16. Decision: code needed or no-code beta

Decision:

```text
SMALL_POLISH_RECOMMENDED
```

Rationale:

- The core beta path can proceed with existing v1.1.0-alpha.10 functionality and manual tenant gating.
- No new feature code is required to start a 1-3 user packaging / LED beta if operators can manually configure tenant AI, provider settings, and quotas.
- However, before inviting non-internal users, small no-risk polish is recommended:
  - beta user guide page or shareable doc
  - visible beta scope wording for packaging / LED only
  - feedback form link
  - operator checklist template
  - optional beta badge/copy that says “不会自动发送邮件”

Not required before first internal/familiar beta:

- new migration
- new provider
- new route
- new AI feature
- new email sending feature
- new scraping/enrichment feature

Blocked conditions:

- If alpha.11 / alpha.11B evidence cannot be produced for audit.
- If production table existence for `candidate_research_reports` or `candidate_outreach_drafts` is not verified.
- If ordinary tenants can access beta provider/AI unexpectedly.
- If any automated email sending occurs from the candidate draft path.

## 17. Acceptance criteria

This plan is ready when:

- beta scope is limited to packaging / LED.
- hardware / metal fittings are excluded.
- no automatic email sending is allowed.
- no `OutreachMessage` creation is allowed.
- no private email/phone enrichment is allowed.
- no crawling/scraping is allowed.
- tenant gating is documented.
- quotas are documented.
- feedback form structure is documented.
- success metrics are documented.
- operating checklist is documented.
- emergency shutoff is documented.
- safety/legal wording is documented.
- data/ledger monitoring is documented.
- decision is made on whether code polish is required before beta.

Recommended beta decision:

```text
Proceed with a 1-3 user packaging / LED limited beta after operator readiness checks pass.
Do not expand industries or add new providers in alpha.12.
Do not present this as a public beta.
```
