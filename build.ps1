# Builds dist\RomvaHub\ (and dist\RomvaHub.zip): everything the app needs in one folder.
#
#   RomvaHub.exe        the app, with Python and Qt inside (no Python needed on the bidder's PC)
#   agent\node.exe      Node.js for the Resume Maker (no Node.js needed)
#   agent\src, agent\node_modules   the Resume agent (../resume_agent), already installed
#
# Copy that folder (or unzip RomvaHub.zip) to any Windows PC or VPS and run RomvaHub.exe. The bidder
# only signs in: to romva in the app, and once to ChatGPT / Claude / Gemini in the agent's Chrome window.
# The agent uses Google Chrome, or Microsoft Edge (already on Windows 10/11) when Chrome is not there.
#
# Run on the build PC (needs Python, Node.js and npm):   powershell -ExecutionPolicy Bypass -File build.ps1

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Assert-Ok($what) {
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" }
}

$agentSource = (Resolve-Path (Join-Path $PSScriptRoot '..\resume_agent')).Path
if (-not (Test-Path (Join-Path $agentSource 'src\agent.js'))) { throw "The Resume agent was not found at $agentSource" }
$node = (Get-Command node -ErrorAction Stop).Source

Write-Host '1/4  Python packages and PyInstaller (in build\venv)'
# A clean venv, so only what the app needs goes into the .exe.
$venv = Join-Path $PSScriptRoot 'build\venv'
$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $python)) {
    python -m venv $venv
    Assert-Ok 'Creating the venv'
}
& $python -m pip install --quiet --disable-pip-version-check -r requirements.txt pyinstaller
Assert-Ok 'pip install'

Write-Host '2/4  RomvaHub.exe'
# run_pyinstaller.py = PyInstaller, plus the fix for Python 3.10.0's dis bug.
& $python run_pyinstaller.py --noconfirm --clean --windowed --name RomvaHub `
    --hidden-import keyring.backends.Windows `
    --distpath dist --workpath build --specpath build main.py
Assert-Ok 'PyInstaller'

Write-Host '3/4  The Resume agent and Node.js'
$out = Join-Path $PSScriptRoot 'dist\RomvaHub\agent'
New-Item -ItemType Directory -Force $out | Out-Null
Copy-Item (Join-Path $agentSource 'package.json'), (Join-Path $agentSource 'package-lock.json') $out -Force
Copy-Item (Join-Path $agentSource 'src') $out -Recurse -Force
Copy-Item $node (Join-Path $out 'node.exe') -Force
Push-Location $out
try {
    npm ci --omit=dev --no-audit --no-fund
    Assert-Ok 'npm ci'
} finally {
    Pop-Location
}

Write-Host '4/4  dist\RomvaHub.zip'
$zip = Join-Path $PSScriptRoot 'dist\RomvaHub.zip'
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $PSScriptRoot 'dist\RomvaHub') -DestinationPath $zip

Write-Host ''
Write-Host "Done: $(Join-Path $PSScriptRoot 'dist\RomvaHub')  (zip: $zip)"
