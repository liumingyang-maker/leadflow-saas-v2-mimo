# V1.1.0 Alpha 10 Outreach From Company Research MVP Plan

## 1. Goal

v1.1.0-alpha.10 的目标是实现第一版“基于候选公司深度背调生成 AI 开发信草稿”。

用户在候选客户详情页 / 深度背调报告页点击：

```text
生成 AI 开发信
```

系统基于已确认的产品记忆、候选客户资料、alpha.9 深度背调报告、来源片段、积极信号、风险信号和建议开发信切入角度，生成一封英文开发信草稿。

alpha.10 只生成草稿，不发送邮件，不创建 `OutreachMessage`，不连接邮箱，不做 sequence，不做自动 follow-up。

## 2. Why now

当前产品主线是：

```text
产品记忆 → 找客户 → 候选过滤评分 → AI 深度背调
```

alpha.9 让用户能判断“这个候选公司是否值得继续看”。alpha.10 补上下一步：

```text
我应该如何开口？
```

这符合“火客雷达 = 雇佣一个 AI 外贸员”的定位。AI 外贸员不仅找客户和研究客户，还应帮助用户写出一封可人工复制、人工确认、人工发送的英文开发信。

现有代码中已有 lead-based AI outreach draft，但该路径服务于 `/leads/<lead_id>/outreach`，与发送表单和 `OutreachMessage` 同页存在。alpha.10 应避免复用发送路径，防止 scope creep 到邮件发送系统。

## 3. Scope

alpha.10 只做 AI 开发信草稿 MVP：

1. 在 candidate detail / research report card 下方增加 `生成 AI 开发信` 入口。
2. 要求候选客户已有 completed `candidate_research_reports`。
3. 使用 tenant product profile + target customer candidate + completed research report 生成英文草稿。
4. 保存 sanitized draft-only 结构化结果。
5. 在同一候选详情页展示 latest draft card。
6. 遵守 global AI gating、tenant AI gating、quota、ledger。
7. alpha 阶段 `credits_charged=0`，但 ledger 记录 estimated usage。
8. 失败不扣费。
9. 用户可以复制草稿，后续版本再做更完整复制 UX。

Draft should include:

- subject
- body
- short_body
- follow_up_angle
- personalization_notes
- confidence_note
- disclaimer

Language:

- Default English.
- Future versions may support Chinese, Spanish, or other localized drafts.

Tone:

- professional
- concise
- not spammy
- not exaggerated
- not claiming verified intent
- suitable for SOHO / small factory foreign trade users

Suggested feature name:

```text
candidate_outreach_draft
```

Suggested user-facing package wording:

```text
3 封 AI 开发信
```

Future production price:

```text
3 credits / draft
```

Alpha behavior:

```text
credits_charged = 0
```

## 4. Out of scope

alpha.10 明确不做：

- no email sending
- no platform SMTP sending for candidate drafts
- no mailbox connection
- no Gmail / Outlook integration
- no `OutreachMessage` creation
- no email sequence
- no bulk sending
- no automatic follow-up
- no contact enrichment
- no private email or phone generation
- no private email or phone storage
- no website crawling
- no webpage body fetching
- no browser automation
- no LinkedIn / Facebook / WhatsApp / Telegram scraping
- no B2B directory scraping
- no customs data
- no claim that the company is verified
- no claim that procurement intent is verified
- no claim that a contact person is confirmed
- no full prompt storage
- no full AI response storage
- no reasoning_content storage
- no raw provider response storage

## 5. User journey

### Main flow

1. 用户完成产品画像。
2. 用户通过搜索得到 target customer candidates。
3. 用户对候选客户生成 AI 深度背调。
4. 用户查看 completed 深度背调报告。
5. 用户点击 `生成 AI 开发信`。
6. 系统检查：
   - login
   - tenant owns candidate
   - tenant owns research report
   - global AI enabled / provider configured
   - tenant AI enabled
   - quota available
7. 系统基于 product profile + candidate + research report 生成英文开发信草稿。
8. 系统保存 draft-only 记录并显示 draft card。
9. 用户人工复制内容，人工确认后自行发送。

### If no completed research report exists

Block draft generation and show:

```text
请先生成 AI 深度背调
```

