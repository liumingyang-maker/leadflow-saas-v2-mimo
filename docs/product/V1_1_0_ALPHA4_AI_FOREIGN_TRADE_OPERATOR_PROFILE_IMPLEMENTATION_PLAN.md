# v1.1.0-alpha.4 AI 外贸员产品记忆实施计划

## 1. Product Objective

v1.1.0-alpha.4 的目标是建立“AI 外贸员产品记忆”。

在 AI 帮用户寻找客户之前，系统必须先理解用户卖什么、卖点是什么、适合哪些买家、应该用哪些英文关键词去搜索和触达。

alpha.4 只解决这个问题：

```text
用户输入公司和产品资料
→ AI 提取结构化产品记忆
→ 用户审核、编辑、确认
→ 保存 tenant 级产品资料
```

这一步是后续目标客户匹配、深度背调、开发信生成的基础。

## 2. User Flow

推荐 alpha.4 用户流程：

```text
first login / no product profile
→ prompt to /onboarding/product-profile
→ user inputs company/product text
→ user clicks “训练 AI 外贸员”
→ AI extracts structured product memory
→ user reviews/edits
→ user confirms
→ product memory saved
→ user can continue to workbench
```

首次引导建议不硬阻塞登录。

alpha.4 行为：

- 登录后如果 tenant 没有 confirmed product profile，在 workbench 或 onboarding 区域显示明确提示。
- 提示用户进入 `训练你的 AI 外贸员`。
- 提供 `稍后再说`。
- 不阻止用户访问 CRM、外联、设置等现有功能。

这样可以降低新用户阻力，同时让产品核心价值入口足够明显。

## 3. Routes

建议新增路由：

- `GET /onboarding/product-profile`
- `POST /onboarding/product-profile/extract`
- `POST /onboarding/product-profile/confirm`
- `GET /settings/product-profile`
- `POST /settings/product-profile/update`

这些路由符合当前 Flask + module blueprint style，也和现有 `/workbench`、`/settings`、`/leads/<id>/outreach` 的服务器渲染流程一致。

建议实现位置有两个可选方案：

1. `app/modules/accounts` 或新 `app/modules/onboarding`
   - 优点：贴近首次引导。
   - 缺点：AI 产品记忆后续也会被 settings、targets、outreach 使用，可能过早绑定 onboarding。

2. `app/modules/ai` 内提供 service，路由放在 `app/modules/settings` 或新 `app/modules/onboarding`
   - 推荐方向。
   - Provider 调用继续由 `app/modules/ai/service.py` 管控。
   - 产品记忆可被后续目标客户匹配和开发信复用。

推荐 alpha.4：

- AI 调用和 ledger 逻辑放在 `app/modules/ai/service.py` 或 `app/modules/ai/product_profile.py`。
- Onboarding 页面路由可放在新 `app/modules/onboarding/routes.py`，或者现有账号/页面模块中。
- Settings 入口放在现有 settings 模块。

最终实现前需确认具体模块位置。

## 4. Database Design

推荐新增 migration：

```text
migrations/versions/0012_tenant_product_profiles.py
```

新增表：

```text
tenant_product_profiles
```

字段：

- id
- tenant_id
- raw_company_intro
- raw_products
- raw_website_url
- raw_target_markets
- raw_advantages
- raw_certificates
- raw_moq
- raw_delivery_capacity
- raw_customer_countries
- extracted_profile_json
- status
- version
- last_extracted_at
- confirmed_at
- created_at
- updated_at

Status values:

- draft
- extracted
- confirmed
- failed

Version policy:

- alpha.4 使用 one active row per tenant。
- `version` 在重新提取或确认时递增。
- alpha.4 不做历史版本表。
- 未来如需要审计历史，可新增 `tenant_product_profile_versions`，但现在不做。

Compatibility:

- SQLite：使用 Text 存储 raw 字段和 JSON 字符串，兼容低内存 beta。
- PostgreSQL：第一版仍可用 Text；未来可考虑 JSONB，但 alpha.4 不依赖。
- Downgrade：删除 `tenant_product_profiles`。
- 不需要从现有表迁移数据。

约束建议：

