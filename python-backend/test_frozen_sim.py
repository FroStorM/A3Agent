"""
模拟 frozen (打包) 环境下的完整流程测试
- 模拟sys.frozen=True
- 模拟_MEIPASS（bundled资源目录）
- 模拟Tauri设置的 GA_WORKSPACE_ROOT 环境变量
- 在 F:\GA 下测试

核心问题验证：
1. 写入mykey后刷新能否读到新模型
2. 第二次启动ga_config目录是否重复复制
"""
import os, sys, json, shutil, types, importlib, tempfile

# ============================================================
# 测试配置
# ============================================================
TEST_WORKSPACE = r"F:\GA"
TEST_GA_CONFIG = os.path.join(TEST_WORKSPACE, "ga_config")
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLED_GA_CONFIG_STAGING = os.path.join(BACKEND_DIR, "build", "_ga_config_staging")

PASS = True  # 全局测试状态

def assert_eq(label, actual, expected):
    global PASS
    if actual == expected:
        print(f"  [OK] {label}")
    else:
        print(f"  [FAIL] {label}")
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")
        PASS = False

def assert_true(label, val):
    global PASS
    if val:
        print(f"  [OK] {label}")
    else:
        print(f"  [FAIL] {label}: was False/empty")
        PASS = False

def assert_false(label, val):
    global PASS
    if not val:
        print(f"  [OK] {label}")
    else:
        print(f"  [FAIL] {label}: expected False but was {val!r}")
        PASS = False

# ============================================================
# 模拟frozen环境
# ============================================================
class MockMEIPASS:
    """假装 sys._MEIPASS 指向bundled staging目录"""
    pass

def setup_frozen_env(workspace=TEST_WORKSPACE, meipass=None):
    """设置环境变量，模拟打包后Tauri启动时的状态"""
    if meipass is None:
        meipass = BUNDLED_GA_CONFIG_STAGING
        # 如果staging不存在，创建一个临时的
        if not os.path.exists(meipass):
            os.makedirs(os.path.join(meipass, "ga_config"), exist_ok=True)
            with open(os.path.join(meipass, "ga_config", "mykey.json"), "w") as f:
                json.dump({}, f)

    os.environ["GA_WORKSPACE_ROOT"] = workspace
    os.environ["GA_USER_DATA_DIR"] = os.path.join(workspace, "ga_config")
    os.environ["GA_BASE_DIR"] = BACKEND_DIR
    # 清掉可能干扰的变量
    os.environ.pop("GA_APP_DATA_DIR", None)
    os.environ.pop("GA_CONFIG_SRC_DIR", None)

    # 模拟sys.frozen和sys._MEIPASS
    sys.frozen = True
    sys._MEIPASS = meipass

    print(f"  [Env] GA_WORKSPACE_ROOT={workspace}")
    print(f"  [Env] GA_USER_DATA_DIR={os.environ['GA_USER_DATA_DIR']}")
    print(f"  [Env] GA_BASE_DIR={BACKEND_DIR}")
    print(f"  [Env] sys._MEIPASS={meipass}")

def teardown_frozen_env():
    if hasattr(sys, 'frozen'):
        del sys.frozen
    if hasattr(sys, '_MEIPASS'):
        del sys._MEIPASS

def reload_modules():
    """重新导入所有相关模块，模拟重启"""
    to_del = [k for k in sys.modules if k in ("api_server", "llmcore", "path_utils", "agentmain", "mykey")]
    for k in to_del:
        del sys.modules[k]
    importlib.invalidate_caches()

def clean_workspace():
    if os.path.exists(TEST_GA_CONFIG):
        shutil.rmtree(TEST_GA_CONFIG)
    os.makedirs(TEST_GA_CONFIG, exist_ok=True)

