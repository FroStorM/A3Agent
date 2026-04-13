#!/usr/bin/env pwsh
# 完整打包脚本 - 创建独立可运行的 A3Agent

param(
    [switch]$SkipPython,
    [switch]$SkipTauri,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "A3Agent 完整打包脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 清理旧的构建产物
if ($Clean) {
    Write-Host "[清理] 删除旧的构建产物..." -ForegroundColor Yellow
    if (Test-Path "python-backend/dist") { Remove-Item -Recurse -Force "python-backend/dist" }
    if (Test-Path "python-backend/build") { Remove-Item -Recurse -Force "python-backend/build" }
    if (Test-Path "src-tauri/target/release") { Remove-Item -Recurse -Force "src-tauri/target/release" }
    Write-Host "✅ 清理完成" -ForegroundColor Green
    Write-Host ""
}

# 步骤 1: 打包 Python 后端
if (-not $SkipPython) {
    Write-Host "[1/3] 打包 Python 后端..." -ForegroundColor Yellow

    # 检查 PyInstaller
    $pyinstallerCheck = python -c "import PyInstaller" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   安装 PyInstaller..." -ForegroundColor Gray
        pip install pyinstaller
    }

    # 进入 python-backend 目录
    Push-Location python-backend

    try {
        Write-Host "   运行 PyInstaller..." -ForegroundColor Gray
        pyinstaller headless_main.spec --clean

        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller 打包失败"
        }

        # 验证输出
        if (-not (Test-Path "dist/python-backend/python-backend.exe")) {
            throw "未找到打包后的 python-backend.exe"
        }

        Write-Host "✅ Python 后端打包完成" -ForegroundColor Green
        Write-Host "   输出: python-backend/dist/python-backend/" -ForegroundColor Gray
    }
    finally {
        Pop-Location
    }
    Write-Host ""
} else {
    Write-Host "[1/3] 跳过 Python 后端打包" -ForegroundColor Gray
    Write-Host ""
}

# 步骤 2: 配置 Tauri sidecar
if (-not $SkipTauri) {
    Write-Host "[2/3] 配置 Tauri..." -ForegroundColor Yellow

    # 创建 sidecar 目录
    $sidecarDir = "src-tauri/binaries"
    if (-not (Test-Path $sidecarDir)) {
        New-Item -ItemType Directory -Path $sidecarDir | Out-Null
    }

    # 复制 Python 后端到 sidecar
    $pythonBackendExe = "python-backend/dist/python-backend/python-backend.exe"
    if (Test-Path $pythonBackendExe) {
        Write-Host "   复制 Python 后端到 sidecar..." -ForegroundColor Gray
        Copy-Item $pythonBackendExe "$sidecarDir/python-backend-x86_64-pc-windows-msvc.exe" -Force

        # 更新 tauri.conf.json 添加 externalBin
        Write-Host "   更新 tauri.conf.json..." -ForegroundColor Gray
        $configPath = "src-tauri/tauri.conf.json"
        $config = Get-Content $configPath -Raw | ConvertFrom-Json

        if (-not $config.bundle.PSObject.Properties['externalBin']) {
            $config.bundle | Add-Member -MemberType NoteProperty -Name 'externalBin' -Value @()
        }

        if ($config.bundle.externalBin -notcontains "binaries/python-backend") {
            $config.bundle.externalBin = @("binaries/python-backend")
        }

        $config | ConvertTo-Json -Depth 10 | Set-Content $configPath

        Write-Host "✅ Sidecar 配置完成" -ForegroundColor Green
    } else {
        Write-Host "⚠️  未找到 Python 后端，跳过 sidecar 配置" -ForegroundColor Yellow
    }
    Write-Host ""
}

# 步骤 3: 构建 Tauri 应用
if (-not $SkipTauri) {
    Write-Host "[3/3] 构建 Tauri 应用..." -ForegroundColor Yellow

    npm run tauri build

    if ($LASTEXITCODE -ne 0) {
        throw "Tauri 构建失败"
    }

    Write-Host "✅ Tauri 应用构建完成" -ForegroundColor Green
    Write-Host ""
}

# 完成
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ 打包完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "构建产物位置：" -ForegroundColor White
Write-Host "  - 安装包: src-tauri/target/release/bundle/" -ForegroundColor Cyan
Write-Host "  - 可执行文件: src-tauri/target/release/a3-agent.exe" -ForegroundColor Cyan
Write-Host ""
Write-Host "注意：生成的 exe 现在包含了完整的 Python 运行环境，" -ForegroundColor Yellow
Write-Host "      可以在没有安装 Python 的系统上直接运行。" -ForegroundColor Yellow
Write-Host ""
