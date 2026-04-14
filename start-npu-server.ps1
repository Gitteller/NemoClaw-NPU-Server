# NemoClaw NPU Inference Server - Windows Startup Script
# Place a shortcut to this in shell:startup for auto-start

$PY = "C:\Users\joech\AppData\Local\Programs\Python\Python311\python.exe"
$SERVER = "$PSScriptRoot\server.py"
$LOG = "$PSScriptRoot\server.log"

# Add firewall rule if not already present
$ruleName = "NemoClaw NPU Server"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    Write-Host "Adding firewall rule for port 11435..."
    New-NetFirewallRule -DisplayName $ruleName `
        -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort 11435 | Out-Null
    Write-Host "Firewall rule added."
}

Write-Host "Starting NemoClaw NPU server on port 11435..."
Write-Host "Log: $LOG"
Write-Host "Press Ctrl+C to stop."
& $PY $SERVER 2>&1 | Tee-Object -FilePath $LOG
