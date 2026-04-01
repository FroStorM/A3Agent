# 配置文件管理说明

## 概述

应用使用workspace机制管理配置文件，确保：
1. 默认配置打包在exe中
2. 首次运行时自动初始化配置
3. 后续运行使用用户的配置文件
4. 配置文件可以被修改和持久化

## 目录结构

```
A3Agent.exe所在目录/
└── workspace/
    └── ga_config/
        ├── mykey.json          # API密钥配置
        ├── memory/             # 记忆文件
        ├── sche_tasks/         # 计划任务
        └── temp/               # 临时文件
```

## 工作原理

### 1. 首次运行

当应用首次运行时：
- 检测到 `workspace/ga_config/mykey.json` 不存在
- 自动从exe内置的默认配置复制到workspace
- 输出日志：`[ConfigManager] 首次运行，初始化配置文件...`

### 2. 后续运行

当应用再次运行时：
- 检测到配置文件已存在
- 直接使用workspace中的配置
- 输出日志：`[ConfigManager] 配置文件已存在，使用现有配置`

### 3. 配置文件读写

所有配置文件的读写都指向 `workspace/ga_config/` 目录：
- 读取配置：从workspace读取
- 写入配置：写入workspace
- 生成的文件：保存到workspace

## 技术实现

### config_manager.py

新增的配置管理模块，提供：

```python
# 初始化workspace配置
initialize_workspace_config()

# 获取配置文件路径
get_config_path('mykey.json')
```

### headless_main.py

启动时自动初始化：

```python
from config_manager import initialize_workspace_config
workspace_config_dir = initialize_workspace_config()
os.environ['GA_USER_DATA_DIR'] = workspace_config_dir
```

### headless_main.spec

PyInstaller配置中包含默认配置：

```python
datas = [
    ('assets', 'assets'),
    ('memory', 'memory'),
    ('../ga_config', 'ga_config'),  # 打包默认配置
]
```

## 使用场景

### 场景1：分发给用户

1. 用户下载 `A3Agent.exe`
2. 双击运行
3. 自动创建 `workspace/ga_config/` 并复制默认配置
4. 用户可以编辑 `workspace/ga_config/mykey.json` 配置API密钥

### 场景2：配置迁移

1. 复制整个 `workspace` 目录
2. 粘贴到新的exe所在目录
3. 运行exe，自动使用已有配置

### 场景3：重置配置

1. 删除 `workspace` 目录
2. 重新运行exe
3. 自动恢复默认配置

## 注意事项

1. **不要修改exe内的配置**：exe内的配置是只读的，仅用于首次初始化
2. **备份workspace**：所有用户数据都在workspace中，建议定期备份
3. **配置文件格式**：修改配置文件时注意保持JSON格式正确
4. **路径问题**：workspace始终在exe所在目录下，不受工作目录影响

## 开发模式

在开发模式下（非打包exe）：
- 默认配置从项目根目录的 `ga_config/` 读取
- workspace创建在项目根目录下
- 行为与打包后一致，便于测试