Reason: alpha.10 的核心价值是“从深度背调到开发信”。没有 research report 时直接生成会更泛，容易回退成普通模板邮件。

### If a completed draft already exists

Show latest draft.

MVP can disable regeneration or show a secondary `重新生成` only after the same AI gating and quota checks. Recommended alpha.10 implementation: show existing draft and skip regeneration to keep cost and prompt behavior predictable.

### If research confidence is low

Allow draft generation, but include uncertainty:

```text
This draft is based on limited public candidate information. Please verify the company and product fit before sending.
```

## 6. Data model decision

Recommendation: add a new draft-only table.

Do not reuse `OutreachMessage` because:

- `OutreachMessage` represents sendable/sent outreach state.
- Existing lead outreach UI includes `Send` behavior.
- alpha.10 explicitly must not send email or create outbound message records.
- Candidate drafts may exist before a candidate is added to CRM as a Lead.

Recommended migration:

```text
0016_candidate_outreach_drafts
```

Recommended table:

```text
candidate_outreach_drafts
```

Fields:

- `id`
- `tenant_id`
- `candidate_id`
- `research_report_id`
- `status`
- `provider`
- `ai_model`
- `language`
- `tone`
- `subject`
- `body`
- `short_body`
- `follow_up_angle`
- `personalization_notes_json`
- `sources_json`
- `ai_usage_ledger_id`
- `error_code`
- `created_at`
- `updated_at`

Status values:

```text
completed
failed
```

Language values for alpha.10:

```text
en
```

Tone default:

```text
professional_concise
```

JSON fields should use `Text` containing JSON strings for SQLite compatibility.

Indexes:

- `tenant_id`
- `candidate_id`
- `research_report_id`
- `status`
- `created_at`

Foreign keys:

- `tenant_id -> tenants.id`
- `candidate_id -> target_customer_candidates.id`
- `research_report_id -> candidate_research_reports.id`
- nullable `ai_usage_ledger_id -> ai_usage_ledger.id`

Do not store:

- full prompt
- full response
- reasoning_content
- raw provider response
- private email
- private phone
- private personal contact data

## 7. AI / provider flow

Business logic must not call MiMo/OpenAI directly.

Required path:

```text
routes -> service layer -> app/modules/ai/service.py -> app/integrations/ai/*
```

Suggested AI service function:

```text
generate_candidate_outreach_draft(...)
```

Suggested prompt builder:

```text
build_candidate_outreach_draft_prompt(...)
```

Inputs to AI:

- tenant product profile JSON
- candidate metadata
- candidate company domain/source URL
- completed candidate research report
- report source snippets
- buyer signals
- risk signals
- suggested outreach angle
- product advantages / selling points
- requested language: English
- requested tone: professional concise

Prompt output should be strict JSON:

```json
{
  "subject": "",
  "body": "",
  "short_body": "",
  "personalization_notes": [],
  "follow_up_angle": "",
  "confidence_note": "",
  "disclaimer": "Draft only. Not sent. Please verify before sending."
}
```

Prompt rules:

- Use only supplied product memory, candidate metadata, research report, and source snippets.
- Do not invent facts.
- Do not claim the company is verified.
- Do not claim current buying intent.
- Do not claim a confirmed contact person.
- Do not include private emails or phone numbers.
- Do not mention scraped or hidden sources.
- Keep the email concise.
- Avoid spammy language.
- Avoid excessive hype.
- Avoid fake familiarity.
- Use uncertainty when evidence is weak.
- Return strict JSON only.

Validation:

- Malformed JSON -> failed draft + failed ledger + user-friendly error.
- Missing optional fields -> normalize to empty strings/arrays.
- Subject and body are required for completed drafts.
- Strip email-like strings and phone-like strings before storing.
- Cap all text lengths.

## 8. Routes

Recommended MVP routes:

```text
POST /collection/candidates/<candidate_id>/outreach-draft
GET  /collection/candidates/<candidate_id>/outreach-draft
```

The GET route can redirect to:

```text
/collection/candidates/<candidate_id>#outreach-draft
```

Candidate detail page should show the latest completed draft inline.

Alternative route if implementation wants explicit report binding:

```text
POST /collection/candidates/<candidate_id>/research/<report_id>/outreach-draft
```

MVP recommendation:

