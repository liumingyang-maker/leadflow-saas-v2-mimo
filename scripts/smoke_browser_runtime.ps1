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

    # This creates no page and performs no public navigation. It only proves that the
    # local facade exposes the exact raw MCP tool contract to the Python gateway.
    docker compose exec -T browser-worker python -c "from pathlib import Path; from app.integrations.browser.gateway import BrowserGateway, build_mcp_command; from app.integrations.browser.mcp_client import StdioMcpClient; client = StdioMcpClient(build_mcp_command(artifact_dir=Path('/tmp/mcp-contract-artifacts'), max_artifact_bytes=1024, allowed_origins=('https://example.com',), proxy_url='http://browser-egress:8080')); gateway = BrowserGateway(client=client, artifact_dir=Path('/tmp/mcp-contract-artifacts'), proxy_url='http://browser-egress:8080'); gateway.assert_raw_tool_contract(); client.close(); print('PASS exact restricted MCP tool contract')" | Out-Host

    Write-Host "PASS browser runtime isolation"
}
finally {
    # Do not tear down the shared application Compose stack: this smoke owns only
    # the three Browser-isolation services that it started above.
    docker compose stop browser-worker browser-egress browser-redis | Out-Host
}
