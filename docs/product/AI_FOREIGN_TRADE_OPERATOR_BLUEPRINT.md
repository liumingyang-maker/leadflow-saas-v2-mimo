# 火客雷达 AI 外贸员产品运作模型

## 1. Product Positioning

火客雷达的核心定位应从“AI CRM”或“线索管理工具”升级为：

```text
火客雷达 = 雇佣一个 AI 外贸员
```

这个定位比“AI CRM”更直接。目标用户不是为了管理客户而来，而是为了获得一个能帮他们理解产品、寻找海外买家、研究客户、生成开发信并辅助跟进的外贸执行角色。

它也比“AI 获客增长平台”更适合第一批用户。“增长平台”对 SOHO、小工厂、小外贸团队来说偏抽象；“AI 外贸员”更容易被理解为一个具体劳动力替代方案。

它更不同于普通线索管理工具。普通 CRM 只承接已有客户和线索，而火客雷达要先帮助用户回答：

```text
我卖什么？
谁可能买？
去哪里找？
怎么开口？
下一步怎么跟？
```

## 2. Target Users

第一批目标用户：

- SOHO foreign trade sellers
- small factories
- small export teams
- beginner foreign trade sellers

这些用户的典型痛点：

- 不知道如何用英文准确描述产品和卖点。
- 不知道去哪里寻找海外买家。
- 负担不起全职专业外贸业务员。
- 不会写英文开发信，或写出的内容缺乏个性化。
- 没有系统化客户跟进流程，客户容易丢失。
- 预算有限，但愿意为有效目标客户和高质量开发信付费。

## 3. Core Product Loop

核心产品闭环：

```text
User tells AI what they sell
→ AI extracts product memory
→ AI suggests buyer profile and search keywords
→ AI recommends target customers
→ user reviews customers
→ AI performs deep research if requested
→ AI writes personalized outreach email
→ user copies or manually sends
→ CRM tracks follow-up
```

中文表达：

```text
用户告诉 AI 自己卖什么
→ AI 提取产品记忆
→ AI 生成买家画像和搜索关键词
→ AI 推荐目标客户
→ 用户审核客户
→ 用户需要时触发深度背调
→ AI 生成个性化开发信
→ 用户复制或手动发送
→ CRM 记录跟进
```

CRM 是承接和跟进层，不是第一价值入口。第一价值入口应是“训练 AI 外贸员”和“让 AI 帮我找客户”。

## 4. First-Login Onboarding

首次登录页面名称：

```text
训练你的 AI 外贸员
```

alpha.4 输入字段：

- company introduction
- main products
- website URL
- target market
- factory advantages
- certificates
- MOQ
- delivery capacity
- existing customer countries

alpha.4 明确不支持：

- PDF upload
- image upload
- product catalog upload
- OCR
- multimodal parsing
- file storage

这些能力留到后续阶段。alpha.4 应先证明“文本产品资料 → AI 结构化产品记忆 → 用户确认保存”这条链路稳定可用。

## 5. AI Product Memory

核心概念：

```text
AI 外贸员产品记忆
```

推荐表：

```text
tenant_product_profiles
```

第一版字段建议：

- tenant_id
- raw_company_intro
- raw_products
- raw_website_url
- raw_target_markets
- raw_advantages
- extracted_profile_json
- status
- created_at
- updated_at

`extracted_profile_json` 建议字段：

- product_keywords_cn
- product_keywords_en
- product_categories
- selling_points_cn
- selling_points_en
- target_industries
- buyer_types
- target_countries
- search_keywords
- negative_keywords
- outreach_angles
- suggested_email_tone
- product_summary_en

后续功能如何使用产品记忆：

- target customer matching：基于产品关键词、行业、买家类型和目标国家生成搜索策略。
- deep research：结合目标客户资料判断产品匹配度、采购可能性和切入角度。
- outreach draft generation：生成更贴合产品卖点和目标客户背景的开发信。
- search keyword generation：生成英文搜索关键词、排除关键词和渠道查询词。

不应保存完整 prompt / response。可以保存用户确认后的结构化结果和原始输入字段。

## 6. Credits And Front-End Wording

后端可以继续统一使用 credits 记账。

前端面向第一批用户时，建议使用更直观的套餐文案：

```text
新用户赠送：
10 个目标客户匹配
3 封 AI 开发信
1 次深度背调体验
```

底层 credits 映射：

- target customer match: 1 credit each
- AI outreach email: 5 credits
- deep research: 5 credits
- regenerate email: 3 credits

