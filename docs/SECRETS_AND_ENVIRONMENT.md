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

Keep mail and legacy collection providers fake for RC1 unless real credentials are explicitly approved.

```text
MAIL_PROVIDER=fake
GOOGLE_SEARCH_PROVIDER=fake
GOOGLE_MAPS_PROVIDER=fake
```

MiMo acquisition uses a tenant-scoped encrypted secret named `mimo_api_key`. Save the key through
the application SecretStore; do not put it in a Job payload, log line, checked-in `.env`, screenshot,
or browser-worker environment. Configure only the non-secret connection metadata as environment
variables:

```text
MIMO_BASE_URL=<OpenAI-compatible-base-url-from-the-MiMo-console>
MIMO_MODEL=mimo-v2.5
```

## Browser research transport

Browser research remains disabled unless `BROWSER_RESEARCH_ENABLED=true` is explicitly set after the
Browser runbook gates pass. Its transport is isolated from the application queue:

```text
BROWSER_REDIS_URL=redis://browser-redis:6379/0
BROWSER_ARTIFACT_DIR=/browser-artifacts
```

These are non-secret runtime coordinates. Do not set `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`,
`TENANT_SECRET_KEY`, `MIMO_API_KEY`, `MIMO_BASE_URL`, user tokens, browser storage state, cookies, or
provider credentials in the Browser Worker environment. The worker uses an internal `HTTPS_PROXY` set
by Compose; it is not an operator-supplied general-purpose proxy.

Pay-as-you-go and Token Plan keys use different base URLs and cannot be mixed. Use the exact base URL
shown with the key in the MiMo console. The live web-search smoke is disabled by default. To run it
locally, provide `MIMO_API_KEY` only in the process environment and execute:

```powershell
$env:RUN_LIVE_MIMO="1"
.\scripts\smoke_mimo.ps1
```

The smoke prints only a bounded PASS/FAIL category and never prints the key or provider response.
MiMo JSON mode is still followed by local Pydantic validation; syntactically valid provider JSON is
not trusted as application data until it passes that schema.

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
