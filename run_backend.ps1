$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $repoRoot "backend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Backend virtual environment not found at $pythonExe"
}

Set-Location $repoRoot
& $pythonExe -m uvicorn main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
