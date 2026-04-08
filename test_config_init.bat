@echo off
echo ========================================
echo 测试配置初始化功能
echo ========================================
echo.

set EXE_PATH=src-tauri\target\release\a3-agent.exe
set WORKSPACE_PATH=src-tauri\target\release\workspace

echo 1. 检查exe文件是否存在...
if not exist "%EXE_PATH%" (
    echo [错误] exe文件不存在: %EXE_PATH%
    pause
    exit /b 1
)
echo [成功] exe文件存在

echo.
echo 2. 清理旧的workspace（如果存在）...
if exist "%WORKSPACE_PATH%" (
    rmdir /s /q "%WORKSPACE_PATH%"
    echo [完成] 已删除旧的workspace
) else (
    echo [跳过] workspace不存在
)

echo.
echo 3. 启动应用（将在5秒后自动关闭）...
echo 请观察控制台输出中的 [ConfigManager] 日志
echo.
start /wait cmd /c "timeout /t 5 /nobreak >nul & taskkill /f /im a3-agent.exe >nul 2>&1" & start "" "%EXE_PATH%"
timeout /t 6 /nobreak >nul

echo.
echo 4. 检查workspace是否创建...
if exist "%WORKSPACE_PATH%\ga_config" (
    echo [成功] workspace/ga_config 目录已创建
) else (
    echo [失败] workspace/ga_config 目录未创建
    pause
    exit /b 1
)

echo.
echo 5. 检查配置文件是否复制...
if exist "%WORKSPACE_PATH%\ga_config\mykey.json" (
    echo [成功] mykey.json 已复制
) else (
    echo [失败] mykey.json 未复制
    pause
    exit /b 1
)

if exist "%WORKSPACE_PATH%\ga_config\memory" (
    echo [成功] memory 目录已复制
) else (
    echo [失败] memory 目录未复制
    pause
    exit /b 1
)

echo.
echo 6. 显示workspace结构...
tree /f "%WORKSPACE_PATH%\ga_config" /a

echo.
echo ========================================
echo 测试完成！配置初始化功能正常
echo ========================================
pause
