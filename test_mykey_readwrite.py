"""
测试配置文件初始化和读写
"""
import os
import sys
import json
import tempfile
import shutil

# 添加python-backend到路径
sys.path.insert(0, 'python-backend')

print("=" * 70)
print("测试配置文件初始化和读写")
print("=" * 70)

# 创建临时测试环境
test_dir = tempfile.mkdtemp(prefix="ga_test_")
print(f"\n测试目录: {test_dir}")

try:
    # 模拟打包环境
    os.environ["GA_WORKSPACE_ROOT"] = test_dir
    os.environ["GA_USER_DATA_DIR"] = os.path.join(test_dir, "ga_config")

    # 测试1: 导入path_utils
    print("\n" + "=" * 70)
    print("测试1: path_utils模块")
    print("=" * 70)
    from path_utils import (
        workspace_root_dir,
        workspace_config_dir,
        resolve_mykey_path,
    )

    workspace_root = workspace_root_dir()
    config_dir = workspace_config_dir()
    print(f"workspace_root: {workspace_root}")
    print(f"config_dir: {config_dir}")
    print(f"config_dir存在: {os.path.exists(config_dir)}")

    # 测试2: 创建mykey.json
    print("\n" + "=" * 70)
    print("测试2: 创建mykey.json")
    print("=" * 70)
    mykey_path = os.path.join(config_dir, "mykey.json")
    test_config = {
        "test_config": {
            "type": "oai",
            "apikey": "sk-test-key",
            "apibase": "https://api.openai.com",
            "model": "gpt-4"
        }
    }
    with open(mykey_path, "w", encoding="utf-8") as f:
        json.dump(test_config, f, indent=4)
    print(f"创建mykey.json: {mykey_path}")
    print(f"文件存在: {os.path.exists(mykey_path)}")
    print(f"文件大小: {os.path.getsize(mykey_path)} 字节")

    # 测试3: 读取mykey.json
    print("\n" + "=" * 70)
    print("测试3: 读取mykey.json")
    print("=" * 70)
    resolved_path = resolve_mykey_path(prefer_existing=True)
    print(f"resolve_mykey_path: {resolved_path}")
    if resolved_path and os.path.exists(resolved_path):
        with open(resolved_path, "r", encoding="utf-8") as f:
            loaded_config = json.load(f)
        print(f"成功读取配置: {list(loaded_config.keys())}")
        print(f"配置内容: {json.dumps(loaded_config, indent=2)}")
    else:
        print("ERROR: 无法解析mykey.json路径")

    # 测试4: 修改mykey.json
    print("\n" + "=" * 70)
    print("测试4: 修改mykey.json")
    print("=" * 70)
    test_config["new_config"] = {
        "type": "oai",
        "apikey": "sk-new-key",
        "apibase": "https://api.example.com",
        "model": "gpt-3.5-turbo"
    }
    with open(mykey_path, "w", encoding="utf-8") as f:
        json.dump(test_config, f, indent=4)
    print(f"修改mykey.json")

    # 重新读取验证
    with open(mykey_path, "r", encoding="utf-8") as f:
        loaded_config = json.load(f)
    print(f"重新读取配置: {list(loaded_config.keys())}")
    if "new_config" in loaded_config:
        print("✓ 修改成功")
    else:
        print("✗ 修改失败")

    # 测试5: 测试api_server的读写函数
    print("\n" + "=" * 70)
    print("测试5: 测试api_server的读写函数")
    print("=" * 70)
    from api_server import get_user_data_dir, resolve_mykey_path as api_resolve_mykey

    api_user_data_dir = get_user_data_dir()
    print(f"api get_user_data_dir: {api_user_data_dir}")

    api_mykey_path = api_resolve_mykey(api_user_data_dir, prefer_existing=True)
    print(f"api resolve_mykey_path: {api_mykey_path}")

    if api_mykey_path and os.path.exists(api_mykey_path):
        print("✓ API可以找到mykey.json")
    else:
        print("✗ API无法找到mykey.json")

    print("\n" + "=" * 70)
    print("所有测试完成")
    print("=" * 70)

finally:
    # 清理测试目录
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
        print(f"\n清理测试目录: {test_dir}")
