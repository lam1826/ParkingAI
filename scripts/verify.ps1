$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Không tìm thấy $python. Hãy tạo .venv và cài backend/requirements.txt trước."
}

Push-Location $projectRoot
try {
    & $python -m pytest -q
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
}
