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
# Console build of the AI-assistant connector (MCP talks over stdin/stdout, which the windowed exe does not have).
& $py -m PyInstaller --noconfirm --onefile --console --name datawatch-mcp `
    --paths src --collect-submodules dissect run_mcp.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller (mcp) failed" }
foreach ($f in "datawatch", "datawatch-mcp") {
    $hash = (Get-FileHash "dist\$f.exe" -Algorithm SHA256).Hash
    "dist\$f.exe  SHA-256 $hash"
}
