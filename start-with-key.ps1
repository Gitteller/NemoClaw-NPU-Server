param()
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile   = Join-Path $ScriptDir ".env"
$PY        = "C:\Users\joech\AppData\Local\Programs\Python\Python311\python.exe"
$GUNICORN  = "C:\Users\joech\AppData\Local\Programs\Python\Python311\Scripts\gunicorn.exe"

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#\s][^=]+?)\s*=\s*(.*)$') {
            $k = $matches[1].Trim(); $v = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($k, $v, 'Process')
            $d = if ($v.Length -gt 8) { $v.Substring(0,8) + '...' } else { '***' }
            Write-Host "[env] $k = $d"
        }
    }
} else {
    Write-Host "[warn] No .env file found"
}

$certFile = [System.Environment]::GetEnvironmentVariable('NPU_TLS_CERT','Process')
$keyFile  = [System.Environment]::GetEnvironmentVariable('NPU_TLS_KEY','Process')

Set-Location $ScriptDir

Write-Host "Starting NPU server (waitress + TLS)..."
& $PY "server.py"
