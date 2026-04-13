import asyncio, threading, sys, time, os, atexit, socket, runpy, urllib.request, shutil
from path_utils import app_root_dir, config_dir_name, ensure_dir, resource_dir, temp_dir, workspace_config_dir

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


def _bundle_ga_config_roots(base_dir):
    roots = []
    for candidate in (os.path.join(base_dir, "ga_config"), base_dir):
        if os.path.isdir(candidate):
            roots.append(candidate)
    return roots


def _ensure_runtime_ga_config(base_dir, workspace_root):
    """确保运行时ga_config目录存在并包含必要的配置文件"""
    config_root = str(workspace_config_dir(workspace_root))
    emit(f"Ensuring ga_config at {config_root}")

    # 处理旧版本的嵌套ga_config目录
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

    bundle_roots = _bundle_ga_config_roots(base_dir)
    if not bundle_roots:
        emit(f"Warning: bundled ga_config source not found under {base_dir}")
        return

    for bundled_root in bundle_roots:
        # 复制memory目录（只在目标目录不存在时复制，避免重复复制）
        bundled_memory = os.path.join(bundled_root, "memory")
        target_memory = os.path.join(config_root, "memory")
        if os.path.isdir(bundled_memory) and not os.path.exists(target_memory):
            _copy_tree_defaults(bundled_memory, target_memory)
            emit(f"Copied memory directory to {target_memory}")
        elif os.path.exists(target_memory):
            emit(f"Keeping existing memory directory at {target_memory}")

        # 复制assets目录（只在目标目录不存在时复制，避免重复复制）
        bundled_assets = os.path.join(bundled_root, "assets")
        target_assets = os.path.join(config_root, "assets")
        if os.path.isdir(bundled_assets) and not os.path.exists(target_assets):
            _copy_tree_defaults(bundled_assets, target_assets)
            emit(f"Copied assets directory to {target_assets}")
        elif os.path.exists(target_assets):
            emit(f"Keeping existing assets directory at {target_assets}")

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

def initialize_runtime():
    base_dir = str(resource_dir())
    is_frozen = getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS") or ".app/Contents/Resources" in base_dir
    if is_frozen:
        # 便携模式：始终使用exe所在目录作为workspace_root
        # 优先使用环境变量（Tauri设置的），否则使用exe目录
        workspace_root = os.environ.get("GA_WORKSPACE_ROOT")
        if not workspace_root:
            if getattr(sys, 'frozen', False):
                exe_dir = os.path.dirname(os.path.abspath(sys.executable))
                workspace_root = exe_dir
                emit(f"Portable mode: using exe directory as workspace: {workspace_root}")
            elif os.environ.get("AI_AGENT") == "TRAE" or os.environ.get("TRAE_SANDBOX_CLI_PATH"):
                workspace_root = "/tmp/A3Agent"
            else:
                # 最后的回退：使用exe所在目录
                exe_dir = os.path.dirname(os.path.abspath(sys.executable))
                workspace_root = exe_dir
                emit(f"Fallback: using exe directory as workspace: {workspace_root}")
        else:
            emit(f"Using workspace from environment: {workspace_root}")

        ensure_dir(workspace_root)

        # 确保ga_config目录存在并复制配置文件
        _ensure_runtime_ga_config(base_dir, workspace_root)

        # 设置ga_config为用户数据目录（在workspace_root下）
        user_data_dir = str(workspace_config_dir(workspace_root))

        temp_dir(root=user_data_dir)

        # 初始化TODO.txt文件（如果不存在）
        todo_file = os.path.join(user_data_dir, "temp", "TODO.txt")
        if not os.path.exists(todo_file):
            with open(todo_file, "w", encoding="utf-8") as f:
                f.write("# TODO List\n")
                f.write("# Format: [ ] for incomplete, [x] for complete\n")
                f.write("# Example:\n")
                f.write("# [ ] Task description here\n\n")

        # 初始化autonomous_reports目录和history.txt
        reports_dir = os.path.join(user_data_dir, "temp", "autonomous_reports")
        ensure_dir(reports_dir)
        history_file = os.path.join(reports_dir, "history.txt")
        if not os.path.exists(history_file):
            with open(history_file, "w", encoding="utf-8") as f:
                f.write("# Autonomous Reports History\n")
                f.write("# Format: RXX | YYYY-MM-DD | Type | Topic | Conclusion\n\n")

        os.chdir(workspace_root)

        # 设置环境变量
        os.environ["GA_WORKSPACE_ROOT"] = workspace_root
        os.environ["GA_USER_DATA_DIR"] = user_data_dir

        if workspace_root not in sys.path:
            sys.path.insert(0, workspace_root)
        if base_dir not in sys.path:
            sys.path.insert(1, base_dir)
        emit(f"Frozen runtime base_dir={base_dir} workspace_root={workspace_root} user_data_dir={user_data_dir}")
    else:
        workspace_root = base_dir
        ensure_dir(workspace_root)
        _ensure_runtime_ga_config(base_dir, workspace_root)
        user_data_dir = str(workspace_config_dir(workspace_root))
        os.chdir(workspace_root)
        os.environ["GA_WORKSPACE_ROOT"] = workspace_root
        os.environ["GA_USER_DATA_DIR"] = user_data_dir
        emit(f"Dev runtime base_dir={base_dir} workspace_root={workspace_root} user_data_dir={user_data_dir}")
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
    import signal

    # 设置信号处理器以支持优雅退出
    shutdown_event = threading.Event()

    def signal_handler(signum, frame):
        emit(f"Received signal {signum}, shutting down gracefully...")
        shutdown_event.set()

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    if hasattr(signal, 'SIGBREAK'):  # Windows
        signal.signal(signal.SIGBREAK, signal_handler)

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

    # 主循环：等待shutdown信号
    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1)
    except KeyboardInterrupt:
        pass

    emit("Shutting down...")
    sys.exit(0)
