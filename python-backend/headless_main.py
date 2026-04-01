import asyncio, threading, sys, time, os, atexit, socket, runpy, urllib.request, shutil
from path_utils import app_root_dir, config_dir_name, ensure_dir, resource_dir, temp_dir, workspace_config_dir

# 初始化配置文件 - 必须在导入其他模块之前完成
from config_manager import initialize_workspace_config
workspace_root = initialize_workspace_config()
# 环境变量已在initialize_workspace_config中设置

def find_free_port():
    sock = socket.socket()
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


def _copy_tree_defaults(source_root, dest_root, overwrite_if_source_newer=False):
    if not os.path.isdir(source_root):
        return
    os.makedirs(dest_root, exist_ok=True)
    ignored_dir = config_dir_name()
    for cur_root, dirs, files in os.walk(source_root):
        dirs[:] = [
            d for d in dirs
            if isinstance(d, str)
            and d not in ("__pycache__", ignored_dir, "temp")
            and not d.startswith(".")
        ]
        rel = os.path.relpath(cur_root, source_root)
        out_dir = dest_root if rel == "." else os.path.join(dest_root, rel)
        os.makedirs(out_dir, exist_ok=True)
        for entry in files:
            if not isinstance(entry, str) or entry.startswith(".") or entry.endswith((".pyc", ".pyo")):
                continue
            src = os.path.join(cur_root, entry)
            dst = os.path.join(out_dir, entry)
            if _should_copy_file(src, dst, overwrite_if_source_newer=overwrite_if_source_newer):
                shutil.copy2(src, dst)


def _ensure_runtime_ga_config(base_dir, workspace_root):
    bundled_root = os.path.join(base_dir, config_dir_name())
    if not os.path.isdir(bundled_root):
        return
    config_root = str(workspace_config_dir(workspace_root))
    legacy_root = os.path.join(config_root, config_dir_name())
    if os.path.isdir(legacy_root):
        legacy_memory = os.path.join(legacy_root, "memory")
        if os.path.isdir(legacy_memory):
            _copy_tree_defaults(legacy_memory, os.path.join(config_root, "memory"), overwrite_if_source_newer=True)
        for name in ("mykey.json", "mykey.py"):
            legacy_file = os.path.join(legacy_root, name)
            target_file = os.path.join(config_root, name)
            if os.path.isfile(legacy_file) and _should_copy_file(legacy_file, target_file, overwrite_if_source_newer=True):
                shutil.copy2(legacy_file, target_file)
        shutil.rmtree(legacy_root, ignore_errors=True)
    bundled_memory = os.path.join(bundled_root, "memory")
    if os.path.isdir(bundled_memory):
        _copy_tree_defaults(bundled_memory, os.path.join(config_root, "memory"))
    for name in ("mykey.json", "mykey.py"):
        bundled_file = os.path.join(bundled_root, name)
        target_file = os.path.join(config_root, name)
        if os.path.isfile(bundled_file) and _should_copy_file(bundled_file, target_file, overwrite_if_source_newer=True):
            shutil.copy2(bundled_file, target_file)

def initialize_runtime():
    base_dir = str(resource_dir())
    is_frozen = getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS") or ".app/Contents/Resources" in base_dir
    if is_frozen:
        if os.environ.get("AI_AGENT") == "TRAE" or os.environ.get("TRAE_SANDBOX_CLI_PATH"):
            user_data_dir = "/tmp/A3Agent"
        else:
            user_data_dir = str(app_root_dir("A3Agent"))
        ensure_dir(user_data_dir)
        bundle_memory = os.path.join(base_dir, "memory")
        user_memory = os.path.join(user_data_dir, "memory")
        if not os.path.exists(user_memory):
            if os.path.exists(bundle_memory):
                shutil.copytree(bundle_memory, user_memory)
            else:
                ensure_dir(user_memory)
        bundle_assets = os.path.join(base_dir, "assets")
        user_assets = os.path.join(user_data_dir, "assets")
        if not os.path.exists(user_assets) and os.path.exists(bundle_assets):
            shutil.copytree(bundle_assets, user_assets)
        _ensure_runtime_ga_config(base_dir, user_data_dir)
        temp_dir(root=user_data_dir)
        os.chdir(user_data_dir)
        os.environ["GA_USER_DATA_DIR"] = user_data_dir
        if user_data_dir not in sys.path:
            sys.path.insert(0, user_data_dir)
        if base_dir not in sys.path:
            sys.path.insert(1, base_dir)
        emit(f"Frozen runtime base_dir={base_dir} user_data_dir={user_data_dir}")
    else:
        user_data_dir = base_dir
        os.chdir(base_dir)
        os.environ["GA_USER_DATA_DIR"] = user_data_dir
        emit(f"Dev runtime base_dir={base_dir}")
    os.environ["GA_BASE_DIR"] = base_dir
    frontend_dir = os.path.join(base_dir, "frontend")
    if os.path.exists(os.path.join(frontend_dir, "index.html")):
        os.environ["GA_FRONTEND_DIR"] = frontend_dir
    return base_dir, user_data_dir

