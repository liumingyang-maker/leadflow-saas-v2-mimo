[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI is required. Install and start Docker Desktop, then run docker version."
}

docker version | Out-Host
docker compose config | Out-Host
docker compose build browser-worker browser-egress | Out-Host
docker compose up -d browser-redis browser-egress browser-worker | Out-Host

try {
    $forbiddenEnvironment = @(
        "DATABASE_URL",
        "SECRET_KEY",
        "TENANT_SECRET_KEY",
        "MIMO_API_KEY",
        "MIMO_BASE_URL",
        "REDIS_URL"
    )
    $environment = docker compose exec -T browser-worker /usr/bin/env
    foreach ($name in $forbiddenEnvironment) {
        if ($environment -match "(?m)^$name=") {
            throw "Browser Worker received forbidden application environment: $name"
        }
    }

    docker compose exec -T browser-worker python -c "from app.integrations.browser.worker import assert_isolated_environment; assert_isolated_environment(); print('PASS browser worker environment')" | Out-Host
    docker compose exec -T browser-worker sh -c "test ! -e /browser-runtime/app/integrations/browser/models.py && test ! -e /browser-runtime/app/integrations/browser/service.py" | Out-Host

    # No public navigation is made by this smoke. Network and raw MCP tool verification are
    # separate fail-closed gates, because a local Compose topology alone cannot prove either.
    Write-Host "PASS provisional browser container isolation"
    Write-Host "OPEN GATE: run the exact MCP tool-list contract before enabling Browser capability."
    exit 2
}
finally {
    # Do not tear down the shared application Compose stack: this smoke owns only
    # the three Browser-isolation services that it started above.
    docker compose stop browser-worker browser-egress browser-redis | Out-Host
}
