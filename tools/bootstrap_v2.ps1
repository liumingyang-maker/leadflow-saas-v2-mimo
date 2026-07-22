param(
  [string]$Target = "C:\Users\97020\Desktop\leadflow-saas-v2"
)

$ErrorActionPreference = "Stop"

if (Test-Path $Target) {
  throw "Target already exists: $Target"
}

$KitRoot = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Path $Target | Out-Null

Copy-Item "$KitRoot\AGENTS.md" "$Target\AGENTS.md"
Copy-Item "$KitRoot\MASTER_AUTOPILOT_PROMPT.md" "$Target\MASTER_AUTOPILOT_PROMPT.md"
Copy-Item "$KitRoot\README_FIRST.md" "$Target\README_FIRST.md"
Copy-Item "$KitRoot\.gitignore" "$Target\.gitignore"
Copy-Item -Recurse "$KitRoot\docs" "$Target\docs"
Copy-Item -Recurse "$KitRoot\milestones" "$Target\milestones"
Copy-Item -Recurse "$KitRoot\tools" "$Target\tools"
Copy-Item -Recurse "$KitRoot\templates" "$Target\templates"
Copy-Item -Recurse "$KitRoot\.agents" "$Target\.agents"
Copy-Item -Recurse "$KitRoot\config" "$Target\config"
Copy-Item "$Target\config\autopilot.example.json" "$Target\config\autopilot.json"

Set-Location $Target
git init
git add AGENTS.md MASTER_AUTOPILOT_PROMPT.md README_FIRST.md .gitignore docs milestones tools templates .agents config
git commit -m "chore: initialize LeadFlow V2 autopilot governance"

python tools\autopilot.py init
python tools\autopilot.py prepare

Write-Host ""
Write-Host "V2 repository initialized at $Target"
Write-Host "Next: python tools\install_ui_skills.py --yes"
Write-Host "Then open this folder in Codex and paste MASTER_AUTOPILOT_PROMPT.md"
