#!/usr/bin/env pwsh
# A3Agent 环境检查工具

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "A3Agent 环境检查工具" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allPassed = $true

# 检查 Python
Write-Host "[1/4] 检查 Python 是否安装..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python 已安装: $pythonVersion" -ForegroundColor Green

    # 检查版本
    $versionCheck = python -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Python 版本符合要求 (>= 3.8)" -ForegroundColor Green
    } else {
        Write-Host "❌ Python 版本过低，需要 3.8 或更高版本" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "❌ Python 未安装或未添加到 PATH" -ForegroundColor Red
    Write-Host "   请从 https://www.python.org/downloads/ 下载并安装 Python 3.8+" -ForegroundColor Yellow
    $allPassed = $false
}
Write-Host ""

# 检查 Python 包
Write-Host "[2/4] 检查必需的 Python 包..." -ForegroundColor Yellow
$packages = @("fastapi", "uvicorn", "requests")
$missingPackages = @()

foreach ($pkg in $packages) {
    $check = python -c "import $pkg" 2>&1
    if ($LASTEXITCODE -ne 0) {
        $missingPackages += $pkg
    }
}

if ($missingPackages.Count -gt 0) {
    Write-Host "❌ 缺少以下 Python 包: $($missingPackages -join ', ')" -ForegroundColor Red
    Write-Host "   正在尝试自动安装..." -ForegroundColor Yellow
    pip install fastapi uvicorn requests pyperclip urllib3
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 依赖包安装成功" -ForegroundColor Green
    } else {
        Write-Host "❌ 自动安装失败，请手动运行:" -ForegroundColor Red
        Write-Host "   pip install -r python-backend/requirements.txt" -ForegroundColor Yellow
        $allPassed = $false
    }
} else {
    Write-Host "✅ 所有必需的 Python 包已安装" -ForegroundColor Green
}
Write-Host ""

# 检查目录结构
Write-Host "[3/4] 检查 python-backend 目录..." -ForegroundColor Yellow
if (Test-Path "python-backend/headless_main.py") {
    Write-Host "✅ python-backend 目录结构正常" -ForegroundColor Green
} else {
    Write-Host "❌ 找不到 python-backend/headless_main.py" -ForegroundColor Red
    Write-Host "   请确保在项目根目录运行此脚本" -ForegroundColor Yellow
    $allPassed = $false
}
Write-Host ""

# 检查启动日志
Write-Host "[4/4] 检查最近的启动日志..." -ForegroundColor Yellow
$logPath = Join-Path $env:TEMP "a3agent_startup.log"
if (Test-Path $logPath) {
    Write-Host "✅ 找到启动日志: $logPath" -ForegroundColor Green
    Write-Host "   最后几行内容:" -ForegroundColor Gray
    Get-Content $logPath -Tail 5 | ForEach-Object { Write-Host "   $_" -ForegroundColor Gray }
} else {
    Write-Host "ℹ️  未找到启动日志（应用尚未运行过）" -ForegroundColor Gray
}
Write-Host ""

# 总结
Write-Host "========================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "✅ 环境检查通过！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "现在可以运行：" -ForegroundColor White
    Write-Host "  - 开发模式：npm run tauri dev" -ForegroundColor Cyan
    Write-Host "  - 生产构建：npm run tauri build" -ForegroundColor Cyan
} else {
    Write-Host "❌ 环境检查失败" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "请根据上述错误信息修复问题后重试" -ForegroundColor Yellow
    Write-Host "详细说明请查看 BUILD_GUIDE.md" -ForegroundColor Yellow
}
Write-Host ""
