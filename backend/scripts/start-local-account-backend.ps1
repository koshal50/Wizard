#requires -Version 5.1
# Local manual-test launcher. Configuration is encrypted for the current Windows user.
param(
    [ValidateSet('http://localhost:8090', 'http://localhost:3000')]
    [string]$PublicOrigin = 'http://localhost:3000'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$configPath = Join-Path $root '.secrets\wizard-account-local.clixml'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw 'Local account configuration is missing. Configure the dedicated account database first.'
}
$configuration = Import-Clixml -LiteralPath $configPath
function Set-ProtectedEnvironment {
    param([string]$Name, [Security.SecureString]$Value)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        [Environment]::SetEnvironmentVariable($Name,
            [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer), 'Process')
    }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
Set-ProtectedEnvironment 'WIZARD_ACCOUNT_DATABASE_URL' $configuration.Database
Set-ProtectedEnvironment 'WIZARD_ACCOUNT_SECRET' $configuration.Secret
$env:WIZARD_ACCOUNT_PUBLIC_ORIGIN = $PublicOrigin
$env:WIZARD_ACCOUNT_LOCAL_DEV = '1'
$python = @('wizard-runtime-engine\.venv\Scripts\python.exe', 'venv\Scripts\python.exe', '.venv\Scripts\python.exe') |
    ForEach-Object { Join-Path $root $_ } | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) { throw 'Wizard Python environment is missing. Install Wizard first.' }
Push-Location $root
try {
    & $python -m backend.db check
    if ($LASTEXITCODE -ne 0) { throw 'Account database preflight failed; backend was not started.' }
    & $python -m uvicorn backend.app:app --host 127.0.0.1 --port 8090 --no-access-log
}
finally {
    Remove-Item Env:WIZARD_ACCOUNT_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:WIZARD_ACCOUNT_SECRET -ErrorAction SilentlyContinue
    $configuration = $null
    Pop-Location
}