- `tenant_id` 唯一，保证一个 tenant 一个 active profile。
- `status` 使用 check constraint。
- 所有读写必须 tenant scoped。

## 5. Extracted JSON Schema

`extracted_profile_json` 建议结构：

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
- moq_summary
- certificates
- delivery_capacity
- factory_type
- ideal_buyer_profile
- oem_odm_capability
- price_positioning

原则：

- 字段数量保持有限。
- 不把它做成完整 PIM 系统。
- 面向后续目标客户匹配、深度背调和开发信生成。
- 用户确认后的 JSON 才能作为后续 AI 默认上下文。

建议类型：

- 多值字段用 array，例如 `product_keywords_en`、`buyer_types`。
- 摘要字段用 string，例如 `product_summary_en`、`moq_summary`。
- 不确定值使用 empty array 或 `"unknown"`。

## 6. AI Prompt Design

Prompt rules:

- 只使用用户提供的公司和产品字段。
- 不编造证书。
- 不编造 MOQ。
- 不编造已有客户国家。
- 不编造交货能力。
- 如果未知，返回 empty array 或 `"unknown"`。
- 输出 strict JSON。
- UI 可显示中文标签，但内部 JSON keys 保持 English。
- 不存储完整 prompt。
- 不存储完整 raw AI response。
- 不存储完整 reasoning_content。
- 只保存解析后的结构化 profile。

失败处理：

- JSON parsing 失败：显示 `系统繁忙，请稍后重试`。
- 写 `failed` ledger。
- 不保存 raw response。
- 不扣 credits。

建议 prompt 输出要求：

```text
Return only valid JSON.
No markdown.
No explanation.
Use the exact keys provided.
Use empty arrays or "unknown" when information is not provided.
Do not infer certifications, MOQ, customer countries, or delivery capacity unless explicitly provided.
```

## 7. AI Service Integration

集成原则：

- 业务路由不得直接调用 MiMo/OpenAI-compatible provider。
- Provider 调用仍必须经过 `app/integrations/ai/*`。
- 业务入口应调用 `app/modules/ai/service.py`，或一个小的 dedicated product-profile service。

必须遵守当前 AI Control Plane：

- global AI enabled
- tenant AI enabled
- provider configured
- no provider/base_url/api_key exposed to tenant

Ledger behavior:

- Disabled tenant:
  - no provider call
  - status `disabled`
  - credits_charged `0`

- Provider failure:
  - status `failed`
  - credits_charged `0`

- Success:
  - status `success`
  - credits_charged `0` in alpha.4

alpha.4 决策：

- 首次产品记忆提取 0 credits。
- Regeneration 也是 0 credits。
- 两者都必须写 `ai_usage_ledger`。
- 可使用 feature_name：`product_profile_extraction`。

## 8. UI Design

Page title:

```text
训练你的 AI 外贸员
```

Subtitle:

```text
告诉 AI 你卖什么，它会帮你总结产品卖点、买家类型和搜索关键词。
```

Input fields:

- 公司介绍
- 主营产品
- 官网 URL
- 目标市场
- 工厂优势
- 证书资质
- MOQ
- 交货能力
- 已有客户国家

Website hint:

```text
如果官网信息很重要，请复制主要公司介绍或产品介绍到上面的文本框。alpha.4 暂不自动抓取网页。
```

Output/review sections:

- 产品关键词
- 英文关键词
- 英文产品摘要
- 产品卖点
- 适合行业
- 买家类型
- 目标国家
- 搜索关键词
- 排除关键词
- 开发信角度
- MOQ/证书/交付能力摘要

Actions:

- 训练 AI 外贸员
- 保存并确认
- 重新生成
- 稍后再说

UI constraints:

- 不做大首页重构。
- 使用现有 shell、form、panel、button 组件。
- 移动端输入区域必须可用。
- AI 输出必须明确提示需要用户审核。
- 不给普通用户暴露 JSON editor。

## 9. Settings Integration

Settings 增加入口：

```text
AI 外贸员产品记忆
```

Settings 能力：

- 查看当前 confirmed product profile。
- 编辑 raw fields。
- 重新运行 extraction。
- 确认 updated profile。
- 不向普通用户暴露 JSON editor。
- 不暴露 provider/base_url/api_key。

