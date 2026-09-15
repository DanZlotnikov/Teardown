param(
    [Parameter(Mandatory = $true)][string]$Condition,
    [int]$Port = 8765,
    [string]$Upstream = "http://127.0.0.1:11434"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
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
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { throw "Proxy port did not clear." }

$captureRelative = "results/raw-proxy-logs/$Condition.jsonl"
$capture = Join-Path $repoRoot $captureRelative
if (Test-Path -LiteralPath $capture) { throw "Capture already exists: $capture" }
$stdout = Join-Path $repoRoot "results/raw-proxy-logs/$Condition.proxy.stdout.log"
$stderr = Join-Path $repoRoot "results/raw-proxy-logs/$Condition.proxy.stderr.log"
$arguments = @(
    "-m", "proxy.server", "--root", $repoRoot, "--upstream", $Upstream,
    "--log", $captureRelative, "--condition", $Condition, "--port", "$Port"
)
$proxy = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $repoRoot `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$deadline = (Get-Date).AddSeconds(15)
do {
    if ($proxy.HasExited) { throw "Local proxy exited before listening. See $stderr" }
    $ready = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($ready) { break }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)
if (-not $ready) { throw "Local proxy did not listen." }
Write-Output "local_proxy_condition=$Condition port=$Port"
