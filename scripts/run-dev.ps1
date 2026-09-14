$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "未找到 .venv，请先按 README 安装依赖。"
}

Push-Location $projectRoot
try {
    & $pythonPath "manage.py" migrate
    & $pythonPath "manage.py" runserver "127.0.0.1:8000"
}
finally {
    Pop-Location
}
