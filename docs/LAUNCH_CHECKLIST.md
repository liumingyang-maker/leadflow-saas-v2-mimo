# Launch Checklist

## Pre-launch

- [ ] All migrations applied: `alembic upgrade head`
- [ ] `SECRET_KEY` set (32+ chars)
- [ ] `TENANT_SECRET_KEY` set (32+ chars)
- [ ] `APP_ENV=production` or `staging`
- [ ] `SESSION_COOKIE_SECURE=True`
- [ ] `WTF_CSRF_ENABLED=True`
- [ ] `PROXY_FIX_HOPS` configured if behind proxy
- [ ] Debug mode disabled
- [ ] All tests pass: `pytest -q`
- [ ] Ruff clean: `ruff check .`
- [ ] Format clean: `ruff format --check .`
- [ ] No `|safe` in templates
- [ ] No remote CDN references
- [ ] No Alpine.js
- [ ] No `API_KEY` in code
- [ ] No SMTP/SendGrid/Mailgun credentials in code

## Security

- [ ] Production rejects fake mailer
- [ ] Production rejects fake adapters
- [ ] CSRF enabled on all browser POST forms
- [ ] Cookies: Secure, HttpOnly, SameSite=Lax
- [ ] Security headers set (X-Content-Type-Options, X-Frame-Options, etc.)
- [ ] ProxyFix configured (if applicable)
- [ ] CSP baseline active
- [ ] Rate limiting configured
- [ ] Upload size limits active

## Operations

- [ ] Redis healthcheck configured
- [ ] Worker auto-recovery active
- [ ] Backup procedure documented
- [ ] Rollback procedure documented
- [ ] Staging environment tested
- [ ] Migration downgrade tested

## Not deployed

- [ ] No production deployment performed
- [ ] No real data modified
- [ ] No real business network accessed
