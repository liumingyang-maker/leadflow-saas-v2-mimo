# Go-Live Checklist

## Pre-Deployment

- [ ] RC validation complete (all items PASS)
- [ ] RC-009 SMTP verification PASS with real email
- [ ] Go/No-Go decision is GO
- [ ] Release tag created and pushed
- [ ] Server provisioned (Alibaba Cloud ECS)
- [ ] Docker installed on server
- [ ] Domain name configured
- [ ] DNS pointing to server IP
- [ ] Environment file created at `/etc/leadflow/production.env`
- [ ] Environment file permissions set to 600
- [ ] All secrets generated (SECRET_KEY, TENANT_SECRET_KEY, etc.)
- [ ] SMTP configured with real credentials
- [ ] Alibaba Cloud security group configured

## Deployment

- [ ] Repository cloned to `/opt/leadflow-saas-v2`
- [ ] Release tag checked out
- [ ] `ops/deploy.sh` executed successfully
- [ ] `ops/healthcheck.sh` returns PASS
- [ ] Nginx configured and reloaded
- [ ] HTTPS certificate obtained

## Post-Deployment

- [ ] `/health/live` returns 200
- [ ] `/health/ready` returns `{"ok":true}`
- [ ] Registration flow works (test with real email)
- [ ] Verification email received
- [ ] Login works
- [ ] Lead import works
- [ ] Outreach email sends
- [ ] Worker is running
- [ ] No errors in application logs

## What NOT to Advertise

- [ ] AI/provider features (not validated)
- [ ] Google Search integration (not configured)
- [ ] Google Maps integration (not configured)
- [ ] DeepSeek integration (not implemented)
- [ ] MiMo integration (not implemented)

## Monitoring

- [ ] Log monitoring configured
- [ ] SMTP delivery monitoring
- [ ] Error alerting configured
- [ ] Backup schedule verified
