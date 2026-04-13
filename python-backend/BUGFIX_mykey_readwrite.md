# Bug修复：mykey.json读取和写入失败

## 问题描述

打包后的系统能够获取到memory中的md文件，但是获取不到mykey.json，前端的操作也无法写入。

## 根本原因

### 1. headless_main.py中的代码错误

**位置**: `python-backend/headless_main.py:9-20`

**问题**: 
- `find_free_port()`函数的实现被错误地替换成了`_should_copy_file`的逻辑
- 缺少`SERVER_HOST`常量定义
- 缺少`emit()`函数定义

**影响**: 程序启动时会因为缺少这些定义而失败

### 2. 环境变量覆盖问题

**问题**:
- 文件开头调用了`config_manager.initialize_workspace_config()`设置环境变量
- 但`initialize_runtime()`函数在第170行被调用时会覆盖`GA_USER_DATA_DIR`
- 导致配置路径不一致

### 3. GA_USER_DATA_DIR路径错误

**问题**:
- 在打包模式下，`GA_USER_DATA_DIR`应该指向`workspace/ga_config`目录
- 但原代码指向了`workspace`目录
- 导致mykey.json的路径解析错误，API无法正确读写配置文件

## 修复方案

### 1. 修复headless_main.py中的代码错误

```python
# 添加缺失的函数和常量
def _should_copy_file(src, dst, overwrite_if_source_newer=False):
    try:
        if not os.path.isfile(dst):
            return True
        if os.path.getsize(dst) <= 0:
            return True
        if not overwrite_if_source_newer:
            return False
        return os.path.getmtime(src) > os.path.getmtime(dst)
    except Exception:
        return True

SERVER_HOST = "127.0.0.1"

def emit(msg):
    print(f"[Launch] {msg}", flush=True)
```

### 2. 移除重复的初始化调用

移除了文件开头的：
```python
from config_manager import initialize_workspace_config
workspace_root = initialize_workspace_config()
```

### 3. 修正initialize_runtime函数

**关键修改**:
```python
# 设置ga_config为用户数据目录（而不是workspace）
user_data_dir = str(workspace_config_dir(workspace_root))

# 正确设置环境变量
os.environ["GA_WORKSPACE_ROOT"] = workspace_root
os.environ["GA_USER_DATA_DIR"] = user_data_dir  # 指向ga_config目录
```

### 4. 改进_ensure_runtime_ga_config函数

**关键修改**:
- 只在mykey.json不存在或为空时才复制
- 不会覆盖用户已有的配置文件
- 添加了详细的日志输出

```python
# 复制配置文件（只在不存在时复制，不覆盖用户的配置）
for name in ("mykey.json", "mykey.py"):
    bundled_file = os.path.join(bundled_root, name)
    target_file = os.path.join(config_root, name)
    if os.path.isfile(bundled_file):
        if not os.path.exists(target_file):
            shutil.copy2(bundled_file, target_file)
            emit(f"Copied {name} from bundle to {target_file}")
        elif os.path.getsize(target_file) == 0:
            shutil.copy2(bundled_file, target_file)
            emit(f"Replaced empty {name} at {target_file}")
        else:
            emit(f"Keeping existing {name} at {target_file}")
```

## 修复后的路径结构

### 打包模式下的目录结构

```
用户目录/AppData/Roaming/A3Agent/  (workspace_root)
├── memory/                          # 从打包资源复制
├── assets/                          # 从打包资源复制
├── ga_config/                       # user_data_dir指向这里
│   ├── mykey.json                   # 配置文件
│   ├── memory/                      # SOP文件
│   └── temp/                        # 临时文件
└── workspace_history.json
```

### 环境变量设置

```
GA_WORKSPACE_ROOT = C:/Users/xxx/AppData/Roaming/A3Agent
GA_USER_DATA_DIR = C:/Users/xxx/AppData/Roaming/A3Agent/ga_config
GA_BASE_DIR = C:/Users/xxx/AppData/Local/Temp/_MEIxxxxxx (打包资源目录)
```

## 验证方法

### 1. 检查路径解析

```python
from path_utils import workspace_config_dir, resolve_mykey_path
import os

os.environ['GA_WORKSPACE_ROOT'] = 'C:/test_workspace'
config_dir = workspace_config_dir()
print(f'config_dir: {config_dir}')  # 应该输出: C:/test_workspace/ga_config

mykey_path = resolve_mykey_path(prefer_existing=False)
print(f'mykey_path: {mykey_path}')  # 应该输出: C:/test_workspace/ga_config/mykey.json
```

### 2. 检查启动日志

打包后运行时，应该看到类似的日志：
```
[Launch] Frozen runtime base_dir=... workspace_root=... user_data_dir=.../ga_config
[Launch] Ensuring ga_config at .../ga_config
[Launch] Copied mykey.json from bundle to .../ga_config/mykey.json
```

### 3. 测试API读写

- GET `/api/config/mykey` 应该返回 `{"exists": true, "path": ".../ga_config/mykey.json"}`
- POST `/api/config/mykey` 应该能成功写入配置
- POST `/api/llm_configs/upsert` 应该能成功更新配置

## 注意事项

1. **不要删除config_manager.py**: 虽然在headless_main.py中移除了它的调用，但其他模块可能还在使用
2. **重新打包**: 修复后需要重新运行打包流程
3. **清理旧配置**: 如果之前有测试过，建议删除旧的workspace目录重新测试

## 相关文件

- `python-backend/headless_main.py` - 主要修复文件
- `python-backend/path_utils.py` - 路径解析工具
- `python-backend/api_server.py` - API端点（读写mykey.json）
- `python-backend/config_manager.py` - 配置管理器（已不再使用）
