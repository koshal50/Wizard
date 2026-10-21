#requires -Version 5.1
# Run interactively: administrator password stays out of command arguments and logs.
param(
    [string]$DatabaseHost = '127.0.0.1',
    [int]$DatabasePort = 5432,
    [string]$Administrator = 'postgres'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$python = @('wizard-runtime-engine\.venv\Scripts\python.exe', 'venv\Scripts\python.exe', '.venv\Scripts\python.exe') |
    ForEach-Object { Join-Path $root $_ } | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) { throw 'Wizard Python environment is missing.' }
$configPath = Join-Path $root '.secrets\wizard-account-local.clixml'
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $configPath)) {
        $password = Read-Host 'PostgreSQL administrator password (not saved)' -AsSecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password)
        try {
            $env:WIZARD_SETUP_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
            $env:WIZARD_SETUP_HOST = $DatabaseHost
            $env:WIZARD_SETUP_PORT = [string]$DatabasePort
            $env:WIZARD_SETUP_USER = $Administrator
            $created = @'
import json, os, secrets
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
try:
    suffix = secrets.token_hex(4)
    name, user = 'wizard_accounts_' + suffix, 'wizard_account_' + suffix
    password = secrets.token_urlsafe(32)
    args = dict(host=os.environ['WIZARD_SETUP_HOST'], port=os.environ['WIZARD_SETUP_PORT'])
    with psycopg.connect(**args, dbname='postgres', user=os.environ['WIZARD_SETUP_USER'],
                         password=os.environ['WIZARD_SETUP_PASSWORD'], connect_timeout=5, autocommit=True) as conn:
        conn.execute('SET statement_timeout = 10000')
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE').format(
            sql.Identifier(user), sql.Literal(password)))
        try:
            conn.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(name), sql.Identifier(user)))
        except Exception:
            conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(user)))
            raise
    print(json.dumps(dict(database=make_conninfo(**args, dbname=name, user=user, password=password),
                         secret=secrets.token_urlsafe(48))))
except Exception:
    raise SystemExit('Account database creation failed; check administrator credentials and privileges.') from None
'@ | & $python -
            if ($LASTEXITCODE -ne 0) { throw 'Account database setup failed. Existing databases were not changed.' }
            $created = $created | ConvertFrom-Json
            New-Item -ItemType Directory -Path (Split-Path $configPath -Parent) -Force | Out-Null
            [pscustomobject]@{
                Database = ConvertTo-SecureString $created.database -AsPlainText -Force
                Secret = ConvertTo-SecureString $created.secret -AsPlainText -Force
            } | Export-Clixml -LiteralPath $configPath
        }
        finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
            'WIZARD_SETUP_PASSWORD','WIZARD_SETUP_HOST','WIZARD_SETUP_PORT','WIZARD_SETUP_USER' |
                ForEach-Object { Remove-Item "Env:$_" -ErrorAction SilentlyContinue }
            $password = $null
            $created = $null
        }
    }
    $configuration = Import-Clixml -LiteralPath $configPath
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($configuration.Database)
    try {
        $env:WIZARD_ACCOUNT_DATABASE_URL = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        & $python -m backend.db
        if ($LASTEXITCODE -ne 0) { throw 'Migration failed. Encrypted database configuration was preserved.' }
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        Remove-Item Env:WIZARD_ACCOUNT_DATABASE_URL -ErrorAction SilentlyContinue
        $configuration = $null
    }
    @'
from pathlib import Path
from dotenv import set_key
root = Path.cwd()
for key, value in {'WIZARD_ACCOUNT_URL':'http://localhost:3000',
                   'WIZARD_ACCOUNT_LOCAL_DEV':'1', 'WIZARD_ACCOUNT_AUTOSTART':'1'}.items():
    set_key(str(root / '.env'), key, value)
website = root.parent / 'wizar-web' / 'wizardsite'
if website.is_dir():
    for key, value in {'WIZARD_ACCOUNT_LOCAL_DEV':'1',
                       'WIZARD_ACCOUNT_BACKEND_URL':'http://127.0.0.1:8090'}.items():
        set_key(str(website / '.env.local'), key, value)
print('Local account configuration saved. Run wizard to start the Runtime and account website.')
'@ | & $python -
    if ($LASTEXITCODE -ne 0) { throw 'Account database is ready, but local environment configuration failed.' }
}
finally { Pop-Location }