- Use candidate id route.
- Service resolves latest completed research report owned by same tenant.
- If no completed report exists, block with `请先生成 AI 深度背调`.

Behavior:

- login required
- candidate must belong to tenant
- latest completed research report must belong to same tenant and candidate
- no completed research report -> no provider call
- AI disabled -> no provider call
- tenant AI disabled -> no provider call
- quota blocked -> no provider call
- provider failure -> safe error
- existing completed draft -> show latest draft

Error copy:

```text
AI 功能暂未开启
额度不足
系统繁忙，请稍后重试
请先生成 AI 深度背调
```

## 9. UI

Use the existing Signal Workspace style:

- quiet B2B workspace
- existing `lf-panel`, `lf-grid`, `lf-actions`, `lf-alert`, `lf-badge`
- no purple AI gradients
- no decorative animation
- visible keyboard focus through existing CSS

Candidate detail / research report card additions:

Button:

```text
生成 AI 开发信
```

Draft card sections:

1. Subject
2. Body
3. Short version
4. Follow-up angle
5. Personalization notes
6. Confidence note
7. Disclaimer

Visible safety copy:

```text
这是草稿，不会自动发送
发送前请人工确认
AI 不会保存或生成私人邮箱/手机号
不要声称对方已有采购意向，除非你已人工确认
```

Do not add:

- send button
- SMTP settings
- mailbox connection
- sequence controls
- automatic follow-up controls

Copy button:

- Optional in alpha.10.
- If added, it should only copy draft text client-side.
- It must not send email or create any outbound message record.

States:

- no research report: show `请先生成 AI 深度背调`
- no draft: show `生成 AI 开发信`
- generating: normal POST submit; future HTMX loading can be added
- completed draft: show draft card
- failed: show `系统繁忙，请稍后重试`
- AI disabled: show `AI 功能暂未开启`
- quota blocked: show `额度不足`

## 10. Credit / ledger behavior

Suggested feature name:

```text
candidate_outreach_draft
```

Alpha behavior:

- `credits_estimated = 3`
- `credits_charged = 0`
- success charges 0
- provider failure charges 0
- malformed response charges 0
- disabled tenant charges 0
- quota block charges 0
- no completed research report charges 0 and does not write provider-call ledger unless product wants an audit ledger

Future production behavior:

- 3 credits / draft
- regenerate may cost 3 credits
- first draft from a completed research report may be included in package trials

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
- raw provider response
- API key
- Authorization header

## 11. Access control

Required:

- tenant login required
- candidate belongs to current tenant
- research report belongs to current tenant
- research report belongs to candidate
- draft belongs to current tenant
- draft belongs to candidate
- no cross-tenant candidate/report/draft access
- tenant AI enabled required
- global AI enabled/provider configured required
- quota required

If candidate missing:

```text
404
```

If candidate belongs to another tenant:

```text
404
```

If research report belongs to another tenant or candidate:

```text
404
```

Normal tenant users cannot see:

- provider API key
- provider base URL
- raw provider response
- other tenant reports
- other tenant drafts

## 12. Safety / privacy

Hard boundaries:

- no email sending
- no `OutreachMessage`
- no SMTP usage
- no mailbox connection
- no sequence automation
- no automatic follow-up
- no website crawling
- no webpage body fetching
- no browser automation
- no social scraping
- no B2B directory scraping
- no customs scraping
- no private email / phone enrichment
- no private personal data storage
- no verified buyer claim
- no purchase intent guarantee
- no confirmed contact person claim

Sanitization:

- strip email-like strings
- strip phone-like strings
- strip private contact-like fields
- cap subject/body/short body/follow-up fields
- store only structured draft fields
- store only source summaries already present in candidate/research metadata

Draft language:

- must say or imply draft-only
- must avoid “I saw that you are buying...”
- must avoid “as your verified importer/distributor...”
- must use soft language such as “may be relevant” or “could be useful” when evidence is inferred
- must encourage human review before sending

## 13. Error handling

### No completed research report

No provider call.

User sees:

```text
请先生成 AI 深度背调
```

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

### Tenant AI disabled

No provider call.

User sees:

```text
AI 功能暂未开启
```

Ledger:

