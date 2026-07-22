# Secrets and Environment

Do not commit real secrets. Use environment variables or a secret manager.

## Required Core Variables

```text
APP_ENV=production
FLASK_ENV=production
SECRET_KEY=<32-plus-character-random-value>
TENANT_SECRET_KEY=<32-plus-character-random-value>
DATABASE_URL=<database-url>
REDIS_URL=<redis-url>
WTF_CSRF_ENABLED=True
SESSION_COOKIE_SECURE=True
PROXY_FIX_HOPS=<trusted-proxy-hop-count>
SERVER_NAME=<host-name>
ALLOWED_HOSTS=<comma-separated-hosts>
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
- Regenerate inbound tokens after encryption-key changes when required.
- Restart web and worker processes after secret changes.

## Local Development Defaults

The repository contains development-only placeholder values such as `dev-only-change-me` in `docker-compose.yml`. These are not valid for staging or production.

## Staging Guidance

- Use unique staging secrets; do not reuse production values.
- Store `.env` outside Git-tracked files.
- Restrict SSH and database access.
- Do not add real customer data to staging unless explicitly approved.
