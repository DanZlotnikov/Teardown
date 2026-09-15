param(
    [Parameter(Mandatory = $true)][string]$Condition,
    [ValidateSet("baseline", "optimized")][string]$Profile = "baseline",
    [string]$CallTypes = "",
    [ValidateSet(1, 2, 3)][int]$RetrievalK = 3,
    [string]$Model = "qwen2.5:14b-instruct",
    [string]$CollectionId = "",
    [string]$BaseUrl = "http://127.0.0.1:8088",
    [int]$ProxyPort = 8765,
    [switch]$SkipSummary,
    [switch]$Resume
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not $CollectionId) {
    $corpusState = Get-Content -Raw (Join-Path $repoRoot "results\corpus-install.json") | ConvertFrom-Json
    $CollectionId = $corpusState.collection_id
}
if (-not $CollectionId) { throw "Controlled corpus collection_id is unavailable." }
$captureRelative = "results/raw-proxy-logs/$Condition.jsonl"
$capture = Join-Path $repoRoot $captureRelative
if ((Test-Path -LiteralPath $capture) -and -not $Resume) {
    throw "Capture already exists; refusing to mix runs: $capture"
}

& $python -m configs.install_condition $Condition --base-url $BaseUrl
if ($LASTEXITCODE -ne 0) { throw "Condition installation failed: $Condition" }

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $ProxyPort -ErrorAction SilentlyContinue)
foreach ($listener in $listeners) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if (-not $process.CommandLine -or $process.CommandLine -notmatch "proxy\.server") {
        throw "Port $ProxyPort belongs to an unexpected process $($listener.OwningProcess); refusing to stop it."
    }
    Stop-Process -Id $listener.OwningProcess -Force
}

$deadline = (Get-Date).AddSeconds(15)
while ((Get-NetTCPConnection -State Listen -LocalPort $ProxyPort -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 250
}
if (Get-NetTCPConnection -State Listen -LocalPort $ProxyPort -ErrorAction SilentlyContinue) {
    throw "Capture proxy did not release port $ProxyPort."
}

$proxyStdout = Join-Path $repoRoot "results/raw-proxy-logs/$Condition.proxy.stdout.log"
$proxyStderr = Join-Path $repoRoot "results/raw-proxy-logs/$Condition.proxy.stderr.log"
$proxyArgs = @(
    "-m", "proxy.server",
    "--root", $repoRoot,
    "--upstream", "http://127.0.0.1:11434",
    "--log", $captureRelative,
    "--condition", $Condition,
    "--port", "$ProxyPort"
)
$proxyProcess = Start-Process -FilePath $python -ArgumentList $proxyArgs -WorkingDirectory $repoRoot `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput $proxyStdout -RedirectStandardError $proxyStderr

$deadline = (Get-Date).AddSeconds(15)
do {
    if ($proxyProcess.HasExited) {
        throw "Capture proxy exited before listening. See $proxyStderr"
    }
    $ready = Get-NetTCPConnection -State Listen -LocalPort $ProxyPort -ErrorAction SilentlyContinue
    if ($ready) { break }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)
if (-not $ready) { throw "Capture proxy did not become ready on port $ProxyPort." }

$scenarioArgs = @(
    "-m", "scenario.run",
    "--base-url", $BaseUrl,
    "--condition", $Condition,
    "--profile", $Profile,
    "--phase", "optimized",
    "--mode", "mock",
    "--model", $Model,
    "--retrieval-collection-id", $CollectionId,
    "--retrieval-k", "$RetrievalK",
    "--timeout", "180"
)
if ($CallTypes) { $scenarioArgs += @("--call-types", $CallTypes) }
& $python @scenarioArgs
if ($LASTEXITCODE -ne 0) { throw "Scenario failed: $Condition" }

if (-not $SkipSummary) {
    $summaryArgs = @(
        "-m", "analysis.summarize_local_run",
        "--condition", $Condition,
        "--capture", $captureRelative,
        "--retrieval-k", "$RetrievalK"
    )
    if ($Condition -ne "baseline") { $summaryArgs += "--compose-with-baseline" }
    if ($Condition -eq "l7-autocomplete-off") { $summaryArgs += @("--drop-call-types", "autocomplete") }
    & $python @summaryArgs
    if ($LASTEXITCODE -ne 0) { throw "Run summarization failed: $Condition" }
}

Write-Output "capture=$captureRelative"
