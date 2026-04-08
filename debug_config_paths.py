"""
调试配置文件路径问题
"""
import os
import sys

# 模拟打包环境
print("=" * 60)
print("调试配置文件路径")
print("=" * 60)

# 1. 检查环境变量
print("\n1. 环境变量:")
print(f"   GA_WORKSPACE_ROOT: {os.environ.get('GA_WORKSPACE_ROOT', 'NOT SET')}")
print(f"   GA_USER_DATA_DIR: {os.environ.get('GA_USER_DATA_DIR', 'NOT SET')}")
print(f"   GA_BASE_DIR: {os.environ.get('GA_BASE_DIR', 'NOT SET')}")

# 2. 检查sys属性
print("\n2. Python环境:")
print(f"   sys.frozen: {getattr(sys, 'frozen', False)}")
print(f"   sys.executable: {sys.executable}")
if hasattr(sys, '_MEIPASS'):
    print(f"   sys._MEIPASS: {sys._MEIPASS}")
else:
    print(f"   sys._MEIPASS: NOT SET")

# 3. 导入并测试path_utils
print("\n3. 测试path_utils:")
sys.path.insert(0, 'python-backend')
from path_utils import (
    resource_dir,
    workspace_root_dir,
    workspace_config_dir,
    resolve_mykey_path,
    mykey_candidate_paths
)

print(f"   resource_dir(): {resource_dir()}")
print(f"   workspace_root_dir(): {workspace_root_dir()}")
print(f"   workspace_config_dir(): {workspace_config_dir()}")

# 4. 检查mykey路径候选
print("\n4. mykey.json候选路径:")
candidates = mykey_candidate_paths()
for i, path in enumerate(candidates, 1):
    exists = path.exists()
    print(f"   {i}. {path}")
    print(f"      存在: {exists}")
    if exists:
        print(f"      可读: {os.access(path, os.R_OK)}")
        print(f"      可写: {os.access(path, os.W_OK)}")

# 5. 解析最终路径
print("\n5. 最终解析路径:")
mykey_path = resolve_mykey_path(prefer_existing=True)
print(f"   prefer_existing=True: {mykey_path}")
if mykey_path:
    print(f"   存在: {mykey_path.exists()}")
    if mykey_path.exists():
        print(f"   可读: {os.access(mykey_path, os.R_OK)}")
        print(f"   可写: {os.access(mykey_path, os.W_OK)}")

mykey_path_new = resolve_mykey_path(prefer_existing=False)
print(f"   prefer_existing=False: {mykey_path_new}")

# 6. 测试config_manager
print("\n6. 测试config_manager:")
from config_manager import initialize_workspace_config, get_resource_path

workspace_root = initialize_workspace_config()
print(f"   workspace_root: {workspace_root}")
print(f"   GA_WORKSPACE_ROOT: {os.environ.get('GA_WORKSPACE_ROOT')}")
print(f"   GA_USER_DATA_DIR: {os.environ.get('GA_USER_DATA_DIR')}")

bundled_config = get_resource_path('ga_config')
print(f"   bundled_config: {bundled_config}")
print(f"   bundled_config存在: {os.path.exists(bundled_config)}")

if os.path.exists(bundled_config):
    print(f"   bundled_config内容:")
    for item in os.listdir(bundled_config):
        item_path = os.path.join(bundled_config, item)
        item_type = "目录" if os.path.isdir(item_path) else "文件"
        print(f"      - {item} ({item_type})")

print("\n" + "=" * 60)
