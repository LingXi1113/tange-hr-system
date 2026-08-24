$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackendDir = Join-Path $RootDir 'projects\backend'

$env:HRATS_ENV = if ($env:HRATS_ENV) { $env:HRATS_ENV } else { 'development' }
$env:HRATS_PORT = if ($env:HRATS_PORT) { $env:HRATS_PORT } else { '8100' }
$env:HRATS_ENABLE_MOCK_AUTH = if ($env:HRATS_ENABLE_MOCK_AUTH) { $env:HRATS_ENABLE_MOCK_AUTH } else { '1' }
$env:HRATS_SEED_DEMO_DATA = if ($env:HRATS_SEED_DEMO_DATA) { $env:HRATS_SEED_DEMO_DATA } else { '1' }
$env:MONGODB_URI = if ($env:MONGODB_URI) { $env:MONGODB_URI } else { 'mongodb://127.0.0.1:27017' }
$env:MONGODB_DATABASE = if ($env:MONGODB_DATABASE) { $env:MONGODB_DATABASE } else { 'hr_ats_sandbox' }

Set-Location $BackendDir
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv venv .venv --python 3.12
        uv pip install -r requirements.txt --python .venv\Scripts\python.exe
    } else {
        py -3.12 -m venv .venv
        .venv\Scripts\python.exe -m pip install -r requirements.txt
    }
}
& .venv\Scripts\python.exe run.py
