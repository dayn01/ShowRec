<#
.SYNOPSIS
  Copy ShowRec to a Raspberry Pi for the native (systemd + uvicorn) deploy.

.DESCRIPTION
  Stages backend/ (without its venv or caches), frontend/dist, deploy/ and .env
  into a temp folder, then pushes them to the Pi over SSH/SCP. Existing data and
  the Pi's own venv are left untouched.

.EXAMPLE
  ./deploy/copy-to-pi.ps1 -PiHost pi@showrec.local
  ./deploy/copy-to-pi.ps1 -PiHost pi@192.168.1.50 -RemoteDir /home/pi/show-rec
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$PiHost,
  [string]$RemoteDir = "",
  # By default an existing .env on the Pi is left alone (it may have been edited
  # there). Pass -ForceEnv to overwrite it with this PC's .env.
  [switch]$ForceEnv
)

$ErrorActionPreference = "Stop"
$root  = Split-Path -Parent $PSScriptRoot          # project root
$stage = Join-Path $env:TEMP "showrec-deploy"

# Default the remote path to the SSH user's home (/home/<user>/show-rec) so it
# matches whatever account you logged in as, instead of assuming 'pi'.
if (-not $RemoteDir) {
  $user = if ($PiHost -match '^([^@]+)@') { $Matches[1] } else { "pi" }
  $RemoteDir = "/home/$user/show-rec"
}
Write-Host "Target: ${PiHost}:${RemoteDir}" -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $root "frontend\dist"))) {
  throw "frontend\dist not found. Run 'npm run build' in frontend\ first."
}

Write-Host "Staging files..." -ForegroundColor Cyan
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null

# robocopy exit codes 0-7 are success; treat >=8 as a real failure.
function Stage($src, $dst, [string[]]$excludeDirs) {
  $rcArgs = @($src, (Join-Path $stage $dst), "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
  if ($excludeDirs) { $rcArgs += "/XD"; $rcArgs += $excludeDirs }
  robocopy @rcArgs | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed copying $src (exit $LASTEXITCODE)" }
}

Stage (Join-Path $root "backend")       "backend"       @("venv", "__pycache__", ".pytest_cache")
Stage (Join-Path $root "frontend\dist") "frontend\dist" @()
Stage (Join-Path $root "deploy")        "deploy"        @()

$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
  Copy-Item $envFile (Join-Path $stage ".env")
} else {
  Write-Warning ".env not found at project root - the app needs it for API keys. Copy it manually later."
}

Write-Host "Ensuring $RemoteDir exists on $PiHost..." -ForegroundColor Cyan
# Remove the old frontend build first so scp does a clean replace instead of
# nesting the new dist inside the old one (frontend/dist/dist).
ssh $PiHost "mkdir -p $RemoteDir/frontend $RemoteDir/data && rm -rf $RemoteDir/frontend/dist"
if ($LASTEXITCODE -ne 0) { throw "ssh mkdir failed - check the host and your SSH key/password." }

Write-Host "Copying to $PiHost`:$RemoteDir ..." -ForegroundColor Cyan
scp -r (Join-Path $stage "backend")       "${PiHost}:${RemoteDir}/"
scp -r (Join-Path $stage "frontend\dist") "${PiHost}:${RemoteDir}/frontend/"
scp -r (Join-Path $stage "deploy")        "${PiHost}:${RemoteDir}/"

if (Test-Path (Join-Path $stage ".env")) {
  # Don't clobber a .env that already exists on the Pi unless -ForceEnv is given.
  ssh $PiHost "test -f $RemoteDir/.env" 2>$null
  $remoteEnvExists = ($LASTEXITCODE -eq 0)
  if ($remoteEnvExists -and -not $ForceEnv) {
    Write-Host "Skipping .env - one already exists on the Pi (use -ForceEnv to overwrite)." -ForegroundColor Yellow
  } else {
    scp (Join-Path $stage ".env") "${PiHost}:${RemoteDir}/.env"
  }
}

Write-Host "Done. Next: SSH in and (re)install deps + restart the service." -ForegroundColor Green
Write-Host "  ssh $PiHost" -ForegroundColor Green
Write-Host "  cd $RemoteDir/backend && ./venv/bin/pip install -r requirements.txt && sudo systemctl restart showrec.service" -ForegroundColor Green
