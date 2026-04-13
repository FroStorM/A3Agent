@echo off
echo ========================================
echo A3Agent 环境检查工具
echo ========================================
echo.

echo [1/4] 检查 Python 是否安装...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python 未安装或未添加到 PATH
    echo    请从 https://www.python.org/downloads/ 下载并安装 Python 3.8+
    echo    安装时务必勾选 "Add Python to PATH"
    goto :error
) else (
    python --version
    echo ✅ Python 已安装
)
echo.

echo [2/4] 检查 Python 版本...
python -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python 版本过低，需要 3.8 或更高版本
    goto :error
) else (
    echo ✅ Python 版本符合要求
)
echo.

echo [3/4] 检查必需的 Python 包...
set MISSING_PACKAGES=
python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 set MISSING_PACKAGES=%MISSING_PACKAGES% fastapi

python -c "import uvicorn" >nul 2>&1
if %errorlevel% neq 0 set MISSING_PACKAGES=%MISSING_PACKAGES% uvicorn

python -c "import requests" >nul 2>&1
if %errorlevel% neq 0 set MISSING_PACKAGES=%MISSING_PACKAGES% requests

if not "%MISSING_PACKAGES%"=="" (
    echo ❌ 缺少以下 Python 包：%MISSING_PACKAGES%
    echo.
    echo 正在尝试自动安装...
    pip install fastapi uvicorn requests pyperclip urllib3
    if %errorlevel% neq 0 (
        echo ❌ 自动安装失败，请手动运行：
        echo    pip install -r python-backend\requirements.txt
        goto :error
    )
    echo ✅ 依赖包安装成功
) else (
    echo ✅ 所有必需的 Python 包已安装
)
echo.

echo [4/4] 检查 python-backend 目录...
if not exist "python-backend\headless_main.py" (
    echo ❌ 找不到 python-backend\headless_main.py
    echo    请确保在项目根目录运行此脚本
    goto :error
) else (
    echo ✅ python-backend 目录结构正常
)
echo.

echo ========================================
echo ✅ 环境检查通过！
echo ========================================
echo.
echo 现在可以运行：
echo   - 开发模式：npm run tauri dev
echo   - 生产构建：npm run tauri build
echo.
pause
exit /b 0

:error
echo.
echo ========================================
echo ❌ 环境检查失败
echo ========================================
echo.
echo 请根据上述错误信息修复问题后重试
echo 详细说明请查看 BUILD_GUIDE.md
echo.
pause
exit /b 1