# ============================================================
# TEST 1: resolve_mykey_path 写入路径 == 读取路径
# ============================================================
def test_read_write_path_consistency():
    print("\n" + "="*60)
    print("TEST 1: 写入路径和读取路径一致性")
    print("="*60)

    clean_workspace()
    setup_frozen_env()
    reload_modules()

    from path_utils import resolve_mykey_path

    base = TEST_GA_CONFIG

    write_path = resolve_mykey_path(base, prefer_existing=False)
    read_path_before = resolve_mykey_path(base, prefer_existing=True)
    print(f"  write_path={write_path}")
    print(f"  read_path(before write)={read_path_before}")

    # 写入文件
    test_data = {"test_model": {"type": "oai", "apikey": "sk-xxx", "apibase": "https://api.openai.com/v1", "model": "gpt-4"}}
    with open(write_path, "w", encoding="utf-8") as f:
        json.dump(test_data, f, indent=2)

    read_path_after = resolve_mykey_path(base, prefer_existing=True)
    print(f"  read_path(after write)={read_path_after}")

    assert_eq("写入路径和写后读取路径一致", str(write_path), str(read_path_after))

    # 验证读到的内容正确
    with open(read_path_after, "r", encoding="utf-8") as f:
        read_data = json.load(f)
    assert_eq("读取内容与写入一致", read_data, test_data)

    teardown_frozen_env()

