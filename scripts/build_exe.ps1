$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BuildDir = Join-Path $ProjectRoot "build"
$SpecDir = Join-Path $BuildDir "spec"

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name Breadcrumbs `
  --distpath $ProjectRoot `
  --workpath $BuildDir `
  --specpath $SpecDir `
  (Join-Path $ProjectRoot "app.py")

Write-Host ""
Write-Host "Built $ProjectRoot\Breadcrumbs.exe"
