$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$FrontendDir = Join-Path $RootDir 'projects\frontend'
$env:VITE_DEV_PORT = if ($env:VITE_DEV_PORT) { $env:VITE_DEV_PORT } else { '5173' }
$env:HRATS_DEV_PROXY_TARGET = if ($env:HRATS_DEV_PROXY_TARGET) { $env:HRATS_DEV_PROXY_TARGET } else { 'http://127.0.0.1:8100' }

Set-Location $FrontendDir
if (-not (Test-Path 'node_modules')) { npm.cmd ci }
npm.cmd run dev -- --host 0.0.0.0 --port $env:VITE_DEV_PORT --strictPort --clearScreen false --cors
