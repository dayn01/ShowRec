# Starts the ShowRec backend and frontend in separate PowerShell windows.

$root = $PSScriptRoot

# Get local IP for display
$localIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -eq "Dhcp" } | Select-Object -First 1).IPAddress

Write-Host "Starting ShowRec..." -ForegroundColor Cyan

# Backend — bind to all interfaces so other devices can reach it
Start-Process powershell -ArgumentList @"
-NoProfile -ExecutionPolicy Bypass -Command "
cd '$root\backend'
Write-Host 'Backend starting on all interfaces...' -ForegroundColor Cyan
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"
"@

Start-Sleep -Seconds 2

# Frontend — bind to all interfaces, tell Vite the backend URL
Start-Process powershell -ArgumentList @"
-NoProfile -ExecutionPolicy Bypass -Command "
cd '$root\frontend'
Write-Host 'Frontend starting on all interfaces...' -ForegroundColor Cyan
npm run dev -- --port 5174 --host 0.0.0.0
"
"@

Write-Host ""
Write-Host "Servers started:" -ForegroundColor Green
Write-Host "  This PC  ->  http://localhost:5174" -ForegroundColor Yellow
if ($localIp) {
    Write-Host "  Network  ->  http://${localIp}:5174" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Open http://${localIp}:5174 on any device on your local network." -ForegroundColor Green
}
Write-Host ""
Write-Host "Note: Windows Firewall may block the ports. Run the firewall commands in SETUP.md if other devices cannot connect." -ForegroundColor Gray
