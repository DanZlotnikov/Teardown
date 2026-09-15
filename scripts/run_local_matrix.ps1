param(
    [string]$CollectionId = "",
    [string]$BaseUrl = "http://127.0.0.1:8088",
    [string]$Model = "qwen2.5:14b-instruct"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not $CollectionId) {
    $corpusState = Get-Content -Raw (Join-Path $repoRoot "results\corpus-install.json") | ConvertFrom-Json
    $CollectionId = $corpusState.collection_id
}
if (-not $CollectionId) { throw "Controlled corpus collection_id is unavailable." }

$baselineActions = Join-Path $repoRoot "results\actions\mock\baseline.jsonl"
if (-not (Test-Path -LiteralPath $baselineActions)) {
    throw "The full pinned baseline must complete before the matrix."
}
$baselineCount = (Get-Content -LiteralPath $baselineActions | Measure-Object -Line).Lines
if ($baselineCount -ne 349) { throw "Expected 349 baseline actions, found $baselineCount." }

& $python -m eval.run_local --base-url $BaseUrl --condition baseline --model $Model --collection-id $CollectionId --retrieval-k 3
if ($LASTEXITCODE -ne 0) { throw "Baseline targeted eval failed." }
& $python -m analysis.summarize_local_run --condition baseline --capture results/raw-proxy-logs/baseline.jsonl --retrieval-k 3
if ($LASTEXITCODE -ne 0) { throw "Baseline summarization failed." }

$conditions = @(
    @{ Id = "l2-cap-512"; Calls = "follow_up,title,tags,retrieval_query,web_query,autocomplete"; Eval = "title,tags,retrieval_query,web_query,autocomplete"; K = 3; Profile = "baseline" },
    @{ Id = "l2-cap-128"; Calls = "follow_up,title,tags,retrieval_query,web_query,autocomplete"; Eval = "title,tags,retrieval_query,web_query,autocomplete"; K = 3; Profile = "baseline" },
    @{ Id = "l2-cap-32"; Calls = "follow_up,title,tags,retrieval_query,web_query,autocomplete"; Eval = "title,tags,retrieval_query,web_query,autocomplete"; K = 3; Profile = "baseline" },
    @{ Id = "l4-last-10-turns"; Calls = "main"; Eval = "main_chat_context"; K = 3; Profile = "baseline" },
    @{ Id = "l4-last-6-turns"; Calls = "main"; Eval = "main_chat_context"; K = 3; Profile = "baseline" },
    @{ Id = "l4-last-3-turns"; Calls = "main"; Eval = "main_chat_context"; K = 3; Profile = "baseline" },
    @{ Id = "l6-top-k-2"; Calls = "retrieval"; Eval = "retrieval"; K = 2; Profile = "baseline" },
    @{ Id = "l6-top-k-1"; Calls = "retrieval"; Eval = "retrieval"; K = 1; Profile = "baseline" },
    @{ Id = "l7-autocomplete-off"; Calls = "autocomplete"; Eval = ""; K = 3; Profile = "optimized" }
)

foreach ($condition in $conditions) {
    & (Join-Path $PSScriptRoot "run_local_condition.ps1") `
        -Condition $condition.Id -Profile $condition.Profile -CallTypes $condition.Calls `
        -RetrievalK $condition.K -CollectionId $CollectionId -BaseUrl $BaseUrl -Model $Model -Resume -SkipSummary
    if ($LASTEXITCODE -ne 0) { throw "Scenario condition failed: $($condition.Id)" }

    if ($condition.Eval) {
        & $python -m eval.run_local --base-url $BaseUrl --condition $condition.Id --model $Model `
            --collection-id $CollectionId --retrieval-k $condition.K --call-types $condition.Eval
        if ($LASTEXITCODE -ne 0) { throw "Targeted eval failed: $($condition.Id)" }
    }

    $summaryArgs = @(
        "-m", "analysis.summarize_local_run",
        "--condition", $condition.Id,
        "--capture", "results/raw-proxy-logs/$($condition.Id).jsonl",
        "--retrieval-k", "$($condition.K)",
        "--compose-with-baseline"
    )
    if ($condition.Id -eq "l7-autocomplete-off") { $summaryArgs += @("--drop-call-types", "autocomplete") }
    & $python @summaryArgs
    if ($LASTEXITCODE -ne 0) { throw "Summarization failed: $($condition.Id)" }
}

& (Join-Path $PSScriptRoot "run_local_condition.ps1") -Condition "l4-native-compaction" `
    -RetrievalK 3 -CollectionId $CollectionId -BaseUrl $BaseUrl -Model $Model -Resume -SkipScenario -SkipSummary
if ($LASTEXITCODE -ne 0) { throw "Native compaction condition setup failed." }
& $python -m eval.run_native_compaction --base-url $BaseUrl --condition l4-native-compaction --model $Model
if ($LASTEXITCODE -ne 0) { throw "Native compaction eval failed." }
& $python -m analysis.summarize_native_compaction
if ($LASTEXITCODE -ne 0) { throw "Native compaction summarization failed." }

Write-Output "Local single-lever matrix completed."
