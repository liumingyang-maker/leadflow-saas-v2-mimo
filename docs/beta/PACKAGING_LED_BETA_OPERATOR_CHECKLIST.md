# Packaging / LED Beta Operator Checklist

Audience: beta 操作员 / MimoCode 运维执行 / 内测负责人。

Purpose: 用最小范围、低成本、可关闭的方式运行 packaging / LED 小范围 beta。

Hard boundaries:

- 不自动发送邮件。
- 不创建 `OutreachMessage`。
- 不连接邮箱。
- 不使用 SMTP 发送 beta 开发信。
- 不做群发。
- 不做自动 follow-up。
- 不补充私人邮箱/手机号。
- 不抓取网站。
- 不做 LinkedIn / Facebook / WhatsApp / Telegram scraping。
- 不做海关 / B2B / 地图扩展。
- 不新增国产 API 联网搜索 provider。
- 不扩大到 hardware / metal fittings 行业。

## 1. Before beta

Before inviting any user:

- [ ] Production version is `v1.1.0-alpha.10` or newer.
- [ ] `/health/live` returns 200.
- [ ] `/health/ready` returns 200.
- [ ] SQLite backup created.
- [ ] `tenant_product_profiles` table exists.
- [ ] `target_customer_candidates` table exists.
- [ ] `candidate_research_reports` table exists.
- [ ] `candidate_outreach_drafts` table exists.
- [ ] `ai_usage_ledger` table exists.
- [ ] Provider disabled by default.
- [ ] Beta tenant selected.
- [ ] Beta tenant is not ordinary public user.
- [ ] Beta tenant industry is packaging or LED.
- [ ] AI enabled only for beta tenant.
- [ ] Acquisition provider enabled only if needed.
- [ ] Acquisition provider query/result limits configured.
- [ ] Quotas configured.
- [ ] Feedback form prepared.
- [ ] User guide sent.
- [ ] Emergency shutoff steps prepared.
- [ ] Operator knows where logs are.
- [ ] Operator knows how to disable tenant AI.
- [ ] Operator knows how to disable acquisition provider.

## 2. Suggested beta quota

Recommended beta package:

- 10 target candidates.
- 3 AI company research reports.
- 3 AI outreach drafts.

Advanced web search:

- max 3-5 queries/day.
- max 5 results/query.
- no batch runs.
- no automatic retry.

Credit handling:

- `credits_charged` can remain 0 during beta.
- Ledger must record estimated usage through feature/status/provider/model/error code.
- Quota blocked means no provider call.
- Disabled tenant means no provider call.

## 3. During beta daily checks

Run these checks daily while beta is active:

- [ ] Health is 200/200.
- [ ] No 500 spikes.
- [ ] `ai_usage_ledger` records normal.
- [ ] No email sent unexpectedly.
- [ ] No `OutreachMessage` created by candidate draft path.
- [ ] No private email/phone saved in candidate/research/draft records.
- [ ] No crawling/scraping logs.
- [ ] Candidate quality reviewed.
- [ ] User feedback collected.
- [ ] Cost estimate reviewed.
- [ ] Provider state checked.
- [ ] Acquisition provider disabled when not actively testing.
- [ ] Ordinary tenants cannot use beta-only provider/AI access.

## 4. DB checks

Use placeholders only. Do not print secrets.

Recent AI usage by feature/status:

```sql
SELECT feature_name, status, COUNT(*) AS calls, SUM(credits_charged) AS charged
FROM ai_usage_ledger
WHERE tenant_id = '<beta_tenant_id>'
GROUP BY feature_name, status
ORDER BY feature_name, status;
```

Recent company research reports:

```sql
SELECT status, COUNT(*) AS reports
FROM candidate_research_reports
WHERE tenant_id = '<beta_tenant_id>'
GROUP BY status;
```

Recent outreach drafts:

```sql
SELECT status, COUNT(*) AS drafts
FROM candidate_outreach_drafts
WHERE tenant_id = '<beta_tenant_id>'
GROUP BY status;
```

Recent candidate count:

```sql
SELECT status, COUNT(*) AS candidates
FROM target_customer_candidates
WHERE tenant_id = '<beta_tenant_id>'
GROUP BY status;
```

Candidate draft path should not create outreach messages:

```sql
SELECT COUNT(*) AS recent_outreach_messages
FROM outreach_messages
WHERE tenant_id = '<beta_tenant_id>'
  AND created_at >= '<beta_start_timestamp>';
```

Coarse private contact spot check for drafts:

```sql
SELECT COUNT(*) AS suspicious_drafts
FROM candidate_outreach_drafts
WHERE tenant_id = '<beta_tenant_id>'
  AND (
    subject LIKE '%@%'
    OR body LIKE '%@%'
    OR short_body LIKE '%@%'
    OR body GLOB '*[0-9][0-9][0-9]*'
  );
```

Coarse private contact spot check for research:

```sql
SELECT COUNT(*) AS suspicious_reports
FROM candidate_research_reports
WHERE tenant_id = '<beta_tenant_id>'
  AND (
    summary LIKE '%@%'
    OR product_fit LIKE '%@%'
    OR suggested_outreach_angle LIKE '%@%'
    OR summary GLOB '*[0-9][0-9][0-9]*'
  );
```

These SQL checks are coarse. Manual review is still required before acting on incidents.

## 5. User support script

Use short, consistent answers.

If user asks whether the system sent an email:

```text
系统不会自动发送邮件，开发信只是草稿。你需要复制、修改，然后自己决定是否发送。
```

If user asks whether the customer is verified:

```text
AI 结果未验证，请人工确认后再联系客户。候选客户不代表一定是买家。
```

If user asks why hardware/OEM is not enabled:

```text
现在只支持包装和 LED 行业小范围测试。五金、金属配件、OEM hardware 的买家/供应商误判风险更高，后续会单独评估。
```

If user asks for private email or phone:

```text
这个版本还不支持找私人邮箱/手机号，也不会把私人邮箱/手机号保存为可信字段。
```

If user asks for LinkedIn contacts:

```text
这个版本不会抓取 LinkedIn、Facebook、WhatsApp 或 Telegram。请你人工确认公开信息后再联系。
```

If user reports a wrong candidate:

```text
请把候选公司名称、为什么不匹配、以及你认为正确的买家类型发给我们，我们会记录到 beta 反馈里。
```

## 6. After beta

After each beta round:

- [ ] Export or summarize feedback.
- [ ] Count completed product profiles.
- [ ] Count generated candidates.
- [ ] Count completed research reports.
- [ ] Count completed outreach drafts.
- [ ] Check no automatic email was sent.
- [ ] Check no `OutreachMessage` was created unexpectedly.
- [ ] Check no private contact data was stored.
- [ ] Check no provider cost spike.
- [ ] Disable acquisition provider if not needed.
- [ ] Disable beta access if user exits beta.

Classify issues:

- blocker
- safety
- quality
- UX polish
- future feature

Decide:

- continue
- polish
- expand users
- expand industries
- pause
