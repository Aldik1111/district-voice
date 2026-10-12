param([int]$Port = 3000)
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path $PSScriptRoot -Parent
Push-Location (Join-Path $repoPath 'frontend')
try { & npm.cmd run dev -- --hostname 127.0.0.1 --port $Port; if ($LASTEXITCODE -ne 0) { throw 'Frontend exited with an error.' } }
finally { Pop-Location }
