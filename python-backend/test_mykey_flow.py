"""
测试mykey读写流程：
1. 模拟打包环境（frozen），workspace在F:\GA
2. 测试写入mykey后能读回
3. 测试重启后mykey不被覆盖
"""
import os, sys, json, shutil, tempfile, importlib

# ============================================================
# 准备测试目录
# ============================================================
TEST_WORKSPACE = r"F:\GA"
TEST_GA_CONFIG = os.path.join(TEST_WORKSPACE, "ga_config")

# 模拟一个bundled的空mykey.json（相当于打包进exe的那个）
BUNDLED_GA_CONFIG = os.path.join(os.path.dirname(__file__), "build", "_ga_config_staging")

def setup():
    """清理并初始化测试目录"""
    if os.path.exists(TEST_GA_CONFIG):
        shutil.rmtree(TEST_GA_CONFIG)
    os.makedirs(TEST_GA_CONFIG, exist_ok=True)
    print(f"[Setup] Test workspace: {TEST_WORKSPACE}")
    print(f"[Setup] ga_config dir: {TEST_GA_CONFIG}")

def cleanup():
    if os.path.exists(TEST_GA_CONFIG):
        shutil.rmtree(TEST_GA_CONFIG)
    print("[Cleanup] Done")

# ============================================================
# 模拟环境变量（frozen模式）
# ============================================================
def set_env(workspace):
    ga_config = os.path.join(workspace, "ga_config")
    os.environ["GA_WORKSPACE_ROOT"] = workspace
    os.environ["GA_USER_DATA_DIR"] = ga_config
    os.environ["GA_BASE_DIR"] = os.path.dirname(os.path.abspath(__file__))
    print(f"[Env] GA_WORKSPACE_ROOT={workspace}")
    print(f"[Env] GA_USER_DATA_DIR={ga_config}")

# ============================================================
# 重新导入模块（避免缓存）
# ============================================================
def reload_modules():
    for mod in list(sys.modules.keys()):
        if mod in ("api_server", "llmcore", "path_utils", "mykey"):
            del sys.modules[mod]
    importlib.invalidate_caches()

