param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot "..\..\Teardown-runtime"),
    [string]$SourceRoot = (Join-Path $PSScriptRoot "..\..\openwebui-upstream"),
    [int]$Port = 8088,
    [int]$ProxyPort = 8765,
    [bool]$EnableQueriesCache = $false
)

$ErrorActionPreference = "Stop"
$RuntimeRoot = [IO.Path]::GetFullPath($RuntimeRoot)
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$executable = Join-Path $RuntimeRoot ".venv\Scripts\open-webui.exe"
if (-not (Test-Path -LiteralPath $executable)) {
    throw "Pinned Open WebUI runtime is missing: $executable"
}
$backend = Join-Path $SourceRoot "backend"
if (-not (Test-Path -LiteralPath (Join-Path $backend "open_webui"))) {
    throw "Pinned Open WebUI source is missing: $backend"
}
$sourceCommit = (git -C $SourceRoot rev-parse HEAD).Trim()
if ($sourceCommit -ne "0a7c15832fb30b1903753e83f81dc7d27e5b0944") {
    throw "Open WebUI source is not at the required commit: $sourceCommit"
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use."
}
if (-not (Get-NetTCPConnection -State Listen -LocalPort $ProxyPort -ErrorAction SilentlyContinue)) {
    throw "Capture proxy is not listening on port $ProxyPort."
}

$env:DATA_DIR = Join-Path $RuntimeRoot "data-pinned-0a7c158"
$env:WEBUI_AUTH = "True"
$env:ENABLE_SIGNUP = "True"
$env:WEBUI_SECRET_KEY = "teardown-local-runtime-only-pinned-0a7c158"
$env:ENABLE_OLLAMA_API = "True"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:$ProxyPort"
$env:RAG_EMBEDDING_ENGINE = "ollama"
$env:RAG_EMBEDDING_MODEL = "nomic-embed-text"
$env:RAG_OLLAMA_BASE_URL = "http://127.0.0.1:$ProxyPort"
$env:RAG_EMBEDDING_MODEL_AUTO_UPDATE = "False"
$env:ENABLE_OPENAI_API = "False"
$env:ENABLE_QUERIES_CACHE = if ($EnableQueriesCache) { "True" } else { "False" }
$env:RESET_CONFIG_ON_START = "True"
$env:ENV = "prod"
$env:PYTHONPATH = $backend
$env:STATIC_DIR = Join-Path $RuntimeRoot ".venv\Lib\site-packages\open_webui\static"
$env:FRONTEND_BUILD_DIR = Join-Path $RuntimeRoot ".venv\Lib\site-packages\open_webui\frontend"

$stdout = Join-Path $RuntimeRoot "openwebui-pinned.stdout.log"
$stderr = Join-Path $RuntimeRoot "openwebui-pinned.stderr.log"
$launchArguments = @("serve", "--host", "127.0.0.1", "--port", "$Port")
$process = Start-Process -FilePath $executable -ArgumentList $launchArguments `
    -WorkingDirectory $RuntimeRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Write-Output "openwebui_pid=$($process.Id)"
