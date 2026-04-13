# A3Agent macOS 独立打包指南

## 概述

本指南将帮助你创建一个完全独立的 A3Agent macOS 应用，无需用户安装 Python 环境即可运行。

## 打包原理

1. **PyInstaller** 将 Python 后端及其所有依赖打包成独立的可执行文件
2. **Tauri Sidecar** 将打包好的 Python 可执行文件嵌入到 Tauri 应用中
3. **最终产物** 是一个包含完整运行环境的 `.app` 或 `.dmg`

## 快速开始

### 方法 1：使用自动化脚本（推荐）

```bash
# 检查环境
npm run check:mac

# 完整打包（包括 Python 后端和 Tauri 应用）
npm run build:mac
```

### 方法 2：手动分步打包

#### 步骤 1：安装依赖

```bash
# 安装 Python 依赖（包括 PyInstaller）
python3 -m pip install -r python-backend/requirements.txt
```

#### 步骤 2：打包 Python 后端

```bash
# 在 python-backend 目录下
cd python-backend
python3 -m PyInstaller headless_main.spec --clean
```

这将在 `python-backend/dist/python-backend/` 目录下生成独立的 Python 可执行文件。

#### 步骤 3：配置 Tauri Sidecar

```bash
# 创建 sidecar 目录
mkdir -p src-tauri/binaries

# 复制 Python 后端（Apple Silicon）
cp python-backend/dist/python-backend/python-backend src-tauri/binaries/python-backend-aarch64-apple-darwin

# 如果是 Intel Mac，请使用：
# cp python-backend/dist/python-backend/python-backend src-tauri/binaries/python-backend-x86_64-apple-darwin
```

#### 步骤 4：构建 Tauri 应用

```bash
npm run tauri build
```

## 构建产物

构建完成后，你会在以下位置找到文件：

### macOS
- **App**: `src-tauri/target/release/bundle/macos/A3Agent.app`
- **DMG**: `src-tauri/target/release/bundle/dmg/`
- **Release 输出**: `src-tauri/target/release/`

### 文件说明
- `.app` 文件：macOS 应用程序包，可直接双击运行
- `.dmg` 文件：macOS 分发镜像，适合发布给用户

## 解决窗口闪烁问题

已在代码中实现以下优化：

1. **初始隐藏窗口** - 主窗口初始设置为不可见
2. **延迟显示** - 等待 Python 后端启动并返回端口后再显示窗口
3. **平滑过渡** - 添加短暂延迟确保页面加载完成

配置位置：
- [tauri.conf.json](../src-tauri/tauri.conf.json) - `"visible": false`
- [lib.rs](../src-tauri/src/lib.rs) - 窗口显示逻辑

## 验证打包结果

### 1. 检查 Python 后端

```bash
# 测试打包的 Python 后端
cd python-backend/dist/python-backend
./python-backend 8000

# 应该看到类似输出：
# [Launch] Using port 8000
# PORT:8000
```

### 2. 检查 Sidecar 配置

```bash
# 确认文件存在
ls src-tauri/binaries/python-backend-aarch64-apple-darwin
```

### 3. 测试最终应用

运行构建的应用，检查：
- ✅ 应用启动无闪烁
- ✅ 托盘图标正常显示
- ✅ 悬浮窗口正常显示
- ✅ 主窗口能正常打开并加载界面
- ✅ 在没有安装 Python 的系统上也能运行

## 故障排除

### 问题 1：PyInstaller 打包失败

**错误**: `ModuleNotFoundError: No module named 'xxx'`

**解决**:
1. 检查 `headless_main.spec` 中的 `hiddenimports` 列表
2. 添加缺失的模块：
   ```python
   hiddenimports = [
       'uvicorn.logging',
       'your_missing_module',
   ]
   ```

### 问题 2：Sidecar 未找到

**错误**: 日志显示 "Sidecar not available"

**解决**:
1. 确认文件名格式正确：`python-backend-{arch}-apple-darwin`
2. Apple Silicon: `python-backend-aarch64-apple-darwin`
3. Intel Mac: `python-backend-x86_64-apple-darwin`
4. 检查文件是否在 `src-tauri/binaries/` 目录

### 问题 3：资源文件未找到

**错误**: Python 后端无法找到 `assets/` 或 `memory/` 目录

**解决**:
1. 检查 `headless_main.spec` 中的 `datas` 配置
2. 确保相对路径正确
3. 使用 `get_resource_path()` 函数访问资源

### 问题 4：应用体积过大

**优化方案**:
1. 在 `headless_main.spec` 中添加更多排除项：
   ```python
   excludes=[
       'tkinter',
       'matplotlib',
       'numpy',
       'pandas',
       # 添加其他不需要的库
   ]
   ```
2. 启用 UPX 压缩（已默认启用）
3. 使用 `--onefile` 模式（但启动会稍慢）

## 高级配置

### 单文件模式

如果你想微调 PyInstaller 的打包参数，当前 `headless_main.spec` 已经采用 onefile 方案，可直接参考其中的 `EXE(...)` 配置：

```python
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,  # 添加这行
    a.zipfiles,  # 添加这行
    a.datas,     # 添加这行
    [],
    name='python-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

```

注意：单文件模式启动会稍慢，因为需要先解压到临时目录。

### 自定义图标

1. 准备 `.icns` 文件
2. 在 spec 文件中添加：
   ```python
   exe = EXE(
       ...
       icon='path/to/icon.icns',
   )
   ```

## 分发建议

### 推荐分发方式

1. **DMG 安装包**（推荐）
   - 标准 macOS 分发方式
   - 双击挂载后拖拽安装
   - 文件：`A3Agent_0.1.0_aarch64.dmg`

2. **App 包**
   - 适合内部测试和快速分发
   - 文件：`A3Agent.app`

### 文件清单

分发时应包含：
```
A3Agent/
├── A3Agent.app
└── A3Agent_0.1.0_aarch64.dmg
```

## 性能优化

### 启动速度优化

1. **减少 Python 包体积** - 只打包必需的依赖
2. **使用目录模式** - 比单文件模式启动更快
3. **预加载资源** - 在后台提前加载常用资源

### 内存优化

1. **延迟导入** - 只在需要时导入大型库
2. **清理临时文件** - 定期清理 temp 目录
3. **限制历史记录** - 设置合理的历史条数上限

## 更新和维护

### 版本更新

1. 修改 `src-tauri/tauri.conf.json` 中的版本号
2. 重新运行打包脚本
3. 生成的安装包会包含新版本号

### 自动更新

Tauri 支持自动更新功能，需要：
1. 配置更新服务器
2. 在 `tauri.conf.json` 中启用 updater
3. 签名发布文件

详见：https://tauri.app/v1/guides/distribution/updater

## 总结

使用本指南，你可以创建一个完全独立的 A3Agent 应用，用户无需安装任何依赖即可使用。打包后的应用包含：

- ✅ 完整的 Python 运行环境
- ✅ 所有 Python 依赖包
- ✅ 前端资源文件
- ✅ Tauri 桌面应用框架

用户只需双击 App 或 DMG 即可使用。
