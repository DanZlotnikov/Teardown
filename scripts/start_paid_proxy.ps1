param(
    [Parameter(Mandatory = $true)][string]$Condition,
    [ValidateSet("baseline", "optimized", "quality_eval", "judge", "contingency")][string]$Phase,
    [int]$SafetyMaxOutput = 512,
    [int]$Port = 8766,
    [string]$Upstream = "https://api.openai.com"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Repository virtual environment is missing." }
if ($SafetyMaxOutput -lt 1) { throw "SafetyMaxOutput must be positive." }

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
foreach ($listener in $listeners) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if (-not $process.CommandLine -or $process.CommandLine -notmatch "proxy\.server") {
        throw "Port $Port belongs to an unexpected process $($listener.OwningProcess); refusing to stop it."
    }
    Stop-Process -Id $listener.OwningProcess -Force
}

$deadline = (Get-Date).AddSeconds(15)
while ((Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 250
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Previous capture proxy did not release port $Port."
}

$captureRelative = "results/raw-proxy-logs/$Condition.jsonl"
$stdout = Join-Path $repoRoot "results/raw-proxy-logs/$Condition.proxy.stdout.log"
$stderr = Join-Path $repoRoot "results/raw-proxy-logs/$Condition.proxy.stderr.log"
$arguments = @(
    "-m", "proxy.server",
    "--root", $repoRoot,
    "--upstream", $Upstream,
    "--log", $captureRelative,
    "--condition", $Condition,
    "--phase", $Phase,
    "--paid",
    "--safety-max-output", "$SafetyMaxOutput",
    "--port", "$Port"
)
$proxy = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $repoRoot `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

$deadline = (Get-Date).AddSeconds(15)
do {
    if ($proxy.HasExited) { throw "Paid proxy exited before listening. See $stderr" }
    $ready = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($ready) { break }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)
if (-not $ready) { throw "Paid proxy did not listen on port $Port." }

Write-Output "paid_proxy_condition=$Condition phase=$Phase port=$Port"
