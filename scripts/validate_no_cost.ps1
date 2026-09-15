param(
    [string]$Upstream = "..\openwebui-upstream"
)
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Missing .venv; create it and install requirements.txt first." }
Push-Location $repoRoot
try {
    $ledgerBefore = (Get-FileHash -LiteralPath "results/spend-log.jsonl" -Algorithm SHA256).Hash
    $spendBefore = (Get-Content -Raw -LiteralPath "results/spend-total.txt").Trim()
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
from decimal import Decimal
from analysis.budget import BudgetGuard
root=Path.cwd(); guard=BudgetGuard(root)
assert guard.running_total() == Decimal((root / "results/spend-total.txt").read_text().strip())
assert guard.effective_total() >= guard.running_total()
assert guard.effective_total() < Decimal(str(guard.budget["hard_stop"]))
'@
    $budgetCheck | & $python -
    $secretPattern = 'sk-(?:proj-)?[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}'
    & rg -n --with-filename -I --hidden -g '!.git/**' -g '!.venv/**' -e $secretPattern .
    if ($LASTEXITCODE -eq 0) { throw "Credential-like token found." }
    if ($LASTEXITCODE -gt 1) { throw "Secret scan failed." }
    $ledgerAfter = (Get-FileHash -LiteralPath "results/spend-log.jsonl" -Algorithm SHA256).Hash
    $spendAfter = (Get-Content -Raw -LiteralPath "results/spend-total.txt").Trim()
    if ($ledgerBefore -ne $ledgerAfter -or $spendBefore -ne $spendAfter) { throw "No-cost validation changed the paid ledger." }
    & git diff --check
    Write-Output "NO_COST_VALIDATION_PASSED cases=95 cached_on_resume=95 spend_usd=$spendAfter new_paid_calls=0"
}
finally {
    Pop-Location
}
