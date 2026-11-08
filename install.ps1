# One-command install for Ray's Claude video kit on Windows (PowerShell).
# Usage, from the folder you cloned:  powershell -ExecutionPolicy Bypass -File .\install.ps1
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Skills = if ($env:CLAUDE_SKILLS_DIR) { $env:CLAUDE_SKILLS_DIR } else { Join-Path $HOME ".claude\skills" }
New-Item -ItemType Directory -Force -Path $Skills | Out-Null

function Copy-Skill($Folder, $Name) {
  $Src = Join-Path $Here $Folder; $Dst = Join-Path $Skills $Name
  if ((Test-Path $Dst) -and -not (Test-Path (Join-Path $Dst ".raycfu"))) {
    Write-Host "Backing up your existing $Name skill to $Dst.backup"
    if (Test-Path "$Dst.backup") { Remove-Item -Recurse -Force "$Dst.backup" }
    Move-Item $Dst "$Dst.backup"
  }
  New-Item -ItemType Directory -Force -Path $Dst | Out-Null
  Get-ChildItem -Force $Src | Where-Object { $_.Name -notin @(".venv", "__pycache__") } | Copy-Item -Destination $Dst -Recurse -Force
  New-Item -ItemType File -Force -Path (Join-Path $Dst ".raycfu") | Out-Null
  Write-Host "Installed $Name -> $Dst"
}

Copy-Skill "effects" "effects"
Copy-Skill "reel-builder" "reel-builder"

$Bash = Get-Command bash -ErrorAction SilentlyContinue
if ($Bash) {
  Write-Host "Setting up the effects environment (first time takes about 2 minutes)..."
  & bash (Join-Path $Skills "effects/scripts/setup.sh")
} else {
  Write-Host "Skills installed. Setup runs automatically the first time you use /effects in Claude Code."
}
Write-Host ""
Write-Host "Done. Restart Claude Code, drop in a clip and type /effects or /reel-builder."
