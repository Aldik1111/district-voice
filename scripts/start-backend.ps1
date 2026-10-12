param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $repoPath 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create backend/.venv and install requirements-lock.txt first. See README.md.' }
Push-Location (Join-Path $repoPath 'backend')
try { & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port $Port --no-access-log; if ($LASTEXITCODE -ne 0) { throw 'Backend exited with an error.' } }
finally { Pop-Location }
