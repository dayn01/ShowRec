# Run this once to get your Trakt access token.
# After running, copy the TRAKT_ACCESS_TOKEN line into your .env file.

$envFile = "$PSScriptRoot\.env"
if (-not (Test-Path $envFile)) {
    Write-Error ".env file not found. Copy .env.example to .env and fill in your Trakt keys first."
    exit 1
}

# Read client_id and client_secret from .env
$clientId = ""
$clientSecret = ""
foreach ($line in Get-Content $envFile) {
    if ($line -match "^TRAKT_CLIENT_ID=(.+)$") { $clientId = $Matches[1].Trim() }
    if ($line -match "^TRAKT_CLIENT_SECRET=(.+)$") { $clientSecret = $Matches[1].Trim() }
}

if (-not $clientId -or $clientId -eq "your_trakt_client_id_here") {
    Write-Error "TRAKT_CLIENT_ID not set in .env"
    exit 1
}

# Step 1: Request a device code
Write-Host "Requesting device code from Trakt..." -ForegroundColor Cyan
$r1 = Invoke-RestMethod -Uri "https://api.trakt.tv/oauth/device/code" -Method Post `
    -ContentType "application/json" `
    -Body (@{ client_id = $clientId } | ConvertTo-Json)

Write-Host ""
Write-Host "1. Go to: " -NoNewline; Write-Host $r1.verification_url -ForegroundColor Yellow
Write-Host "2. Enter code: " -NoNewline; Write-Host $r1.user_code -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter after you've authorized on the Trakt website"

# Step 2: Exchange device code for access token
Write-Host "Fetching token..." -ForegroundColor Cyan
try {
    $r2 = Invoke-RestMethod -Uri "https://api.trakt.tv/oauth/device/token" -Method Post `
        -ContentType "application/json" `
        -Body (@{
            code          = $r1.device_code
            client_id     = $clientId
            client_secret = $clientSecret
        } | ConvertTo-Json)
} catch {
    Write-Error "Token exchange failed: $_"
    exit 1
}

$token = $r2.access_token
Write-Host ""
Write-Host "Success! Add this line to your .env file:" -ForegroundColor Green
Write-Host "TRAKT_ACCESS_TOKEN=$token" -ForegroundColor Yellow
Write-Host ""

# Offer to write it automatically
$ans = Read-Host "Write it to .env automatically? (y/n)"
if ($ans -eq "y") {
    $content = Get-Content $envFile
    $content = $content -replace "^TRAKT_ACCESS_TOKEN=.*$", "TRAKT_ACCESS_TOKEN=$token"
    $content | Set-Content $envFile -Encoding utf8
    Write-Host "Done - .env updated." -ForegroundColor Green
}
