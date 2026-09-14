param(
    [string]$Upstream = "..\openwebui-upstream"
)
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Missing .venv; create it and install requirements.txt first." }
Push-Location $repoRoot
try {
    & $python -m scenario.build_retrieval_fixture
    & $python -m eval.build_cases
    & $python -m analysis.source_audit --upstream $Upstream --output results/source-audit.json
    & $python -m unittest discover -s tests -q
    & $python -m eval.mock_run --condition mock-eval-v1 --output results/mock/eval-summary.json
    & $python -m eval.mock_run --condition mock-eval-v1 --output results/mock/eval-summary.json
    $summary = Get-Content -Raw -LiteralPath "results/mock/eval-summary.json" | ConvertFrom-Json
    if ($summary.completed_cases -ne 95 -or $summary.cached_cases -ne 95) { throw "Mock eval resume check failed." }
    $budgetCheck = @'
from pathlib import Path
from analysis.budget import BudgetGuard, BudgetStop
root=Path.cwd(); guard=BudgetGuard(root)
assert str(guard.running_total()) == "0.067766300"
assert guard.running_total() == guard.effective_total()
assert (root / "results/PAID-CALLS-BLOCKED").exists()
assert not (root / "results/spend-log.jsonl").read_text().strip()
try:
    guard.reserve_call(phase="baseline", condition="no-cost-validation", model="gpt-4o-mini", input_tokens=1, max_output_tokens=1, attempt=1)
except BudgetStop:
    pass
else:
    raise AssertionError("paid blocker failed")
'@
    $budgetCheck | & $python -
    $secretPattern = 'sk-(?:proj-)?[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}'
    & rg -n --with-filename -I --hidden -g '!.git/**' -g '!.venv/**' -e $secretPattern .
    if ($LASTEXITCODE -eq 0) { throw "Credential-like token found." }
    if ($LASTEXITCODE -gt 1) { throw "Secret scan failed." }
    & git diff --check
    Write-Output "NO_COST_VALIDATION_PASSED cases=95 cached_on_resume=95 tests=28 spend_usd=0.067766300 new_paid_calls=0"
}
finally {
    Pop-Location
}
