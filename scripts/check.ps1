$ErrorActionPreference = "Stop"

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

& $Python -m ruff check .
& $Python -m ruff format --check .
& $Python -m pytest
git diff --check
