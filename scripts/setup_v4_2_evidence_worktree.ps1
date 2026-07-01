[CmdletBinding()]
param(
    [string]$EvidenceRoot = "C:\Users\klsma\OneDrive\Documents\Options Trading Assistant - v4.2 Evidence",
    [string]$FrozenRef = "codex/v4.2-prospective-tracking"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$evidenceExists = Test-Path $EvidenceRoot

Write-Step "Repo root: $repoRoot"
Write-Step "Evidence worktree: $EvidenceRoot"

if (-not $evidenceExists) {
    Write-Step "Creating frozen worktree from $FrozenRef"
    git -c core.autocrlf=false -c core.eol=lf -C $repoRoot worktree add --checkout $EvidenceRoot $FrozenRef
} else {
    Write-Step "Evidence worktree already exists"
}

if (-not (Test-Path $EvidenceRoot)) {
    throw "Evidence worktree was not created at $EvidenceRoot"
}

$requiredDirs = @(
    "data\journal",
    "data\journal\decision_packets",
    "data\journal\signal_rankings",
    "data\reports",
    "data\reports\daily",
    "data\reports\validation",
    "data\reports\validation\forward",
    "data\reports\validation\weekly"
)

foreach ($relativeDir in $requiredDirs) {
    $targetDir = Join-Path $EvidenceRoot $relativeDir
    if (-not (Test-Path $targetDir)) {
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    }
}

Write-Step "Marking tracked files read-only"
$trackedFiles = git -C $EvidenceRoot ls-files
foreach ($relativePath in $trackedFiles) {
    $targetPath = Join-Path $EvidenceRoot $relativePath
    if (Test-Path $targetPath -PathType Leaf) {
        attrib +R $targetPath | Out-Null
    }
}

$pythonPath = Join-Path $EvidenceRoot "src"
Write-Step "Verifying frozen baseline inside the isolated worktree"
$verifyScript = @'
from pathlib import Path
import json
from options_trading_assistant.validation.engine import load_validation_protocol, verify_baseline_manifest

root = Path.cwd()
protocol = load_validation_protocol(None)
result = verify_baseline_manifest(protocol, project_root=root)
print(json.dumps(result, indent=2))
if not result.get("valid"):
    raise SystemExit(1)
'@

Push-Location $EvidenceRoot
try {
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:PYTHONPATH = $pythonPath
    $verifyScript | python -
    if ($LASTEXITCODE -ne 0) {
        throw "Frozen baseline verification failed in $EvidenceRoot"
    }
} finally {
    Pop-Location
    Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}

Write-Step "Frozen evidence worktree is ready"
Write-Host ""
Write-Host "Use the launcher below for baseline evidence runs:"
Write-Host "  .\scripts\run_v4_2_baseline_from_worktree.ps1"
