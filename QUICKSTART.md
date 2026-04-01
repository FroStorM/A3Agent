# 快速开始 - 打包独立exe

## 一键打包

```powershell
# 1. 安装依赖（首次运行）
pip install -r python-backend/requirements.txt

# 2. 运行打包脚本
.\build_standalone.ps1
```

## 打包产物

构建完成后，可执行文件位于：

- **独立exe**: `src-tauri\target\release\A3Agent.exe`
- **MSI安装包**: `src-tauri\target\release\bundle\msi\`
- **NSIS安装包**: `src-tauri\target\release\bundle\nsis\`

## 配置文件管理

应用使用workspace机制管理配置：

### 首次运行
1. 双击 `A3Agent.exe`
2. 自动创建 `workspace/ga_config/` 目录
3. 从exe复制默认配置到workspace
4. 输出日志：`[ConfigManager] 首次运行，初始化配置文件...`

### 配置文件位置
```
A3Agent.exe所在目录/
└── workspace/
    └── ga_config/
        ├── mykey.json          # API密钥配置
        ├── memory/             # 记忆文件
        ├── sche_tasks/         # 计划任务
        └── temp/               # 临时文件
```

### 修改配置
1. 编辑 `workspace/ga_config/mykey.json` 配置API密钥
2. 重启应用，配置自动生效
3. 所有生成的文件都保存在workspace中

### 配置迁移
- 复制整个 `workspace` 目录到新位置
- 配置和数据完整保留

### 重置配置
- 删除 `workspace` 目录
- 重新运行exe，自动恢复默认配置

## 验证

运行打包好的exe：
```powershell
.\src-tauri\target\release\A3Agent.exe
```

检查：
1. ✅ 应用正常启动，无闪退
2. ✅ 窗口无多次闪烁
3. ✅ 自动创建workspace目录
4. ✅ 配置文件正确初始化

## 分发

将以下文件分发给用户：
- `A3Agent.exe` - 独立可执行文件
- 或 MSI/NSIS安装包

用户无需安装Python环境，双击即可运行。

## 故障排查

### 构建失败
- 确保关闭所有运行中的A3Agent.exe
- 删除 `src-tauri/target/release/a3-agent.exe`
- 重新运行构建脚本

### 配置文件问题
- 查看启动日志中的 `[ConfigManager]` 信息
- 检查workspace目录权限
- 确认mykey.json格式正确

详细文档：
- [配置管理说明](CONFIG_MANAGEMENT.md)
- [完整构建指南](STANDALONE_BUILD.md)
- [故障排查](BUILD_GUIDE.md)