Settings 页面应强调：

```text
AI 生成的建议可能不准确，请确认后再用于找客户和开发信。
```

## 10. i18n

需要 zh-CN/en-US key parity。

建议 keys：

- Train your AI foreign trade operator
- Tell AI what you sell
- Company introduction
- Main products
- Website URL
- Target markets
- Factory advantages
- Certificates
- MOQ
- Delivery capacity
- Existing customer countries
- Product memory
- Train AI
- Save and confirm
- Regenerate
- Maybe later
- System is busy, please try again later
- Product profile saved
- AI generated suggestions may be inaccurate. Please review and confirm.

默认语言仍是 zh-CN，en-US 保留。

## 11. Security And Privacy

alpha.4 安全边界：

- No file upload.
- Sanitize text length.
- Limit input size.
- Website URL saved but not fetched.
- No full prompt stored.
- No full response stored.
- No full reasoning_content stored.
- No API key exposure.
- No provider/base_url exposed to tenant.
- User can edit AI result.
- AI output is not treated as verified fact.

建议输入限制：

- 每个长文本字段限制在合理长度，例如 5,000 到 10,000 chars。
- URL 字段只接受 http/https 或空值。
- 提交时进行 server-side validation。
- UI 提示不要输入密码、客户隐私、内部报价表等敏感信息。

## 12. Tests

计划测试：

- GET onboarding page requires login.
- Missing product profile shows onboarding entry.
- User can skip onboarding.
- Disabled tenant cannot call extraction provider.
- Disabled tenant writes disabled ledger.
- Enabled tenant can extract with fake provider.
- Parsed JSON saved.
- User can edit/confirm profile.
- Product profile is tenant-isolated.
- Website URL saved but not fetched.
- Failed provider shows `系统繁忙，请稍后重试`.
- Malformed JSON handled safely.
- No full prompt/response stored.
- `/settings/product-profile` requires login.
- i18n parity.
- Migration upgrade/downgrade.
- Existing auth/resend/navigation/outreach/AI tests still pass.

Additional recommended tests:

- Confirmed profile can be viewed in settings.
- Re-extraction increments version.
- Empty unknown fields do not crash review page.
- Tenant A cannot view or update Tenant B profile.
- Product profile extraction writes `ai_usage_ledger` with credits_charged `0`.

## 13. Migration Plan

Migration:

```text
migrations/versions/0012_tenant_product_profiles.py
```

Upgrade:

- Create `tenant_product_profiles`.
- Add indexes/unique constraint for tenant lookup.
- Add status check constraint.

Downgrade:

- Drop `tenant_product_profiles`.

Compatibility:

- SQLite compatible.
- PostgreSQL compatible.
- No data migration from existing tables.
- No change to existing AI quota/ledger schema.

## 14. Acceptance Criteria

alpha.4 is done when:

- Tenant can create product profile through onboarding.
- Fake/MiMo provider extracts structured memory.
- User can review/edit/confirm.
- Product memory saved per tenant.
- Settings can view/edit profile.
- Disabled tenant cannot call provider.
- Ledger records extraction attempt.
- No full prompt/response/reasoning_content saved.
- No website crawling occurs.
- Tests pass.
- Migration upgrade/downgrade works.

## 15. Open Decisions Before Implementation

Open decisions:

- Exact route module location.
- Whether profile extraction belongs under AI module or onboarding module.
- Whether onboarding prompt appears on workbench or redirects.
- Whether first extraction remains 0 credits after beta.
- How to handle repeated profile versions after alpha.4.
- How to display extracted arrays in editable UI.
- Whether website URL validation should reject non-http(s) values or save them as plain text with warning.
- Whether confirmed profile should be editable inline in settings or via the same onboarding form.

Recommended defaults for alpha.4:

- Route location: new onboarding route module plus AI service helper.
- Prompt behavior: workbench/onboarding prompt, not forced redirect.
- Credits: extraction and regeneration remain 0 credits for alpha.4.
- Versions: one active row, `version` increments, no history table.
- Editable arrays: render as newline-separated text fields, then serialize to arrays server-side.
