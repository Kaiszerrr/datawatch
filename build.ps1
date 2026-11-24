# Builds dist\datawatch.exe (single file, no console window) with PyInstaller.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $py -m PyInstaller --noconfirm --clean --onefile --windowed --name datawatch `
    --paths src `
    --add-data "src\datawatch\web;datawatch\web" `
    --collect-submodules dissect `
    run.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
$hash = (Get-FileHash dist\datawatch.exe -Algorithm SHA256).Hash
"dist\datawatch.exe  SHA-256 $hash"