扣费规则：

- success charges credits
- system failure does not charge
- insufficient quota does not call provider
- disabled tenant does not call provider

用户侧失败提示：

```text
系统繁忙，请稍后重试
```

后台仍应记录稳定 error_code，便于排查和成本分析。

## 7. Target Customer Matching

alpha.5 未来行为：

- 使用产品记忆生成 search keywords。
- 第一阶段可从 Google Search adapter、CSV import、manual add 开始。
- 不承诺“完美全球买家数据库”。
- 每个推荐客户展示：
  - company name
  - country
  - website
  - industry
  - source channel
  - match reason
- 用户可以将推荐客户加入 CRM。

明确边界：

```text
alpha.4 不实现真实目标客户匹配。
alpha.4 只创建 AI 外贸员产品记忆。
```

## 8. Lead Generation Channels

长期渠道架构：

- search engine channel
- map/local business channel
- B2B directory channel
- trade fair directory channel
- customs data channel
- social/public profile channel
- CSV import
- manual add

第一版优先：

- Google Search
- CSV import
- manual add

产品设计中可以保留未来渠道槽位，但不要一次性实现所有渠道。渠道越多，合规、成本、数据质量、失败重试和去重复杂度越高。

每条线索建议长期记录：

- source channel
- match reason
- confidence
- research status
- outreach draft status
- CRM stage

## 9. Deep Research

普通客户卡片作为匹配结果的基础展示，不额外扣费。

Basic card:

- company name
- country
- website
- source
- match reason

Deep research costs credits.

Deep research 输出：

- business summary
- buyer fit
- likely pain points
- product fit
- suggested outreach angle
- risk notes
- recommended email strategy

深度背调是真正节省外贸业务员时间的 AI 工作，应作为清晰的付费动作。

## 10. Outreach Email

Stage 1:

- AI generates email only.
- User copies or manually sends.
- No platform sending.

Stage 2:

- user connects own email.
- user confirms single email send.

Stage 3:

- email sequence and follow-up, future only.

硬边界：

- platform system email must not send customer outreach.
- no auto bulk sending.
- no auto sequence in early versions.
- no auto follow-up in early versions.

系统邮箱只用于注册验证、密码重置、系统通知。客户外联必须使用客户自己的邮箱、SMTP、OAuth 或独立发信域名，并且必须由用户确认发送。

## 11. Version Roadmap

```text
v1.1.0-alpha.4:
AI 外贸员首次引导 + 产品记忆

v1.1.0-alpha.5:
基于产品记忆生成目标客户画像 + fake/example/search results

v1.1.0-alpha.6:
真实目标客户匹配 + 加入 CRM

v1.1.0-alpha.7:
深度背调 + AI 开发信增强

v1.1.0-beta.1:
small real-user trial, cost/quality/speed validation
```

## 12. Risks And Constraints

- MiMo formal API access must be confirmed before paid production use.
- MiMo latency and cost may affect UX and pricing.
- Search API quota and cost must be measured before scaling target matching.
- SQLite is acceptable for low-concurrency beta but not strict high-concurrency quota enforcement.
- File upload security is postponed; PDF/image/catalog parsing should not enter alpha.4.
- Customs/social scraping has compliance and data-rights risks.
- Email sending has deliverability, compliance, unsubscribe, suppression, SPF/DKIM/DMARC and abuse risks.

## 13. Non-Goals For Alpha.4

alpha.4 explicitly does not include:

- PDF upload
- image upload
- product catalog parsing
- OCR
- automatic customer matching
- deep research
- email sending
- auto follow-up
- new channels
- large homepage redesign

alpha.4 should stay focused on:

```text
text product input → MiMo extraction → user review/edit → tenant product profile saved
```

## 14. Acceptance Criteria For Alpha.4

alpha.4 is acceptable when:

- first-login product profile page exists.
- user can submit product text and website URL.
- MiMo extracts structured product memory.
- user can review/edit/save extracted memory.
- profile is saved by tenant.
- profile can be viewed in settings.
- no provider call for disabled tenant.
- quota/ledger records extraction call.
- failure shows `系统繁忙，请稍后重试`.
- no full prompt/response stored.
- no key leakage.

Additional engineering expectations:

- tenant scoping is enforced on read/write.
- zh-CN is default and en-US remains available.
- existing auth, resend verification, outreach draft, quota, ledger, and tenant gating behavior must not regress.
