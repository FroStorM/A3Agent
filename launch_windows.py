import atexit
import json
import os
import socket
import site
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


def iter_local_deps_dirs():
    roots = []
    seen = set()
    dep_dirs = []
    dep_seen = set()

    def add_root(path):
        if not path:
            return
        try:
            root = Path(path).resolve()
        except Exception:
            return
        key = str(root)
        if key in seen:
            return
        seen.add(key)
        roots.append(root)

    def add_dep(path):
        if not path:
            return
        try:
            dep_path = Path(path).resolve()
        except Exception:
            return
        key = str(dep_path)
        if key in dep_seen:
            return
        dep_seen.add(key)
        dep_dirs.append(dep_path)

    add_dep(os.environ.get("GA_PYDEPS_DIR"))
    add_root(os.environ.get("GA_BASE_DIR"))
    add_root(Path(__file__).resolve().parent)
    try:
        add_root(Path(sys.executable).resolve().parent)
    except Exception:
        pass
    add_root(os.environ.get("GA_APP_DATA_DIR"))
    if os.name == "nt":
        app_name = os.environ.get("GA_APP_NAME") or "A3Agent"
        add_root(Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")) / app_name)

    for root in roots:
        add_dep(root / ".pydeps")
        add_dep(root / "_internal" / ".pydeps")
    return dep_dirs


def preferred_local_deps_dir():
    for dep_dir in iter_local_deps_dirs():
        try:
            dep_dir.mkdir(parents=True, exist_ok=True)
            return dep_dir
        except Exception:
            continue
    return None


def add_python_path(path):
    try:
        path = Path(path).resolve()
    except Exception:
        return
    try:
        is_dir = path.is_dir()
    except Exception:
        return
    if not is_dir:
        return
    path_str = str(path)
    if path_str in sys.path:
        return
    try:
        site.addsitedir(path_str)
    except Exception:
        sys.path.insert(0, path_str)


def bootstrap_python_paths():
    preferred_dep_dir = preferred_local_deps_dir()
    if preferred_dep_dir is not None:
        os.environ.setdefault("GA_PYDEPS_DIR", str(preferred_dep_dir))
        os.environ.setdefault("PIP_TARGET", str(preferred_dep_dir))
        os.environ.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
        os.environ.setdefault("PIP_NO_WARN_SCRIPT_LOCATION", "1")
    for dep_dir in iter_local_deps_dirs():
        add_python_path(dep_dir)
    try:
        user_sites = site.getusersitepackages()
    except Exception:
        user_sites = []
    if isinstance(user_sites, str):
        user_sites = [user_sites]
    for user_site in user_sites:
        add_python_path(user_site)


def run_child_python_if_requested():
    if os.environ.get("A3AGENT_CHILD_PYTHON") != "1":
        return
    import runpy

    capture_output = os.environ.get("A3AGENT_CHILD_CAPTURE") == "1"
    args = list(sys.argv[1:])
    module = None
    code = None
    script = None
    rest = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-X" and i + 1 < len(args):
            i += 2
            continue
        if arg == "-u":
            i += 1
            continue
        if arg == "-m" and i + 1 < len(args):
            module = args[i + 1]
            rest = args[i + 2:]
            break
        if arg == "-c" and i + 1 < len(args):
            code = args[i + 1]
            rest = args[i + 2:]
            break
        if arg.startswith("-"):
            i += 1
            continue
        script = arg
        rest = args[i + 1:]
        break
    if not any((module, code, script)):
        raise SystemExit("A3AGENT_CHILD_PYTHON requires a script, module, or code string")
    if not capture_output:
        try:
            sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
            sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        if module:
            sys.argv = [module] + rest
            runpy.run_module(module, run_name="__main__", alter_sys=True)
        elif code is not None:
            sys.argv = ["-c"] + rest
            globs = {"__name__": "__main__", "__file__": "<string>"}
            exec(compile(code, "<string>", "exec"), globs, globs)
        else:
            sys.argv = [script] + rest
            runpy.run_path(script, run_name="__main__")
    except Exception:
        try:
            import traceback

            traceback.print_exc()

            fallback_log = Path(os.environ.get("GA_LOG_FILE") or (Path.cwd() / "launch-windows.log"))
            fallback_log.parent.mkdir(parents=True, exist_ok=True)
            with fallback_log.open("a", encoding="utf-8") as f:
                f.write("[child-python-error]\n")
                traceback.print_exc(file=f)
                f.write("\n")
        except Exception:
            pass
        raise SystemExit(1)
    raise SystemExit(0)


bootstrap_python_paths()
run_child_python_if_requested()

LOCAL_DEPS_DIR = next((path for path in iter_local_deps_dirs() if path.is_dir()), None)

import uvicorn

try:
    import webview
except Exception:
    webview = None

try:
    from path_utils import app_data_dir, resource_path
except Exception:
    app_data_dir = None
    resource_path = None

try:
    from path_utils import resource_dir

    BASE_DIR = resource_dir()
except Exception:
    BASE_DIR = Path(__file__).resolve().parent

os.chdir(str(BASE_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

APP_NAME = "A3Agent"
os.environ.setdefault("GA_APP_NAME", APP_NAME)
if app_data_dir is not None:
    _default_log_file = Path(app_data_dir()) / "launch-windows.log"
else:
    _default_log_file = BASE_DIR / "launch-windows.log"
os.environ.setdefault("GA_BASE_DIR", str(BASE_DIR))
if app_data_dir is not None:
    try:
        os.environ.setdefault("GA_APP_DATA_DIR", str(app_data_dir()))
    except Exception:
        pass
LOG_FILE = Path(os.environ.get("GA_LOG_FILE") or str(_default_log_file))
WINDOW_TITLE = APP_NAME
PET_PROCESS_REF = None
LAST_PET_CONFIG = None
PET_MONITOR_STOP = threading.Event()

DESKTOP_PET_DEFAULT_CONFIG = {
    "enabled": True,
    "size": 104,
    "position": "right-bottom",
    "x": None,
    "y": None,
    "skin_name": "legacy-pet",
    "always_on_top": True,
    "show_shadow": False,
    "click_action": "toggle_main",
}


def log(message):
    try:
        print(message)
    except Exception:
        pass
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(str(message) + "\n")
    except Exception:
        pass


def find_free_port(lo=18501, hi=18599):
    for port in range(lo, hi + 1):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            sock.close()
            return port
        except OSError:
            continue
    return lo


PORT = find_free_port()
URL = f"http://127.0.0.1:{PORT}"


def wait_for_server(timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(URL + "/api/status", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


def start_server():
    try:
        from api_server import app

        log(f"server: starting on {URL}")
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="error")
    except Exception as e:
        log(f"server: failed: {e}")


def desktop_pet_config_path():
    try:
        if app_data_dir is not None:
            return Path(app_data_dir()) / "desktop_pet.json"
    except Exception:
        pass
    return Path(os.environ.get("GA_APP_DATA_DIR") or str(BASE_DIR)) / "desktop_pet.json"


def sanitize_desktop_pet_config(data):
    if not isinstance(data, dict):
        data = {}
    cfg = dict(DESKTOP_PET_DEFAULT_CONFIG)
    cfg.update({k: data.get(k) for k in cfg.keys() if k in data})
    cfg["enabled"] = bool(cfg.get("enabled"))
    cfg["always_on_top"] = bool(cfg.get("always_on_top"))
    cfg["show_shadow"] = bool(cfg.get("show_shadow"))
    try:
        cfg["size"] = int(cfg.get("size", DESKTOP_PET_DEFAULT_CONFIG["size"]))
    except Exception:
        cfg["size"] = DESKTOP_PET_DEFAULT_CONFIG["size"]
    cfg["size"] = max(48, min(220, cfg["size"]))
    if cfg.get("position") not in {"right-bottom", "right-top", "left-bottom", "left-top", "center", "custom"}:
        cfg["position"] = DESKTOP_PET_DEFAULT_CONFIG["position"]
    for key in ("x", "y"):
        value = cfg.get(key)
        if value is None or value == "":
            cfg[key] = None
            continue
        try:
            cfg[key] = float(value)
        except Exception:
            cfg[key] = None
    if cfg.get("click_action") not in {"toggle_main", "none"}:
        cfg["click_action"] = DESKTOP_PET_DEFAULT_CONFIG["click_action"]
    cfg["skin_name"] = str(cfg.get("skin_name") or DESKTOP_PET_DEFAULT_CONFIG["skin_name"])
    return cfg


def load_desktop_pet_config():
    try:
        path = desktop_pet_config_path()
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return sanitize_desktop_pet_config(json.load(f))
    except Exception as e:
        log(f"desktop_pet: load config failed: {e}")
    return dict(DESKTOP_PET_DEFAULT_CONFIG)


def desktop_pet_script_path():
    candidates = []
    if resource_path is not None:
        try:
            candidates.append(Path(resource_path("frontends", "desktop_pet_v2.pyw")))
        except Exception:
            pass
        try:
            candidates.append(Path(resource_path("frontends", "desktop_pet.pyw")))
        except Exception:
            pass
    candidates.extend([
        BASE_DIR / "frontends" / "desktop_pet_v2.pyw",
        BASE_DIR / "frontends" / "desktop_pet.pyw",
    ])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def terminate_pet_process():
    global PET_PROCESS_REF
    proc = PET_PROCESS_REF
    PET_PROCESS_REF = None
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception as e:
        log(f"desktop_pet: terminate failed: {e}")


def start_pet_process(cfg):
    global PET_PROCESS_REF
    script = desktop_pet_script_path()
    if script is None:
        log("desktop_pet: script not found")
        return
    cmd = [
        sys.executable,
        "-u",
        str(script),
        "--skin",
        str(cfg.get("skin_name") or "legacy-pet"),
        "--size",
        str(cfg.get("size") or DESKTOP_PET_DEFAULT_CONFIG["size"]),
        "--position",
        str(cfg.get("position") or DESKTOP_PET_DEFAULT_CONFIG["position"]),
        "--always-on-top",
        "1" if cfg.get("always_on_top") else "0",
        "--show-shadow",
        "1" if cfg.get("show_shadow") else "0",
    ]
    if cfg.get("x") is not None:
        cmd.extend(["--x", str(cfg["x"])])
    if cfg.get("y") is not None:
        cmd.extend(["--y", str(cfg["y"])])

    env = os.environ.copy()
    if getattr(sys, "frozen", False) or Path(sys.executable).stem.lower() == "a3agent":
        env["A3AGENT_CHILD_PYTHON"] = "1"
    env["GA_BASE_DIR"] = str(BASE_DIR)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    PET_PROCESS_REF = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        startupinfo=startupinfo,
    )
    log(f"desktop_pet: started pid={PET_PROCESS_REF.pid} cfg={cfg}")


def apply_desktop_pet_config(cfg):
    global LAST_PET_CONFIG
    cfg = sanitize_desktop_pet_config(cfg)
    proc_alive = PET_PROCESS_REF is not None and PET_PROCESS_REF.poll() is None

    if not cfg.get("enabled"):
        if proc_alive:
            terminate_pet_process()
            log("desktop_pet: disabled")
        LAST_PET_CONFIG = dict(cfg)
        return

    restart_keys = ("skin_name", "size", "position", "x", "y", "always_on_top", "show_shadow")
    needs_restart = (
        not proc_alive
        or LAST_PET_CONFIG is None
        or any(cfg.get(k) != LAST_PET_CONFIG.get(k) for k in restart_keys)
    )
    LAST_PET_CONFIG = dict(cfg)
    if not needs_restart:
        return
    if proc_alive:
        terminate_pet_process()
    start_pet_process(cfg)


def desktop_pet_monitor():
    while not PET_MONITOR_STOP.is_set():
        try:
            apply_desktop_pet_config(load_desktop_pet_config())
        except Exception as e:
            log(f"desktop_pet: monitor failed: {e}")
        PET_MONITOR_STOP.wait(1.0)


def open_browser_fallback():
    log(f"launcher: opening system browser {URL}")
    webbrowser.open(URL)
    try:
        if os.name == "nt":
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(
                APP_NAME,
                f"pywebview unavailable, opened in system browser.\n\nURL: {URL}",
            )
            root.destroy()
    except Exception as e:
        log(f"launcher: browser fallback prompt failed: {e}")


def create_window():
    if webview is None:
        try:
            open_browser_fallback()
            return
        finally:
            PET_MONITOR_STOP.set()
            terminate_pet_process()

    window = webview.create_window(
        WINDOW_TITLE,
        URL,
        width=1280,
        height=860,
        text_select=True,
        resizable=True,
    )
    try:
        webview.start()
    finally:
        PET_MONITOR_STOP.set()
        terminate_pet_process()
    return window


def main():
    log("launcher: windows entry loaded")
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    if not wait_for_server():
        message = f"Local server failed to start. Check log: {LOG_FILE}"
        log(message)
        raise SystemExit(message)

    pet_thread = threading.Thread(target=desktop_pet_monitor, daemon=True)
    pet_thread.start()
    atexit.register(terminate_pet_process)

    create_window()


if __name__ == "__main__":
    main()
