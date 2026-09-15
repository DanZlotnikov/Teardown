param(
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot "..\..\Teardown-runtime"),
    [string]$SourceRoot = (Join-Path $PSScriptRoot "..\..\openwebui-upstream"),
    [int]$Port = 8089,
    [int]$ProxyPort = 8766
)

$ErrorActionPreference = "Stop"
$RuntimeRoot = [IO.Path]::GetFullPath($RuntimeRoot)
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$executable = Join-Path $RuntimeRoot ".venv\Scripts\open-webui.exe"
$backend = Join-Path $SourceRoot "backend"
if (-not (Test-Path -LiteralPath $executable)) { throw "Pinned Open WebUI runtime is missing." }
if ((git -C $SourceRoot rev-parse HEAD).Trim() -ne "0a7c15832fb30b1903753e83f81dc7d27e5b0944") {
    throw "Open WebUI source is not at the required commit."
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use."
}
if (-not (Get-NetTCPConnection -State Listen -LocalPort $ProxyPort -ErrorAction SilentlyContinue)) {
    throw "Paid capture proxy is not listening on port $ProxyPort."
}

$env:DATA_DIR = Join-Path $RuntimeRoot "data-paid-pinned-0a7c158"
$env:WEBUI_AUTH = "True"
$env:ENABLE_SIGNUP = "True"
$env:WEBUI_SECRET_KEY = "teardown-paid-runtime-only-pinned-0a7c158"
$env:ENABLE_OLLAMA_API = "False"
$env:ENABLE_OPENAI_API = "False"
$env:OPENAI_API_BASE_URLS = "http://127.0.0.1:$ProxyPort/v1"
$env:OPENAI_API_KEYS = "disabled-until-local-config-update"
$env:RAG_EMBEDDING_ENGINE = "ollama"
$env:RAG_EMBEDDING_MODEL = "nomic-embed-text"
$env:RAG_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:RAG_EMBEDDING_MODEL_AUTO_UPDATE = "False"
$env:ENABLE_QUERIES_CACHE = "False"
$env:RESET_CONFIG_ON_START = "True"
$env:ENV = "prod"
$env:PYTHONPATH = $backend
$env:STATIC_DIR = Join-Path $RuntimeRoot ".venv\Lib\site-packages\open_webui\static"
$env:FRONTEND_BUILD_DIR = Join-Path $RuntimeRoot ".venv\Lib\site-packages\open_webui\frontend"

$stdout = Join-Path $RuntimeRoot "openwebui-paid-pinned.stdout.log"
$stderr = Join-Path $RuntimeRoot "openwebui-paid-pinned.stderr.log"
$process = Start-Process -FilePath $executable -ArgumentList @("serve", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $RuntimeRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Write-Output "openwebui_paid_pid=$($process.Id)"
