$ErrorActionPreference = "Stop"

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

& $Python -m ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m ruff format --check app tests run_worker.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
git diff --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$SecretPattern = 'sk-[A-Za-z0-9_-]{20,}|MIMO_API_' + 'KEY=.+'
git grep -n -I -E $SecretPattern -- . ":(exclude).env.example" ":(exclude)docs/superpowers/plans/**"
if ($LASTEXITCODE -eq 0) { throw "Potential secret found" }
if ($LASTEXITCODE -ne 1) { throw "Secret scan failed" }
