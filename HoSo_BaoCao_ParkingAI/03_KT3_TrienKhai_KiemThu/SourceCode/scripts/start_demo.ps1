param(
    [switch]$Lan,
    [switch]$NoVision,
    [int]$Port = 8765,
    [string]$Database = "",
    [string]$DemoPassword = "DemoParkingAI!2026"
)
$ErrorActionPreference = "Stop"
$demoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$demoPython = Join-Path $demoRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $demoPython)) { throw "Chưa có .venv. Xem docs/DEMO_GUIDE.md để cài thư viện." }
if (-not $Database) { $Database = Join-Path $demoRoot "backend/artifacts/demo/parking-demo.db" }
$Database = [System.IO.Path]::GetFullPath($Database)
if (-not (Test-Path -LiteralPath $Database)) {
    Push-Location (Join-Path $demoRoot "backend")
    try {
        & $demoPython -m expansion.demo_seed --database $Database --password $DemoPassword
        if ($LASTEXITCODE -ne 0) { throw "Không tạo được dữ liệu demo." }
    } finally { Pop-Location }
}
Push-Location (Join-Path $demoRoot "frontend")
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build lỗi; chưa khởi động demo." }
} finally { Pop-Location }
$demoBindAddress = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
$demoArguments = @((Join-Path $PSScriptRoot "demo_server.py"), "--database", $Database, "--host", $demoBindAddress, "--port", $Port)
if ($NoVision) { $demoArguments += "--no-vision" }
Write-Host "DEMO đồ án, không chuyển tiền thật. Mở http://localhost:$Port"
Write-Host "Tài khoản tạo ban đầu: admin_demo / manager_demo / staff_demo / customer_demo"
Write-Host "Mật khẩu của DB mới: tham số DemoPassword (mặc định xem DEMO_GUIDE.md). DB có sẵn giữ mật khẩu cũ."
if ($Lan) {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.IPAddress -notlike "169.254.*" } |
        ForEach-Object { Write-Host "Điện thoại cùng Wi-Fi: http://$($_.IPAddress):$Port" }
}
& $demoPython @demoArguments
exit $LASTEXITCODE
