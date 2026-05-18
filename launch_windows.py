import atexit
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

LOCAL_DEPS_DIR = Path(__file__).resolve().parent / ".pydeps"
if LOCAL_DEPS_DIR.is_dir() and str(LOCAL_DEPS_DIR) not in sys.path:
    sys.path.insert(0, str(LOCAL_DEPS_DIR))

import uvicorn

try:
    import webview
except Exception:
    webview = None

try:
    from path_utils import app_data_dir
except Exception:
    app_data_dir = None

try:
    from path_utils import resource_dir

    BASE_DIR = resource_dir()
except Exception:
    BASE_DIR = Path(__file__).resolve().parent

os.chdir(str(BASE_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

APP_NAME = "A3Agent"
if app_data_dir is not None:
    _default_log_file = Path(app_data_dir()) / "launch-windows.log"
else:
    _default_log_file = BASE_DIR / "launch-windows.log"
LOG_FILE = Path(os.environ.get("GA_LOG_FILE") or str(_default_log_file))
WINDOW_TITLE = APP_NAME


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
        open_browser_fallback()
        return

    window = webview.create_window(
        WINDOW_TITLE,
        URL,
        width=1280,
        height=860,
        text_select=True,
        resizable=True,
    )
    webview.start()
    return window


def main():
    log("launcher: windows entry loaded")
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    if not wait_for_server():
        message = f"Local server failed to start. Check log: {LOG_FILE}"
        log(message)
        raise SystemExit(message)

    create_window()


if __name__ == "__main__":
    main()