# ============================================================
# TEST 2: _ensure_default_mykey 不覆盖有内容的文件
# ============================================================
def test_ensure_no_overwrite():
    print("\n" + "="*60)
    print("TEST 2: _ensure_default_mykey 不覆盖有内容的用户文件")
    print("="*60)

    clean_workspace()
    setup_frozen_env()
    reload_modules()

    import api_server

    # 写入用户数据
    mykey_path = os.path.join(TEST_GA_CONFIG, "mykey.json")
    user_data = {"user_model": {"type": "oai", "apikey": "sk-secret", "apibase": "https://api.test.com/v1", "model": "gpt-4o"}}
    with open(mykey_path, "w", encoding="utf-8") as f:
        json.dump(user_data, f, indent=2)
    original_size = os.path.getsize(mykey_path)
    original_mtime = os.path.getmtime(mykey_path)
    print(f"  Written mykey: size={original_size}, mtime={original_mtime}")

    # 调用 _ensure_default_mykey（模拟重启时的调用）
    import time; time.sleep(0.05)  # 确保时间戳不同
    api_server._ensure_default_mykey(TEST_GA_CONFIG)

    new_size = os.path.getsize(mykey_path)
    with open(mykey_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    print(f"  After _ensure_default_mykey: size={new_size}")
    assert_eq("文件内容未被覆盖", result, user_data)

    teardown_frozen_env()

# ============================================================
# TEST 3: 完整流程 - 写入 -> 重启 -> 读取
# ============================================================
def test_full_write_restart_read():
    print("\n" + "="*60)
    print("TEST 3: 完整流程：写入 -> 模拟重启 -> 读取（最关键的测试）")
    print("="*60)

    clean_workspace()
    setup_frozen_env()
    reload_modules()

    import api_server
    from path_utils import resolve_mykey_path

    # --- 步骤1: 模拟POST /api/llm_configs 写入新模型 ---
    base = TEST_GA_CONFIG
    os.makedirs(base, exist_ok=True)

    # 先确保mykey.json存在（首次启动会创建）
    mykey_path = os.path.join(base, "mykey.json")
    if not os.path.exists(mykey_path):
        with open(mykey_path, "w") as f:
            json.dump({}, f)

    write_path = resolve_mykey_path(base, prefer_existing=False)
    module_before = api_server._load_mykey_module_from_path(write_path)
    order, values = api_server._read_mykey_simple_assignments(module_before)

    cid = "my_new_model"
    values[cid] = {"type": "oai", "apikey": "sk-newmodel123", "apibase": "https://api.openai.com/v1", "model": "gpt-4o-mini", "name": "My New Model"}
    if cid not in order:
        order.append(cid)
    content = api_server._render_mykey_py(order, values)

    final_path = resolve_mykey_path(base, prefer_existing=False)
    with open(final_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Step1: Written to {final_path}, size={os.path.getsize(final_path)}")

    # --- 步骤2: 模拟"刷新"（不重启，直接读）---
    read_path = resolve_mykey_path(base, prefer_existing=True)
    read_module = api_server._load_mykey_module_from_path(read_path)
    configs_immediate = api_server._extract_llm_configs_from_module(read_module)
    found_immediate = any(c.get("id") == cid for c in configs_immediate)
    print(f"  Step2 (immediate read): configs={[c.get('id') for c in configs_immediate]}")
    assert_true("写入后立即能读到新模型", found_immediate)

    # --- 步骤3: 模拟重启（重新import api_server）---
    reload_modules()
    setup_frozen_env()  # 重新设置环境变量
    import api_server as api_server2
    from path_utils import resolve_mykey_path as rmp2

    read_path2 = rmp2(base, prefer_existing=True)
    print(f"  Step3 (after restart): reading from {read_path2}")
    read_module2 = api_server2._load_mykey_module_from_path(read_path2)
    configs_after_restart = api_server2._extract_llm_configs_from_module(read_module2)
    found_after = any(c.get("id") == cid for c in configs_after_restart)
    print(f"  Step3 (after restart): configs={[c.get('id') for c in configs_after_restart]}")
    assert_true("重启后仍能读到写入的模型", found_after)

    teardown_frozen_env()

# ============================================================
# TEST 4: ga_config 目录第二次启动不重复复制
# ============================================================
def test_ga_config_no_duplicate_copy():
    print("\n" + "="*60)
    print("TEST 4: ga_config 第二次启动不重复复制文件")
    print("="*60)

    clean_workspace()
    setup_frozen_env()
    reload_modules()

    import api_server

    # 记录第一次启动后的文件列表和mtime
    first_files = {}
    for root, dirs, files in os.walk(TEST_GA_CONFIG):
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, TEST_GA_CONFIG)
            first_files[rel] = (os.path.getsize(p), os.path.getmtime(p))
    print(f"  After 1st launch: {list(first_files.keys())}")

    import time; time.sleep(0.1)

    # 模拟第二次启动
    reload_modules()
    setup_frozen_env()
    import api_server as api2

    second_files = {}
    for root, dirs, files in os.walk(TEST_GA_CONFIG):
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, TEST_GA_CONFIG)
            second_files[rel] = (os.path.getsize(p), os.path.getmtime(p))
    print(f"  After 2nd launch: {list(second_files.keys())}")

    # 检查文件mtime是否被修改（如果被修改说明重新复制了）
    overwritten = []
    for rel, (size2, mtime2) in second_files.items():
        if rel in first_files:
            size1, mtime1 = first_files[rel]
            if mtime2 > mtime1:
                overwritten.append(rel)
                print(f"  [WARN] {rel}: mtime changed {mtime1} -> {mtime2}")

    assert_false("第二次启动没有重新写文件（mtime不变）", overwritten)

    teardown_frozen_env()

# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    PASS = True

    if not os.path.exists(TEST_WORKSPACE):
        os.makedirs(TEST_WORKSPACE, exist_ok=True)

    try:
        test_read_write_path_consistency()
        test_ensure_no_overwrite()
        test_full_write_restart_read()
        test_ga_config_no_duplicate_copy()
    finally:
        teardown_frozen_env()
        if os.path.exists(TEST_GA_CONFIG):
            shutil.rmtree(TEST_GA_CONFIG)
        print(f"\n[Cleanup] {TEST_GA_CONFIG} removed")

    print("\n" + "="*60)
    if PASS:
        print("所有测试通过 ✓")
        sys.exit(0)
    else:
        print("有测试失败 ✗")
        sys.exit(1)
