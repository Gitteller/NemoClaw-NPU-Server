# Start NPU server with API key from .env
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ScriptDir ".env"
$ServerScript = Join-Path $ScriptDir "server.py"
$PY = "C:\Users\joech\AppData\Local\Programs\Python\Python311\python.exe"

# Load .env
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#\s][^=]+?)\s*=\s*(.*)$') {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($key, $val, 'Process')
            Write-Host "[env] $key = $($val.Substring(0, [Math]::Min(8,$val.Length)))..."
        }
    }
} else {
    Write-Host "[warn] No .env file found"
}

Write-Host "Starting NPU server..."
& $PY $ServerScript
