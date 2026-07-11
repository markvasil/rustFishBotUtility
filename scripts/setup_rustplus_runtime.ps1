# Rust+ runtime setup: Node.js + @liamcottle/rustplus.js CLI (FCM pairing).
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $ProjectRoot "runtime"
$NodeDir = Join-Path $RuntimeDir "node-win-x64"
$CliDir = Join-Path $RuntimeDir "rustplus-cli"

Write-Host "=== Rust+ Runtime Setup ===" -ForegroundColor Cyan
Write-Host "Folder: $RuntimeDir"

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

$NodeZip = Join-Path $RuntimeDir "node.zip"
$NodeUrl = "https://nodejs.org/dist/v20.18.0/node-v20.18.0-win-x64.zip"

if (-not (Test-Path (Join-Path $NodeDir "node.exe"))) {
    Write-Host "Downloading Node.js..."
    Invoke-WebRequest -Uri $NodeUrl -OutFile $NodeZip
    Expand-Archive -Path $NodeZip -DestinationPath $RuntimeDir -Force
    $Extracted = Get-ChildItem $RuntimeDir -Directory | Where-Object { $_.Name -like "node-v*" } | Select-Object -First 1
    if ($Extracted) {
        if (Test-Path $NodeDir) { Remove-Item $NodeDir -Recurse -Force }
        Rename-Item $Extracted.FullName $NodeDir
    }
    Remove-Item $NodeZip -Force -ErrorAction SilentlyContinue
}

$NodeExe = Join-Path $NodeDir "node.exe"
if (-not (Test-Path $NodeExe)) {
    throw "node.exe not found after install"
}

$CliIndex = Join-Path $CliDir "node_modules\@liamcottle\rustplus.js\cli\index.js"
if (-not (Test-Path $CliIndex)) {
    Write-Host "Installing @liamcottle/rustplus.js..."
    New-Item -ItemType Directory -Force -Path $CliDir | Out-Null
    Push-Location $CliDir
    & (Join-Path $NodeDir "npm.cmd") init -y 2>$null
    & (Join-Path $NodeDir "npm.cmd") install @liamcottle/rustplus.js
    Pop-Location
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
Write-Host "  Node: $NodeExe"
Write-Host "  CLI:  $CliDir"
Write-Host ""
Write-Host "Next: open app, tab Rust+ Live, Steam/FCM, Start listener, Pair Server in game."
