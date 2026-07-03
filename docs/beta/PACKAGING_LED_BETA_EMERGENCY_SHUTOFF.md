# Packaging / LED Beta Emergency Shutoff

Use this runbook when packaging / LED beta crosses a safety, cost, privacy, or availability boundary.

Do not paste secrets into chat. Do not delete logs or evidence before backup. Do not drop tables unless manually approved.

## 1. Emergency triggers

Stop beta immediately if any of these happen:

- Email sent unexpectedly.
- `OutreachMessage` created unexpectedly.
- Private email/phone stored.
- API key leak.
- Authorization header leak.
- `SMTP_PASSWORD` leak.
- Full prompt/response leak.
- `reasoning_content` leak.
- Raw provider response leak.
- Ordinary customer can access beta.
- Repeated 500 errors.
- AI claims verified buyer/purchase intent.
- AI claims confirmed contact person.
- Cost spike.
- Crawling/scraping detected.
- LinkedIn / Facebook / WhatsApp / Telegram scraping detected.
- Hardware / metal fittings user was enabled by mistake.

## 2. Immediate actions

Use the smallest action that stops the risk:

1. Disable acquisition provider.
2. Disable tenant AI.
3. Reduce beta quotas to 0.
4. Disable global AI only if needed.
5. Stop inviting beta users.
6. Preserve logs.
7. Create a fresh SQLite backup.
8. Record incident timeline.
9. Notify operator owner.
10. Do not paste secrets into chat.
11. Do not delete evidence before backup.

If the issue involves leaked secrets:

- Treat the secret as compromised.
- Rotate through the provider/admin console.
- Do not print the old or new secret.
- Verify logs do not contain the replacement secret.

## 3. Production commands checklist

Use placeholders only. Do not include real secrets in commands or reports.

### Health check

```bash
curl -fsS https://<your-domain>/health/live
curl -fsS https://<your-domain>/health/ready
```

### SQLite backup

Use the approved production backup script if available:

```bash
cd /opt/leadflow-saas-v2
bash ops/lightserver-backup-sqlite.sh
```

If the script is unavailable, stop and ask the operator to use the documented production backup method. Do not improvise destructive database commands.

### Table existence checks

```sql
SELECT name
FROM sqlite_master
WHERE type = 'table'
  AND name IN (
    'tenant_product_profiles',
    'target_customer_candidates',
    'candidate_research_reports',
    'candidate_outreach_drafts',
    'ai_usage_ledger',
    'outreach_messages'
  );
```

### Provider disabled check

Acquisition provider state:

```sql
SELECT provider, enabled, daily_spend_cap_cents, query_limit_per_run, result_limit_per_run
FROM acquisition_provider_settings;
```

AI provider state:

```sql
SELECT provider, enabled, model, timeout_seconds, max_output_tokens
FROM ai_provider_settings;
```

Tenant quota state:

```sql
SELECT tenant_id, enabled, monthly_included_credits
FROM tenant_ai_quotas
WHERE tenant_id = '<beta_tenant_id>';
```

### Ledger check

```sql
SELECT feature_name, status, COUNT(*) AS calls, SUM(credits_charged) AS charged
FROM ai_usage_ledger
WHERE tenant_id = '<beta_tenant_id>'
GROUP BY feature_name, status
ORDER BY feature_name, status;
```

### Outreach messages count check

Candidate draft beta should not create outreach messages:

```sql
SELECT COUNT(*) AS outreach_messages_since_beta_start
FROM outreach_messages
WHERE tenant_id = '<beta_tenant_id>'
  AND created_at >= '<beta_start_timestamp>';
```

### Private contact spot checks

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

These checks are coarse indicators. Review suspicious rows manually after backup.

## 4. Rollback

Rollback only if there is an app bug, repeated 500s, or data integrity risk.

Rollback principles:

- Roll back to previous known good tag only if app bug.
- Disable providers first if the issue is provider, AI, cost, or safety related.
- Additive tables can remain.
- Do not drop tables unless manually approved.
- Do not run destructive git/database commands without explicit approval.
- Verify health after rollback.

Suggested rollback checklist:

1. Create SQLite backup.
2. Record current tag / commit.
3. Disable acquisition provider.
4. Disable tenant AI or set quota to 0.
5. Run approved rollback script for previous known good tag.
6. Run health checks.
7. Verify table existence.
8. Verify ordinary tenant access remains blocked.
9. Record final status in incident report.

## 5. Incident report template

Use this template after immediate risk is stopped.

```text
Incident title:

Time detected:
Time contained:
Operator:
Tenant:
Feature:

Issue:

Severity:
- blocker
- safety
- privacy
- cost
- availability
- quality

User impact:

Was email sent unexpectedly?
- yes / no / unknown

Was OutreachMessage created unexpectedly?
- yes / no / unknown

Was any secret leaked?
- yes / no / unknown

Was private email/phone stored?
- yes / no / unknown

Was prompt/full response/reasoning/raw provider response leaked?
- yes / no / unknown

Was crawling/scraping involved?
- yes / no / unknown

Actions taken:

Evidence preserved:

Current system state:

Next fix:

Decision:
- resume beta
- keep paused
- rollback
- patch required
- user communication required
```
