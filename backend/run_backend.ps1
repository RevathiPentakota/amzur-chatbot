$ErrorActionPreference = "Stop"

$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Backend virtual environment not found at $pythonExe"
}

Set-Location $backendDir
& $pythonExe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
