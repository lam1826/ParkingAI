$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pytestTempRoot = Join-Path $projectRoot ".pytest-tmp"
$pytestBaseTemp = Join-Path $pytestTempRoot ("verify-" + [guid]::NewGuid().ToString("N"))
$pytestTempRootFull = [IO.Path]::GetFullPath($pytestTempRoot)
$pytestBaseTempFull = [IO.Path]::GetFullPath($pytestBaseTemp)

. (Join-Path $PSScriptRoot "database_guard.ps1")

$protectedDatabasePaths = @(
    (Join-Path $projectRoot "backend\database\parking.db"),
    (Join-Path $projectRoot "database\parking.db")
)
$protectedDatabaseStateBefore = Get-ProtectedDatabaseState $protectedDatabasePaths

if (-not (Test-Path -LiteralPath $python)) {
    throw "Không tìm thấy $python. Hãy tạo .venv và cài backend/requirements.txt trước."
}

Push-Location $projectRoot
try {
    & $python scripts/sync_source_snapshot.py --check
    if ($LASTEXITCODE -ne 0) { throw "Source snapshot không đồng bộ hoặc chứa artifact bị cấm." }

    # Keep pytest away from the user's OS temp directory. On managed Windows
    # hosts that directory may be unreadable even though the workspace is writable.
    New-Item -ItemType Directory -Force -Path $pytestTempRootFull | Out-Null
    & $python -m pytest -q --basetemp $pytestBaseTempFull
    if ($LASTEXITCODE -ne 0) { throw "Backend tests thất bại." }

    Push-Location (Join-Path $projectRoot "frontend")
    try {
        npm.cmd test
        if ($LASTEXITCODE -ne 0) { throw "Frontend tests thất bại." }

        npm.cmd run lint
        if ($LASTEXITCODE -ne 0) { throw "Frontend lint thất bại." }

        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build thất bại." }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location

    $expectedPrefix = $pytestTempRootFull + [IO.Path]::DirectorySeparatorChar
    if (
        (Test-Path -LiteralPath $pytestBaseTempFull) -and
        $pytestBaseTempFull.StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        Remove-Item -LiteralPath $pytestBaseTempFull -Recurse -Force -ErrorAction SilentlyContinue
    }

    $protectedDatabaseStateAfter = Get-ProtectedDatabaseState $protectedDatabasePaths
    Assert-ProtectedDatabaseStateUnchanged `
        -Before $protectedDatabaseStateBefore `
        -After $protectedDatabaseStateAfter
}
