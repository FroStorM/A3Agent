# A3Agent 构建和运行指南

## 问题诊断

如果打包后的 exe 文件闪退，通常是以下原因：

### 1. Python 环境未安装
应用需要系统安装 Python 3.8+ 环境。

**检查方法：**
```bash
python --version
```

### 2. Python 依赖未安装
应用需要以下 Python 包：
- fastapi
- uvicorn
- requests
- 其他依赖（见下方完整列表）

**安装依赖：**
```bash
cd python-backend
pip install fastapi uvicorn requests pyperclip urllib3
```

### 3. 资源文件未正确打包
检查构建产物中是否包含 `python-backend` 和 `frontend` 目录。

## 开发模式运行

```bash
npm run tauri dev
```

## 生产构建

```bash
npm run tauri build
```

构建产物位置：
- Windows: `src-tauri/target/release/bundle/`
- 可执行文件: `src-tauri/target/release/a3-agent.exe`

## 查看启动日志

如果应用闪退，查看日志文件：

**Windows:**
```bash
type %TEMP%\a3agent_startup.log
```

**Linux/Mac:**
```bash
cat /tmp/a3agent_startup.log
```

## 常见错误及解决方案

### 错误：Cannot find python-backend directory
**原因：** 资源文件未正确打包或路径配置错误
**解决：** 
1. 检查 `tauri.conf.json` 中的 `bundle.resources` 配置
2. 确保 `python-backend` 目录存在且包含 `headless_main.py`

### 错误：Failed to spawn Python process
**原因：** 系统未安装 Python 或 Python 不在 PATH 中
**解决：**
1. 安装 Python 3.8+
2. 将 Python 添加到系统 PATH
3. 重启终端/IDE

### 错误：ModuleNotFoundError
**原因：** Python 依赖包未安装
**解决：**
```bash
pip install fastapi uvicorn requests
```

## 打包注意事项

1. 确保 `.taurignore` 文件存在，避免打包不必要的文件
2. Python 后端代码会被打包到应用资源目录
3. 用户系统需要安装 Python 环境（应用不包含 Python 解释器）

## 改进建议

如果希望应用独立运行（不依赖系统 Python），可以考虑：
1. 使用 PyInstaller 将 Python 代码打包为独立可执行文件
2. 配置为 Tauri sidecar
3. 或使用嵌入式 Python 发行版
