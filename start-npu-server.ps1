# NemoClaw NPU Inference Server - Windows Startup Script
# Place a shortcut to this in shell:startup for auto-start

$PY = "C:\Users\joech\AppData\Local\Programs\Python\Python311\python.exe"
$SERVER = "$PSScriptRoot\server.py"
$LOG = "$PSScriptRoot\server.log"
$ENV_FILE = "$PSScriptRoot\.env"

# Load .env file if it exists (sets NPU_API_KEY etc.)
if (Test-Path $ENV_FILE) {
    Get-Content $ENV_FILE | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($key, $val, 'Process')
            Write-Host "[env] Loaded $key"
        }
    }
} else {
    Write-Host "[security] No .env file found — API key auth disabled. Copy .env.example to .env to enable."
}

# Restrict firewall rule to WSL2 subnet only (172.16.0.0/12), not all inbound
$ruleName = "NemoClaw NPU Server"
$existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existingRule) {
    Write-Host "Adding firewall rule for port 11435 (WSL2 subnet only)..."
    New-NetFirewallRule -DisplayName $ruleName `
        -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort 11435 `
        -RemoteAddress "172.16.0.0/12" | Out-Null
    Write-Host "Firewall rule added (restricted to 172.16.0.0/12)."
} else {
    Write-Host "Firewall rule '$ruleName' already exists."
}

Write-Host "Starting NemoClaw NPU server on port 11435..."
Write-Host "Log: $LOG"
Write-Host "Press Ctrl+C to stop."
& $PY $SERVER 2>&1 | Tee-Object -FilePath $LOG