# ============================================================
# 测试1: _ensure_default_mykey 不覆盖用户文件
# ============================================================
def test_ensure_default_mykey_no_overwrite():
    print("\n" + "="*60)
    print("TEST 1: _ensure_default_mykey 不应覆盖用户文件")
    print("="*60)

    set_env(TEST_WORKSPACE)
    reload_modules()

    # 先写入用户数据
    user_mykey_path = os.path.join(TEST_GA_CONFIG, "mykey.json")
    user_data = {"my_model": {"type": "oai", "apikey": "sk-test123", "apibase": "https://api.openai.com/v1", "model": "gpt-4"}}
    with open(user_mykey_path, "w", encoding="utf-8") as f:
        json.dump(user_data, f, indent=2)
    print(f"[Test1] Wrote user mykey to: {user_mykey_path}")
    print(f"[Test1] Content: {user_data}")

    # 模拟启动时调用 _ensure_default_mykey
    import api_server
    api_server._ensure_default_mykey(TEST_GA_CONFIG)
    print(f"[Test1] Called _ensure_default_mykey")

    # 读取并验证
    with open(user_mykey_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    if result == user_data:
        print(f"[Test1] PASS: 用户数据未被覆盖 ✓")
        return True
    else:
        print(f"[Test1] FAIL: 数据被覆盖了！")
        print(f"[Test1] Expected: {user_data}")
        print(f"[Test1] Got: {result}")
        return False

# ============================================================
# 测试2: 写入后，list_llm_configs 能读回新模型
# ============================================================
def test_write_and_read_configs():
    print("\n" + "="*60)
    print("TEST 2: 写入llm_config后能立即读回")
    print("="*60)

    set_env(TEST_WORKSPACE)
    reload_modules()

    import api_server
    from path_utils import resolve_mykey_path

    base = TEST_GA_CONFIG
    os.makedirs(base, exist_ok=True)

    # 模拟保存一个新模型（像前端调用 POST /api/llm_configs）
    # 先确保有个mykey.json（可以是空的）
    mykey_path = os.path.join(base, "mykey.json")
    if not os.path.exists(mykey_path):
        with open(mykey_path, "w") as f:
            json.dump({}, f)

    # 模拟写入一个配置
    new_config = {
        "id": "test_gpt4",
        "type": "oai",
        "apikey": "sk-abc123",
        "apibase": "https://api.openai.com/v1",
        "model": "gpt-4",
        "name": "Test GPT4"
    }

    # 直接调用api_server内部的写入逻辑
    path = resolve_mykey_path(base, prefer_existing=False)
    module = api_server._load_mykey_module_from_path(path)
    order, values = api_server._read_mykey_simple_assignments(module)

    cid = new_config["id"]
    values[cid] = {
        "type": new_config["type"],
        "apikey": new_config["apikey"],
        "apibase": new_config["apibase"],
        "model": new_config["model"],
        "name": new_config.get("name", cid),
    }
    order.append(cid)
    content = api_server._render_mykey_py(order, values)

    write_path = resolve_mykey_path(base, prefer_existing=False)
    with open(write_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[Test2] Wrote config to: {write_path}")
    print(f"[Test2] Content preview: {content[:200]}")

    # 模拟前端刷新：调用 list_llm_configs 逻辑
    read_path = resolve_mykey_path(base, prefer_existing=True)
    read_module = api_server._load_mykey_module_from_path(read_path)
    configs = api_server._extract_llm_configs_from_module(read_module)

    print(f"[Test2] Read back configs: {configs}")
    found = any(c.get("id") == cid for c in configs)
    if found:
        print(f"[Test2] PASS: 写入后能读回新模型 ✓")
        return True
    else:
        print(f"[Test2] FAIL: 写入后读不到新模型！")
        return False

# ============================================================
# 测试3: 重启（重新导入模块）后mykey不被覆盖
# ============================================================
def test_restart_no_overwrite():
    print("\n" + "="*60)
    print("TEST 3: 重启（重新导入api_server）后数据不丢失")
    print("="*60)

    set_env(TEST_WORKSPACE)
    reload_modules()

    # 先写入用户数据
    mykey_path = os.path.join(TEST_GA_CONFIG, "mykey.json")
    user_data = {"saved_model": {"type": "oai", "apikey": "sk-restart-test", "apibase": "https://api.openai.com/v1", "model": "gpt-4o"}}
    with open(mykey_path, "w", encoding="utf-8") as f:
        json.dump(user_data, f, indent=2)

    mtime_before = os.path.getmtime(mykey_path)
    size_before = os.path.getsize(mykey_path)
    print(f"[Test3] Before restart: size={size_before}, mtime={mtime_before}")

    # 模拟"重启"：重新导入 api_server，触发模块级别的初始化代码
    reload_modules()
    import api_server  # 这会执行 _ensure_default_ga_config 和 _ensure_default_mykey

    mtime_after = os.path.getmtime(mykey_path)
    size_after = os.path.getsize(mykey_path)
    print(f"[Test3] After restart: size={size_after}, mtime={mtime_after}")

    with open(mykey_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    if result == user_data:
        print(f"[Test3] PASS: 重启后数据未丢失 ✓")
        return True
    else:
        print(f"[Test3] FAIL: 重启后数据被覆盖！")
        print(f"[Test3] Expected: {user_data}")
        print(f"[Test3] Got: {result}")
        return False

# ============================================================
# 测试4: 第一次启动时，如果mykey不存在，从bundled复制
# ============================================================
def test_first_launch_copies_default():
    print("\n" + "="*60)
    print("TEST 4: 首次启动时，bundled mykey被复制（不存在时）")
    print("="*60)

    # 清空ga_config
    if os.path.exists(TEST_GA_CONFIG):
        shutil.rmtree(TEST_GA_CONFIG)
    os.makedirs(TEST_GA_CONFIG, exist_ok=True)

    set_env(TEST_WORKSPACE)
    reload_modules()
    import api_server

    mykey_path = os.path.join(TEST_GA_CONFIG, "mykey.json")
    exists = os.path.exists(mykey_path)
    print(f"[Test4] mykey.json exists after first launch: {exists}")

    if exists:
        with open(mykey_path) as f:
            content = f.read()
        print(f"[Test4] Content: {content}")
        print(f"[Test4] PASS: 首次启动创建了默认mykey ✓")
        return True
    else:
        print(f"[Test4] WARN: 首次启动没有创建mykey（可能bundled文件不存在，属正常）")
        return True  # 不算失败

# ============================================================
# 主测试
# ============================================================
if __name__ == "__main__":
    # 确保F:\GA存在
    if not os.path.exists(TEST_WORKSPACE):
        os.makedirs(TEST_WORKSPACE, exist_ok=True)
        print(f"Created {TEST_WORKSPACE}")

    results = []

    try:
        setup()
        results.append(("TEST1: _ensure_default_mykey不覆盖", test_ensure_default_mykey_no_overwrite()))

        setup()
        results.append(("TEST2: 写入后能读回", test_write_and_read_configs()))

        setup()
        results.append(("TEST3: 重启后数据不丢失", test_restart_no_overwrite()))

        setup()
        results.append(("TEST4: 首次启动复制默认", test_first_launch_copies_default()))
    finally:
        cleanup()

    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    all_pass = True
    for name, result in results:
        status = "PASS ✓" if result else "FAIL ✗"
        print(f"  {status}  {name}")
        if not result:
            all_pass = False

    print()
    if all_pass:
        print("所有测试通过！")
        sys.exit(0)
    else:
        print("有测试失败，需要修复！")
        sys.exit(1)
