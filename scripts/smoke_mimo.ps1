$ErrorActionPreference = "Stop"

if ($env:RUN_LIVE_MIMO -ne "1") {
    Write-Output "SKIP live MiMo smoke"
    exit 0
}

python -m app.integrations.ai.smoke
exit $LASTEXITCODE
