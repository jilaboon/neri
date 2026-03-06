$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot/../.."
Set-Location $Root

if (-Not (Test-Path ".venv-build")) {
    python -m venv .venv-build
}

. .\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

pyinstaller --noconfirm --clean --onefile --name CB2TManager `
  --hidden-import app.main `
  --hidden-import app.db `
  --hidden-import app.simulator `
  --collect-submodules app `
  --add-data "app\templates;app\templates" `
  --add-data "app\static;app\static" `
  run_cb2t.py

$PackageDir = "dist\CB2TManager-win64"
if (Test-Path $PackageDir) {
    Remove-Item -Recurse -Force $PackageDir
}
New-Item -ItemType Directory -Path $PackageDir | Out-Null
New-Item -ItemType Directory -Path "$PackageDir\demo" | Out-Null

Copy-Item "dist\CB2TManager.exe" "$PackageDir\CB2TManager.exe"
Copy-Item "demo\topology-demo.json" "$PackageDir\demo\topology-demo.json"
Copy-Item "demo\topology-demo.csv" "$PackageDir\demo\topology-demo.csv"

@"
CB2T Manager package

Run:
1) Double click CB2TManager.exe
2) Browser opens on http://127.0.0.1:8000
3) In BERT Config, import demo files from .\demo
"@ | Out-File -Encoding UTF8 "$PackageDir\README.txt"

$ZipPath = "dist\CB2TManager-win64.zip"
if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}
Compress-Archive -Path "$PackageDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host "Created: $ZipPath"
