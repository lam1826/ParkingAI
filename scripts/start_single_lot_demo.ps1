param(
    [switch]$Lan,
    [switch]$NoVision,
    [switch]$EnableAI,
    [int]$Port = 8766,
    [string]$Database = ""
)
$ErrorActionPreference = "Stop"
$singleLotRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$singleLotPython = Join-Path $singleLotRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $singleLotPython)) { throw "Missing .venv. Follow docs/SINGLE_LOT_DEMO.md." }
if (-not $Database) { $Database = Join-Path $singleLotRoot "backend/artifacts/demo/single-lot-20260915.db" }
$Database = [System.IO.Path]::GetFullPath($Database)
if (-not (Test-Path -LiteralPath $Database)) {
    Push-Location (Join-Path $singleLotRoot "backend")
    try {
        & $singleLotPython -m expansion.single_lot_seed --database $Database
        if ($LASTEXITCODE -ne 0) { throw "Single-lot seed failed. Existing files were preserved." }
    } finally { Pop-Location }
}
# Validate the marker and one-lot database before spending time on the build.
& $singleLotPython -c "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from demo_server import configure_demo; configure_demo(Path(sys.argv[2]), vision=False, single_lot=True)" $PSScriptRoot $Database
if ($LASTEXITCODE -ne 0) { throw "This is not a valid single-lot demo database." }
Push-Location (Join-Path $singleLotRoot "frontend")
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed; server was not started." }
} finally { Pop-Location }
$singleLotBindAddress = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
$singleLotArguments = @((Join-Path $PSScriptRoot "demo_server.py"), "--database", $Database, "--single-lot", "--host", $singleLotBindAddress, "--port", $Port)
if ($NoVision) { $singleLotArguments += "--no-vision" }
if ($EnableAI) { $singleLotArguments += "--enable-ai" }
Write-Host "SYNTHETIC academic demo; no bank payments. Open http://localhost:$Port"
Write-Host "Local account credentials: $Database.demo-credentials.json"
Write-Host "Existing demo data and passwords are preserved on restart."
if ($EnableAI) {
    Write-Host "Gemini enabled for synthetic parking aggregates; uses the configured local API key and provider quota."
} else {
    Write-Host "AI is disabled. Use -EnableAI to opt in with a configured Gemini API key."
}
& $singleLotPython @singleLotArguments
exit $LASTEXITCODE
