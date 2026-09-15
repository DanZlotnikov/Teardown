param(
    [string]$BaseUrl = "http://127.0.0.1:8089",
    [int]$ProxyPort = 8766,
    [string]$EnvFile = "C:\Users\Admin\repos\Teardown\.env"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $EnvFile)) { throw "External .env file not found." }
$line = Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match '^\s*OPENAI_API_KEY\s*=' } | Select-Object -First 1
if (-not $line) { throw "OPENAI_API_KEY is absent from the external .env file." }
$apiKey = ($line -replace '^\s*OPENAI_API_KEY\s*=\s*', '').Trim().Trim('"').Trim("'")
if ($apiKey.Length -lt 20) { throw "OPENAI_API_KEY looks invalid." }

$signinBody = @{ email = "admin@localhost"; password = "admin" } | ConvertTo-Json
$session = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/auths/signin" -ContentType "application/json" -Body $signinBody
if (-not $session.token) { throw "Open WebUI sign-in did not return a token." }
$headers = @{ Authorization = "Bearer $($session.token)" }
$models = @("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-4o-2024-11-20")
$payload = @{
    ENABLE_OPENAI_API = $true
    OPENAI_API_BASE_URLS = @("http://127.0.0.1:$ProxyPort/v1")
    OPENAI_API_KEYS = @($apiKey)
    OPENAI_API_CONFIGS = @{
        "0" = @{
            enable = $true
            model_ids = $models
            connection_type = "external"
        }
    }
} | ConvertTo-Json -Depth 8
$updated = Invoke-RestMethod -Method Post -Uri "$BaseUrl/openai/config/update" -Headers $headers -ContentType "application/json" -Body $payload
if (-not $updated.ENABLE_OPENAI_API -or $updated.OPENAI_API_BASE_URLS.Count -ne 1) {
    throw "OpenAI connection update was not applied."
}
Write-Output "paid_openai_configured=true manual_models=$($models.Count) proxy_port=$ProxyPort"