def reserve_server_socket(port=0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((SERVER_HOST, int(port)))
    sock.listen(2048)
    return sock

def wait_for_server(port, timeout=20):
    deadline = time.time() + timeout
    last_err = None
    url = f"http://{SERVER_HOST}:{int(port)}/api/status"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.getcode() == 200:
                    return True
        except Exception as e:
            last_err = e
            time.sleep(0.2)
    if last_err is not None:
        print(f"[Launch] Server readiness probe failed: {last_err}", flush=True)
    return False

def start_api_server(server_socket):
    import uvicorn
    from api_server import app as fastapi_app
    port = server_socket.getsockname()[1]
    config = uvicorn.Config(
        fastapi_app,
        host=SERVER_HOST,
        port=int(port),
        log_level="warning",
        loop="asyncio",
        http="h11",
        ws="none",
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve(sockets=[server_socket]))


def start_script(script_filename):
    script_dir = str(resource_dir())
    script_path = os.path.join(script_dir, script_filename)
    runpy.run_path(script_path, run_name="__main__")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('port', nargs='?', default='0')
    parser.add_argument('--tg', action='store_true', help='启动 Telegram Bot')
    parser.add_argument('--qq', action='store_true', help='启动 QQ Bot')
    parser.add_argument('--feishu', '--fs', dest='feishu', action='store_true', help='启动 Feishu Bot')
    parser.add_argument('--wecom', action='store_true', help='启动 WeCom Bot')
    parser.add_argument('--dingtalk', '--dt', dest='dingtalk', action='store_true', help='启动 DingTalk Bot')
    parser.add_argument('--no-sched', action='store_true', help='不启动计划任务调度器')
    parser.add_argument('--llm_no', type=int, default=0, help='LLM编号')
    args = parser.parse_args()

    initialize_runtime()
    server_socket = reserve_server_socket(0 if args.port == '0' else int(args.port))
    port = str(server_socket.getsockname()[1])
    emit(f"Reserved port {port}")
    
    server_thread = threading.Thread(target=start_api_server, args=(server_socket,), daemon=True)
    server_thread.start()
    if not wait_for_server(port):
        emit(f"Server failed to start on port {port}")
        sys.exit(1)
    emit(f"API server ready on {SERVER_HOST}:{port}")

    if args.tg:
        threading.Thread(target=start_script, args=("tgapp.py",), daemon=True).start()
        emit("Telegram Bot started")
    else: emit("Telegram Bot not enabled (use --tg to start)")

    if args.qq:
        threading.Thread(target=start_script, args=("qqapp.py",), daemon=True).start()
        emit("QQ Bot started")
    else: emit("QQ Bot not enabled (use --qq to start)")

    if args.feishu:
        threading.Thread(target=start_script, args=("fsapp.py",), daemon=True).start()
        emit("Feishu Bot started")
    else: emit("Feishu Bot not enabled (use --feishu to start)")

    if args.wecom:
        threading.Thread(target=start_script, args=("wecomapp.py",), daemon=True).start()
        emit("WeCom Bot started")
    else: emit("WeCom Bot not enabled (use --wecom to start)")

    if args.dingtalk:
        threading.Thread(target=start_script, args=("dingtalkapp.py",), daemon=True).start()
        emit("DingTalk Bot started")
    else: emit("DingTalk Bot not enabled (use --dingtalk to start)")
    
    if not args.no_sched:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.bind(('127.0.0.1', 45762)); sock.listen(1)
            import agentmain
            agentmain.start_scheduled_scheduler(llm_no=args.llm_no)
            atexit.register(sock.close)
            emit("Task Scheduler started")
        except OSError:
            emit("Task Scheduler already running (port occupied)")
    else: emit("Task Scheduler disabled (--no-sched)")

    print(f'PORT:{port}', flush=True)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        emit("Exiting...")
