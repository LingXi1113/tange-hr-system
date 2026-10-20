param(
    [string]$Model = 'qwen3:1.7b',
    [string]$OllamaExe = 'D:\hr-ats-ocr\Ollama\ollama.exe',
    [string]$ModelsDirectory = 'D:\hr-ats-ocr\models'
)

$ErrorActionPreference = 'Stop'
$env:OLLAMA_MODELS = $ModelsDirectory
$env:HRATS_RESUME_AI_ENABLED = '1'
$env:HRATS_RESUME_AI_BASE_URL = 'http://127.0.0.1:11434/v1'
$env:HRATS_RESUME_AI_MODEL = $Model
$env:HRATS_RESUME_AI_TIMEOUT = '120'

try {
    $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3
} catch {
    if (-not (Test-Path -LiteralPath $OllamaExe)) {
        throw "Ollama executable not found: $OllamaExe"
    }
    Start-Process -FilePath $OllamaExe -ArgumentList 'serve' -WindowStyle Hidden
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
            $ready = $true
            break
        } catch { }
    }
    if (-not $ready) { throw 'Ollama did not start.' }
}

$tags = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
if ($Model -notin @($tags.models | ForEach-Object { $_.name })) {
    throw "Model not installed. Run: & '$OllamaExe' pull '$Model'"
}

$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Push-Location $PSScriptRoot
try { & $pythonExe 'run.py' } finally { Pop-Location }