```text
status=disabled
error_code=tenant_ai_disabled
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

Create failed draft or return failure consistently.

Ledger:

```text
status=failed
error_code=malformed_json
credits_charged=0
```

### Existing completed draft

Show latest draft.

Regeneration should be explicit and can be deferred.

## 14. Tests

Add tests, likely:

```text
tests/test_candidate_outreach_draft.py
```

Routes / access:

- draft route requires login
- candidate must belong to tenant
- cross-tenant candidate access blocked
- missing candidate returns 404
- no completed research report blocks and does not call provider
- research report must belong to same tenant and candidate

AI gating:

- global AI disabled blocks provider call
- tenant AI disabled blocks provider call
- quota blocked blocks provider call
- provider failure shows safe error and charges 0
- malformed JSON shows safe error and charges 0
- successful draft creates completed draft

Ledger:

- success writes ledger
- failure writes ledger
- alpha `credits_charged = 0`
- blocked quota charges 0
- disabled charges 0

Storage safety:

- no full prompt stored
- no full response stored
- no reasoning_content stored
- no raw provider response stored
- no private email stored
- no phone stored
- sources_json contains only sanitized source summaries

No sending:

- no `OutreachMessage` created
- no email sent
- no SMTP usage
- no send button in candidate draft UI

UI:

- candidate detail displays `生成 AI 开发信` when completed research exists
- candidate detail does not display draft CTA when research is missing, or shows blocked message
- draft card displays subject/body
- draft card displays `不会自动发送`
- manual review disclaimer appears
- no send button appears in candidate detail draft section

Regression:

- candidate research tests pass
- advanced web search tests pass
- AI control tests pass
- existing lead AI outreach draft tests pass
- navigation/i18n tests pass

Suggested validation commands:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .

PYTHONPATH=$PWD .venv/bin/python -m pytest -q \
  tests/test_candidate_outreach_draft.py \
  tests/test_candidate_company_research.py \
  tests/test_advanced_web_search_channel.py \
  tests/test_acquisition_channel_hub.py \
  tests/test_target_customer_discovery.py \
  tests/test_ai_control_plane.py \
  tests/test_ai_outreach_draft.py \
  tests/test_i18n.py \
  tests/test_navigation.py

PYTHONPATH=$PWD .venv/bin/python -m pytest -q -k "not playwright and not browser_acceptance"

git diff --check
```

Security grep:

```bash
grep -RInE "requests\.|httpx|urlopen|urllib.request|BeautifulSoup|selenium|playwright|scrap|crawl|customs|linkedin|facebook|whatsapp|telegram|SMTP|send_email|OutreachMessage" \
  app/integrations/acquisition app/modules/acquisition app/modules/jobs app/templates/collection app/templates/admin app/modules/ai app/integrations/ai tests || true

git diff | grep -iE "tp-|sk-|Authorization:|Bearer |SMTP_PASSWORD|SECRET_KEY|TENANT_SECRET_KEY|INBOUND_TOKEN_KEY|OUTREACH_SIGNING_KEY" || true
```

Allowed hits:

- existing provider code
- existing tests
- explicit tests that assert `OutreachMessage` is not created
- UI copy saying email is not sent

Forbidden:

- real API key
- real Authorization header
- real SMTP password
- real secret keys
- new SMTP/send path for candidate drafts

## 15. Migration / deployment notes

If using the recommended new table:

Migration:

```text
0016_candidate_outreach_drafts
```

Migration should:

- create `candidate_outreach_drafts`
- use `Text` columns for JSON
- create indexes on tenant_id, candidate_id, research_report_id, status, created_at
- add FK to `target_customer_candidates.id`
- add FK to `candidate_research_reports.id`
- add FK to `tenants.id`
- optionally add nullable FK to `ai_usage_ledger.id`
- not mutate existing tables

Downgrade:

- drop indexes
- drop table

Local migration gate:

