@echo off
echo ========================================
echo A3Agent 打包脚本
echo ========================================
echo.

set RELEASE_DIR=src-tauri\target\release
set DIST_DIR=A3Agent-Portable
set VERSION=0.1.0

echo 1. 清理旧的分发目录...
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
mkdir "%DIST_DIR%"

echo.
echo 2. 复制主程序...
copy "%RELEASE_DIR%\a3-agent.exe" "%DIST_DIR%\" >nul
if errorlevel 1 (
    echo [错误] 主程序不存在，请先运行 npm run tauri build
    pause
    exit /b 1
)

echo.
echo 3. 复制Python后端...
copy "%RELEASE_DIR%\python-backend.exe" "%DIST_DIR%\" >nul
if errorlevel 1 (
    echo [错误] Python后端不存在
    pause
    exit /b 1
)

echo.
echo 4. 创建README...
(
echo A3Agent v%VERSION%
echo.
echo 使用说明：
echo 1. 双击 a3-agent.exe 启动应用
echo 2. 首次运行会自动创建 ga_config 配置目录
echo 3. 可以编辑 ga_config/mykey.json 配置API密钥
echo.
echo 注意事项：
echo - 请保持 a3-agent.exe 和 python-backend.exe 在同一目录
echo - 不要删除 python-backend.exe，这是应用的后端服务
echo - 配置文件会保存在 ga_config 目录中
echo.
echo 系统要求：
echo - Windows 10/11
echo - 无需安装Python环境
) > "%DIST_DIR%\README.txt"

echo.
echo 5. 计算总大小...
for /f "tokens=3" %%a in ('dir "%DIST_DIR%" ^| find "个文件"') do set SIZE=%%a
echo 总大小: %SIZE% 字节

echo.
echo 6. 创建压缩包...
powershell -Command "Compress-Archive -Path '%DIST_DIR%\*' -DestinationPath 'A3Agent-v%VERSION%-Portable.zip' -Force"

echo.
echo ========================================
echo 打包完成！
echo ========================================
echo.
echo 分发文件：
echo - 文件夹: %DIST_DIR%\
echo - 压缩包: A3Agent-v%VERSION%-Portable.zip
echo.
echo 可以将压缩包分发给用户，解压后运行 a3-agent.exe
echo.
pause
