# Secrets and Environment

Do not commit real secrets. Use environment variables or a secret manager.

## Required Core Variables

```text
APP_ENV=production
FLASK_ENV=production
SECRET_KEY=<32-plus-character-random-value>
TENANT_SECRET_KEY=<32-plus-character-random-value>
INBOUND_TOKEN_KEY=<32-plus-character-random-value>
OUTREACH_SIGNING_KEY=<32-plus-character-random-value>
DATABASE_URL=<database-url>
REDIS_URL=<redis-url>
WTF_CSRF_ENABLED=True
SESSION_COOKIE_SECURE=True
PROXY_FIX_HOPS=<trusted-proxy-hop-count>
SERVER_NAME=<host-name>
ALLOWED_HOSTS=<comma-separated-hosts>
```

## Account Email Variables

Staging and production require SMTP configuration so registration verification and password
reset emails do not silently fall back to a fake sender.

```text
SMTP_HOST=<smtp-host>
SMTP_PORT=587
SMTP_USER=<smtp-user>
SMTP_PASSWORD=<smtp-password>
SMTP_FROM=<verified-from-address>
SMTP_USE_TLS=true
```

## Provider Variables

Keep these fake for RC1 unless real credentials are explicitly approved.

```text
MAIL_PROVIDER=fake
GOOGLE_SEARCH_PROVIDER=fake
GOOGLE_MAPS_PROVIDER=fake
```

Future real provider variables should be named clearly and stored outside Git, for example:

```text
MAIL_API_KEY=<secret-manager-reference>
GOOGLE_SEARCH_API_KEY=<secret-manager-reference>
GOOGLE_MAPS_API_KEY=<secret-manager-reference>
```

## Secret Rotation

- Rotate `SECRET_KEY` during a maintenance window because it affects session signing.
- Rotate `TENANT_SECRET_KEY` with a planned tenant secret migration/rotation procedure.
- Rotate `INBOUND_TOKEN_KEY` only with a planned inbound token rotation. Regenerate inbound tokens after encryption-key changes when required.
- Rotate `OUTREACH_SIGNING_KEY` with a planned email-link transition because existing tracking and unsubscribe links depend on it.
- Restart web and worker processes after secret changes.

## Local Development Defaults

The repository contains development-only placeholder values such as `dev-only-change-me` in `docker-compose.yml`. These are not valid for staging or production.

## Staging Guidance

- Use unique staging secrets; do not reuse production values.
- Store `.env` outside Git-tracked files.
- Restrict SSH and database access.
- Do not add real customer data to staging unless explicitly approved.
- Set `ALLOWED_HOSTS` to the exact staging hostnames. Staging and production reject
  requests with hosts outside this allowlist and emit HSTS when secure cookies are enabled.
- Keep Redis available before user trials. Staging and production use Redis-backed atomic
  counters for login, registration, password-reset, admin-login, and inbound API abuse limits.
- CSP currently keeps inline script/style allowances for existing HTMX and inline UI behavior.
  Plan a separate nonce/hash CSP migration before tightening those directives further.