```bash
rm -f /tmp/leadflow-alpha10-outreach-drafts.sqlite3

DATABASE_URL=sqlite:////tmp/leadflow-alpha10-outreach-drafts.sqlite3 \
APP_ENV=testing \
SECRET_KEY=test-secret \
TENANT_SECRET_KEY=test-tenant-secret \
INBOUND_TOKEN_KEY=test-inbound-secret \
OUTREACH_SIGNING_KEY=test-outreach-secret \
REDIS_URL=redis://127.0.0.1:6379/15 \
LOWMEM_ALLOW_SQLITE=true \
PYTHONPATH=$PWD .venv/bin/alembic upgrade head

DATABASE_URL=sqlite:////tmp/leadflow-alpha10-outreach-drafts.sqlite3 \
APP_ENV=testing \
SECRET_KEY=test-secret \
TENANT_SECRET_KEY=test-tenant-secret \
INBOUND_TOKEN_KEY=test-inbound-secret \
OUTREACH_SIGNING_KEY=test-outreach-secret \
REDIS_URL=redis://127.0.0.1:6379/15 \
LOWMEM_ALLOW_SQLITE=true \
PYTHONPATH=$PWD .venv/bin/alembic downgrade -1

DATABASE_URL=sqlite:////tmp/leadflow-alpha10-outreach-drafts.sqlite3 \
APP_ENV=testing \
SECRET_KEY=test-secret \
TENANT_SECRET_KEY=test-tenant-secret \
INBOUND_TOKEN_KEY=test-inbound-secret \
OUTREACH_SIGNING_KEY=test-outreach-secret \
REDIS_URL=redis://127.0.0.1:6379/15 \
LOWMEM_ALLOW_SQLITE=true \
PYTHONPATH=$PWD .venv/bin/alembic upgrade head
```

Production deploy verification:

1. Backup SQLite.
2. Confirm current revision.
3. Run migration.
4. Verify table exists:

```sql
SELECT name FROM sqlite_master WHERE type='table' AND name='candidate_outreach_drafts';
```

5. Verify app starts.
6. Verify candidate detail page.
7. Verify draft generation with fake provider in non-production smoke.
8. Verify no send button, no `OutreachMessage`, no email sent.

Manual SQL fallback:

- Prepare reviewed SQL equivalent to the Alembic migration.
- Use only after backup exists, Alembic failure is confirmed, table absence is confirmed, and operator approval is given.

Rollback plan:

1. Disable AI provider.
2. Roll back app code.
3. Keep additive table if harmless.
4. Drop table only with explicit rollback approval and after confirming no useful draft records need retention.

## 16. Acceptance criteria

alpha.10 is done when:

- user can generate an outreach draft from a completed research report
- draft includes subject and body
- draft includes short version and follow-up angle
- draft is personalized using research report and product profile
- no email sent
- no `OutreachMessage` created
- no SMTP used
- no private email / phone stored
- no crawling / scraping
- no website body fetch
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
- no completed research report blocks draft generation
- visible `不会自动发送` disclaimer
- existing tests pass
- migration upgrade/downgrade works if new table is implemented

## 17. Risks and mitigations

### Risk: AI hallucinated personalization

Mitigation:

- prompt uses only product profile, candidate metadata, and completed research report
- draft includes confidence note
- UI says manual confirmation required
- no verified buyer or purchase intent claims

### Risk: Spammy email copy

Mitigation:

- prompt requires concise professional tone
- reject excessive hype and fake familiarity
- tests assert no “guaranteed”, “verified buyer”, or current purchase-intent wording

### Risk: User thinks system sent email

Mitigation:

- visible `这是草稿，不会自动发送`
- no send button in candidate draft UI
- no `OutreachMessage`
- no SMTP usage

### Risk: Accidental email-sending scope creep

Mitigation:

- draft-only table
- no reuse of `/leads/<lead_id>/outreach/send`
- tests assert no `OutreachMessage` and no send controls

### Risk: Private data leakage

Mitigation:

- strip email-like and phone-like strings
- do not enrich contact data
- do not store raw provider responses
- do not store full prompt or response

### Risk: Repeated regeneration cost abuse

Mitigation:

- alpha.10 can show latest draft and defer regeneration
- future regenerate requires explicit click and quota gate

### Risk: Weak research report creates generic email

Mitigation:

- require completed research report
- include confidence note
- use soft CTA and uncertainty language

### Risk: Misleading verified buyer claims

Mitigation:

- prompt forbids verified buyer/importer and purchase intent claims
- UI repeats manual confirmation warning
- tests scan draft output for forbidden wording

### Risk: SQLite migration friction

Mitigation:

- additive table only
- SQLite-compatible `Text` JSON
- local upgrade/downgrade/upgrade gate
- production table existence check
- manual SQL fallback prepared but not executed without approval
