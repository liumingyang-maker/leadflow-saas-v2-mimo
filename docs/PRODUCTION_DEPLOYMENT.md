# Production Deployment Guide

## Overview

This guide covers deploying LeadFlow SaaS V2 to a production Alibaba Cloud ECS server.

## Server Requirements

- Ubuntu 22.04 LTS or later
- Docker 24+ and Docker Compose V2
- 2 vCPU, 4GB RAM minimum
- 40GB SSD
- Public IP with domain name

## Directory Structure

```
/opt/leadflow-saas-v2/          # Git repository
/etc/leadflow/production.env    # Environment variables (chmod 600)
/var/backups/leadflow/          # Database backups
```

## First-Time Deployment

### 1. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

### 2. Clone Repository

```bash
sudo mkdir -p /opt/leadflow-saas-v2
sudo chown $USER:$USER /opt/leadflow-saas-v2
git clone https://github.com/liumingyang-maker/leadflow-saas-v2-mimo.git /opt/leadflow-saas-v2
cd /opt/leadflow-saas-v2
git checkout v1.0.0-beta.1
```

### 3. Create Environment File

```bash
sudo mkdir -p /etc/leadflow
sudo tee /etc/leadflow/production.env > /dev/null <<'EOF'
APP_ENV=production
SECRET_KEY=<generate-64-char-random-string>
TENANT_SECRET_KEY=<generate-64-char-random-string>
INBOUND_TOKEN_KEY=<generate-64-char-random-string>
OUTREACH_SIGNING_KEY=<generate-64-char-random-string>

POSTGRES_USER=leadflow
POSTGRES_PASSWORD=<generate-strong-password>
POSTGRES_DB=leadflow
DATABASE_URL=postgresql://leadflow:<password>@db:5432/leadflow

REDIS_URL=redis://redis:6379/0

SERVER_NAME=your-domain.com
ALLOWED_HOSTS=your-domain.com,www.your-domain.com
SESSION_COOKIE_SECURE=true
WTF_CSRF_ENABLED=true
PROXY_FIX_HOPS=1

SMTP_HOST=smtpdm.aliyun.com
SMTP_PORT=25
SMTP_USER=noreply@your-domain.com
SMTP_PASSWORD=<aliyun-smtp-password>
SMTP_FROM=noreply@your-domain.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false

WEB_CONCURRENCY=2
GUNICORN_THREADS=4
GUNICORN_TIMEOUT=60
EOF

sudo chmod 600 /etc/leadflow/production.env
```

### 4. Deploy

```bash
cd /opt/leadflow-saas-v2
bash ops/deploy.sh v1.0.0-beta.1
```

### 5. Configure Nginx

Install Nginx and configure reverse proxy:

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/leadflow`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/leadflow /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 6. Enable HTTPS

```bash
sudo certbot --nginx -d your-domain.com
```

### 7. Alibaba Cloud Security Group

Allow inbound traffic:
- Port 80 (HTTP) — for certbot renewal
- Port 443 (HTTPS) — for production traffic
- Port 22 (SSH) — for admin access only

Do NOT expose:
- Port 8000 (Gunicorn) — bound to 127.0.0.1
- Port 5432 (PostgreSQL) — internal only
- Port 6379 (Redis) — internal only

## Daily Operations

### View Logs

```bash
cd /opt/leadflow-saas-v2
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env logs -f web
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env logs -f worker
```

### Healthcheck

```bash
bash ops/healthcheck.sh
```

### Backup

```bash
bash ops/backup-db.sh
```

### Deploy New Version

```bash
bash ops/deploy.sh <new-tag>
```

### Rollback

```bash
bash ops/rollback.sh <previous-tag>
```

## Important Notes

- Do not expose port 8000 to the public internet
- Do not commit or share `/etc/leadflow/production.env`
- Do not advertise AI/provider features (Google Search, Maps, DeepSeek) — not validated for production
- Monitor SMTP delivery, bounce rate, and application errors
- Keep backups for at least 30 days
