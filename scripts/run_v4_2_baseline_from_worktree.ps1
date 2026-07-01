[CmdletBinding()]
param(
    [string]$EvidenceRoot = "C:\Users\klsma\OneDrive\Documents\Options Trading Assistant - v4.2 Evidence",
    [string]$ScanDate = (Get-Date -Format "yyyy-MM-dd"),
    [string]$Mode = "balanced",
    [string]$Provider = "moomoo"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

if (-not (Test-Path $EvidenceRoot)) {
    throw "Evidence worktree not found at $EvidenceRoot. Run scripts/setup_v4_2_evidence_worktree.ps1 first."
}

$pythonPath = Join-Path $EvidenceRoot "src"
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

    Write-Step "Verifying frozen baseline manifest"
    $verifyScript | python -
    if ($LASTEXITCODE -ne 0) {
        throw "Frozen baseline verification failed in $EvidenceRoot"
    }

    Write-Step "Running isolated v4.2 baseline daily report for $ScanDate"
    python -m options_trading_assistant.cli daily-report --provider $Provider --mode $Mode --date $ScanDate
    if ($LASTEXITCODE -ne 0) {
        throw "Baseline daily report failed in $EvidenceRoot"
    }
} finally {
    Pop-Location
    Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Baseline run finished inside the frozen worktree."
Write-Host "H-008 shadow still needs to run from the research workspace because codex/v4.2-prospective-tracking does not include h008-shadow-scan."
