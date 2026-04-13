# 快速开始 - 打包 macOS 应用

## 一键打包

```bash
# 1. 安装依赖（首次运行）
python3 -m pip install -r python-backend/requirements.txt

# 2. 检查环境
npm run check:mac

# 3. 运行打包脚本
npm run build:mac
```

## 打包产物

构建完成后，产物通常位于：

- **App**: `src-tauri/target/release/bundle/macos/`
- **DMG**: `src-tauri/target/release/bundle/dmg/`
- **Release 输出**: `src-tauri/target/release/`

## 配置文件管理

应用使用workspace机制管理配置：

更多 Mac 首次打包/运行步骤见 [MAC_SETUP.md](MAC_SETUP.md)。

### 首次运行
1. 双击 `A3Agent.app`
2. 自动创建 `~/Library/Application Support/A3Agent/workspace/ga_config/` 目录
3. 从应用资源复制默认配置到 workspace
4. 输出日志：`[Launch] Frozen runtime ...`

### 配置文件位置
```
A3Agent.app 的用户数据目录/
└── workspace/
    └── ga_config/
        ├── mykey.json          # API密钥配置
        ├── memory/             # 记忆文件
        ├── sche_tasks/         # 计划任务
        └── temp/               # 临时文件
```

### 修改配置
1. 编辑 `~/Library/Application Support/A3Agent/workspace/ga_config/mykey.json` 配置API密钥
2. 重启应用，配置自动生效
3. 所有生成的文件都保存在workspace中

### 配置迁移
- 复制整个 `workspace` 目录到新位置
- 配置和数据完整保留

### 重置配置
- 删除 `~/Library/Application Support/A3Agent/workspace`
- 重新运行应用，自动恢复默认配置

## 验证

运行打包好的应用：
```bash
open src-tauri/target/release/bundle/macos/A3Agent.app
```

检查：
1. ✅ 应用正常启动，无闪退
2. ✅ 窗口无多次闪烁
3. ✅ 自动创建 workspace 目录
4. ✅ 配置文件正确初始化

## 分发

将以下文件分发给用户：
- `A3Agent.app`
- 或 `A3Agent.dmg`

用户无需单独安装 Python 环境，双击即可运行。

## 故障排查

### 构建失败
- 确保关闭所有运行中的 A3Agent
- 删除 `src-tauri/target/release/` 下旧的构建产物
- 重新运行构建脚本

### 配置文件问题
- 查看启动日志中的 `[ConfigManager]` 信息
- 检查workspace目录权限
- 确认mykey.json格式正确

详细文档：
- [配置管理说明](CONFIG_MANAGEMENT.md)
- [完整构建指南](STANDALONE_BUILD.md)
- [故障排查](BUILD_GUIDE.md)
