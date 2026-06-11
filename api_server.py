import os
import sys
import threading
import json
import time
import asyncio
import queue
import traceback
import shutil
import subprocess
import base64
import mimetypes
import socket
import signal
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import importlib
import importlib.util
import re
import uuid
from difflib import SequenceMatcher
from path_utils import (
    app_data_dir,
    config_dir_name,
    ensure_dir,
    app_root_dir,
    normalize_workspace_root,
    resolve_mykey_path,
    resource_dir,
    resource_path,
    workspace_config_dir,
    workspace_history_path,
    workspace_root_dir,
)

BASE_DIR = str(resource_dir())
sys.path.append(BASE_DIR)

def resolve_frontend_dir():
    env_dir = os.environ.get("GA_FRONTEND_DIR")
    if env_dir and os.path.exists(os.path.join(env_dir, "index.html")):
        return os.path.normpath(env_dir)

    candidates = [
        os.path.join(BASE_DIR, "frontend"),
        os.path.join(BASE_DIR, "..", "frontend"),
        os.path.join(BASE_DIR, "..", "..", "frontend"),
        os.path.join(BASE_DIR, "..", "..", "..", "frontend"),
    ]
    exe_path = os.path.abspath(sys.executable)
    candidates.append(os.path.join(os.path.dirname(exe_path), "..", "Resources", "frontend"))

    # For bundled/portable mode: check if frontend is in the same directory as exe
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(exe_path)
        candidates.insert(0, os.path.join(exe_dir, "frontend"))

    for path in candidates:
        p = os.path.normpath(os.path.abspath(path))
        if os.path.exists(os.path.join(p, "index.html")):
            return p
    return None

app = FastAPI()
API_LOG = "/tmp/a3agent-api.log"
STREAM_DEBUG_LOG = "/tmp/a3agent-stream-debug.log"


def _debug_log(kind, **fields):
    try:
        payload = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind,
        }
        for key, value in fields.items():
            if value is None:
                continue
            payload[key] = value
        line = json.dumps(payload, ensure_ascii=False, default=str)
        print(f"[StreamDebug] {line}")
        with open(STREAM_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def _token_usage_payload():
    try:
        from frontends import cost_tracker
    except Exception:
        return {"available": False}
    try:
        trackers = cost_tracker.all_trackers()
        total = cost_tracker.TokenStats()
        started_values = []
        for item in trackers.values():
            total.requests += int(getattr(item, "requests", 0) or 0)
            total.input += int(getattr(item, "input", 0) or 0)
            total.output += int(getattr(item, "output", 0) or 0)
            total.cache_create += int(getattr(item, "cache_create", 0) or 0)
            total.cache_read += int(getattr(item, "cache_read", 0) or 0)
            total.last_input = max(total.last_input, int(getattr(item, "last_input", 0) or 0))
            total.last_output = max(total.last_output, int(getattr(item, "last_output", 0) or 0))
            started = float(getattr(item, "started_at", 0) or 0)
            if started > 0:
                started_values.append(started)
        if started_values:
            total.started_at = min(started_values)
        backend = getattr(getattr(getattr(state, "agent", None), "llmclient", None), "backend", None)
        context_chars = cost_tracker.current_input_chars(backend) if backend else 0
        context_limit_chars = cost_tracker.context_window_chars(backend) if backend else 0
        return {
            "available": True,
            "threads": len(trackers),
            "requests": total.requests,
            "input": total.input,
            "output": total.output,
            "cache_create": total.cache_create,
            "cache_read": total.cache_read,
            "total": total.total_tokens(),
            "last_input": total.last_input,
            "last_output": total.last_output,
            "cache_hit_rate": round(total.cache_hit_rate(), 1),
            "elapsed_seconds": round(total.elapsed_seconds(), 1),
            "context_chars": context_chars,
            "context_limit_chars": context_limit_chars,
        }
    except Exception as e:
        return {"available": False, "error": str(e)}

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


def _resolve_ga_config_target(base):
    base = os.path.abspath(base)
    if os.path.basename(base) == config_dir_name():
        return base
    return os.path.join(base, config_dir_name())


def _find_bundled_mykey_sources():
    source_root = _find_ga_config_src_root()
    if not source_root:
        return []
    sources = []
    for name in ("mykey.json", "mykey.py"):
        src = os.path.join(source_root, name)
        if os.path.isfile(src):
            sources.append(src)
    return sources


def _ensure_default_mykey(base):
    try:
        target_root = _resolve_ga_config_target(base)
        bundled_sources = _find_bundled_mykey_sources()
        if not bundled_sources:
            return
        os.makedirs(target_root, exist_ok=True)
        for src in bundled_sources:
            dst = os.path.join(target_root, os.path.basename(src))
            # 只在目标文件不存在或为空时复制，绝不覆盖用户已写入的文件
            if not os.path.isfile(dst) or os.path.getsize(dst) <= 0:
                shutil.copy2(src, dst)
        resolve_mykey_path(target_root, prefer_existing=True)
    except Exception:
        return


def _migrate_legacy_ga_config(target_root):
    legacy_root = os.path.join(target_root, config_dir_name())
    if not os.path.isdir(legacy_root):
        return
    memory_src = os.path.join(legacy_root, "memory")
    if os.path.isdir(memory_src):
        _copy_tree_defaults(memory_src, os.path.join(target_root, "memory"), overwrite_if_source_newer=True)
    for name in ("mykey.json", "mykey.py"):
        src = os.path.join(legacy_root, name)
        dst = os.path.join(target_root, name)
        if os.path.isfile(src) and _should_copy_file(src, dst, overwrite_if_source_newer=True):
            shutil.copy2(src, dst)
    shutil.rmtree(legacy_root, ignore_errors=True)

@app.middleware("http")
async def add_frontend_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    try:
        p = request.url.path or ""
        if p == "/" or p.endswith(".html") or p.endswith(".js") or p.endswith(".css"):
            response.headers["Cache-Control"] = "no-store"
    except Exception:
        pass
    return response

def _default_app_root_dir():
    app_name = os.environ.get("GA_APP_NAME") or "A3Agent"
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        root = os.path.join(home, "Library", "Application Support", app_name)
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        root = os.path.join(base, app_name)
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
        root = os.path.join(base, app_name)
    os.makedirs(root, exist_ok=True)
    return root

def _default_workspace_dir():
    root = os.environ.get("GA_APP_DATA_DIR") or _default_app_root_dir()
    os.environ.setdefault("GA_APP_DATA_DIR", root)
    ws = os.path.join(root, "workspace")
    os.makedirs(ws, exist_ok=True)
    return ws

def _config_dir_name():
    name = os.environ.get("GA_CONFIG_DIRNAME")
    if isinstance(name, str) and name:
        return name
    return "ga_config"

def _try_mkdir(path):
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False

def _normalize_workspace_root(path):
    if not isinstance(path, str) or not path:
        return None
    root = os.path.abspath(path)
    cfg_name = _config_dir_name()
    if os.path.basename(root) == cfg_name:
        root = os.path.dirname(root)
    return root

def _workspace_config_dir(root):
    root = _normalize_workspace_root(root)
    if not root:
        root = _default_workspace_dir()
    cfg = os.path.join(root, _config_dir_name())
    os.makedirs(cfg, exist_ok=True)
    return cfg


def get_workspace_root_dir():
    if hasattr(app, "current_workspace") and app.current_workspace:
        root = normalize_workspace_root(app.current_workspace)
        if root is not None:
            root = ensure_dir(root)
            os.environ.setdefault("GA_WORKSPACE_ROOT", str(root))
            return str(root)

    root = normalize_workspace_root(os.environ.get("GA_WORKSPACE_ROOT"))
    if root is not None:
        root = ensure_dir(root)
        return str(root)

    root = normalize_workspace_root(os.environ.get("GA_USER_DATA_DIR"))
    if root is not None:
        root = ensure_dir(root)
        os.environ.setdefault("GA_WORKSPACE_ROOT", str(root))
        return str(root)

    root = workspace_root_dir()
    os.environ.setdefault("GA_WORKSPACE_ROOT", str(root))
    return str(root)


def get_user_data_dir():
    root = get_workspace_root_dir()
    cfg = workspace_config_dir(root)
    os.environ["GA_WORKSPACE_ROOT"] = root
    os.environ["GA_USER_DATA_DIR"] = str(cfg)
    return str(cfg)


goal_process = {"proc": None, "state_path": "", "started_at": 0}
hive_process = {"bbs": None, "master": None, "workers": [], "state_path": "", "started_at": 0}


def _goal_dir():
    path = os.path.join(get_user_data_dir(), "goals")
    os.makedirs(path, exist_ok=True)
    return path


def _goal_state_path():
    return os.path.join(_goal_dir(), "goal_state.json")


def _goal_log_path():
    return os.path.join(_goal_dir(), "goal_mode.log")


def _hive_dir():
    path = os.path.join(get_user_data_dir(), "hive")
    os.makedirs(path, exist_ok=True)
    return path


def _hive_state_path():
    return os.path.join(_hive_dir(), "hive_state.json")


def _hive_log_path(name):
    return os.path.join(_hive_dir(), f"{name}.log")


def _read_goal_state():
    path = _goal_state_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _goal_proc_alive():
    proc = goal_process.get("proc")
    return bool(proc is not None and proc.poll() is None)


def _goal_payload():
    data = _read_goal_state() or {}
    budget = float(data.get("budget_seconds") or 0)
    start = float(data.get("start_time") or 0)
    elapsed = max(0, time.time() - start) if start else 0
    remaining = max(0, budget - elapsed) if budget else 0
    return {
        "state_path": _goal_state_path(),
        "log_path": _goal_log_path(),
        "state": data,
        "running": _goal_proc_alive() and data.get("status") in ("running", "wrapping_up"),
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "pid": getattr(goal_process.get("proc"), "pid", None) if _goal_proc_alive() else None,
    }


def _stop_goal_process(mark_status="stopped"):
    proc = goal_process.get("proc")
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    data = _read_goal_state()
    if data:
        data["status"] = mark_status
        data["end_time"] = time.time()
        with open(_goal_state_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def _start_goal_reflect_process(state_doc, state_path, log_path, cwd=None, extra_env=None):
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state_doc, f, ensure_ascii=False, indent=2)
    env = os.environ.copy()
    env["GOAL_STATE"] = state_path
    env["GA_WORKSPACE_ROOT"] = get_workspace_root_dir()
    env["GA_USER_DATA_DIR"] = get_user_data_dir()
    if extra_env:
        env.update({str(k): str(v) for k, v in extra_env.items()})
    log_f = open(log_path, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "agentmain.py"), "--reflect", os.path.join(BASE_DIR, "reflect", "goal_mode.py")],
            cwd=cwd or BASE_DIR,
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return proc
    except Exception:
        try:
            log_f.close()
        except Exception:
            pass
        raise


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _proc_alive(proc):
    return bool(proc is not None and proc.poll() is None)


def _read_json_file(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _hive_payload():
    data = _read_json_file(_hive_state_path()) or {}
    master_state = _read_json_file(data.get("master_goal_state_path") or os.path.join(_hive_dir(), "master_goal_state.json")) or {}
    workers = hive_process.get("workers") or []
    bbs_alive = _proc_alive(hive_process.get("bbs"))
    master_alive = _proc_alive(hive_process.get("master"))
    worker_pids = [p.pid for p in workers if _proc_alive(p)]
    worker_alive = bool(worker_pids)
    master_status = master_state.get("status") or ("running" if master_alive else "")
    budget_seconds = float(master_state.get("budget_seconds") or (float(data.get("budget_minutes") or 0) * 60) or 0)
    start_time = float(master_state.get("start_time") or 0)
    elapsed_seconds = max(0.0, time.time() - start_time) if start_time else 0.0
    remaining_seconds = max(0.0, budget_seconds - elapsed_seconds) if budget_seconds else None
    turns_used = int(master_state.get("turns_used") or 0)
    max_turns = int(master_state.get("max_turns") or data.get("max_turns") or 0)
    turns_remaining = max(0, max_turns - turns_used) if max_turns else None
    state_status = data.get("status") or ""
    effective_status = state_status
    if master_status in ("done_budget", "done", "stopped", "error") and not master_alive:
        effective_status = master_status
    elif worker_alive:
        effective_status = "workers_running"
    elif bbs_alive and state_status == "running" and master_status:
        effective_status = f"bbs_only_{master_status}"
    if data and effective_status != state_status and not worker_alive and not master_alive:
        data["status"] = effective_status
        if master_state.get("end_time") and not data.get("end_time"):
            data["end_time"] = master_state.get("end_time")
        _write_hive_state(data)
    output_dir = data.get("output_dir") or os.path.join(data.get("hive_root") or _hive_dir(), "outputs")
    recent_outputs = []
    try:
        if output_dir and os.path.isdir(output_dir):
            paths = []
            for root, _dirs, files in os.walk(output_dir):
                for name in files:
                    if name.startswith("."):
                        continue
                    path = os.path.join(root, name)
                    paths.append(path)
            paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            recent_outputs = [
                {
                    "path": path,
                    "name": os.path.basename(path),
                    "mtime": os.path.getmtime(path),
                    "size": os.path.getsize(path),
                }
                for path in paths[:20]
            ]
    except Exception:
        recent_outputs = []
    return {
        "state_path": _hive_state_path(),
        "state": data,
        "master_state": master_state,
        "effective_status": effective_status,
        "running": bbs_alive or master_alive or worker_alive,
        "active_coordination": master_alive or worker_alive,
        "bbs_running": bbs_alive,
        "master_running": master_alive,
        "master_status": master_status,
        "budget_seconds": budget_seconds,
        "elapsed_seconds": elapsed_seconds,
        "remaining_seconds": remaining_seconds,
        "turns_used": turns_used,
        "max_turns": max_turns,
        "turns_remaining": turns_remaining,
        "paused_targets": data.get("paused_targets") or [],
        "worker_pids": worker_pids,
        "bbs_pid": hive_process.get("bbs").pid if bbs_alive else None,
        "master_pid": hive_process.get("master").pid if master_alive else None,
        "output_dir": output_dir,
        "recent_outputs": recent_outputs,
    }


def _write_hive_state(data):
    with open(_hive_state_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _terminate_proc(proc):
    if not _proc_alive(proc):
        return
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _stop_hive_processes(mark_status="stopped"):
    data = _read_json_file(_hive_state_path()) or {}
    if data and mark_status == "stopped":
        try:
            token = data.get("seed_token")
            base_url = data.get("base_url")
            board_key = data.get("board_key")
            if token and base_url and board_key:
                _hive_http_json(
                    f"{base_url}/post",
                    {"token": token, "content": "Hive 已由用户停止。master 和 worker 不应继续接新任务，除非用户明确重新启动。"},
                    board_key,
                )
        except Exception:
            pass
    _terminate_proc(hive_process.get("master"))
    for proc in list(hive_process.get("workers") or []):
        _terminate_proc(proc)
    _terminate_proc(hive_process.get("bbs"))
    if data:
        data["status"] = mark_status
        data["end_time"] = time.time()
        _write_hive_state(data)


def _unique_paths(paths):
    out = []
    seen = set()
    for path in paths:
        if not path:
            continue
        try:
            ap = os.path.abspath(path)
        except Exception:
            continue
        if ap not in seen:
            seen.add(ap)
            out.append(ap)
    return out


def _todo_paths():
    root = os.path.abspath(BASE_DIR)
    canonical = os.path.join(root, "temp", "TODO.txt")
    legacy_candidates = [
        os.path.join(get_user_data_dir(), "ToDo.txt"),
        os.path.join(get_user_data_dir(), "TODO.txt"),
        os.path.join(get_workspace_root_dir(), "ToDo.txt"),
        os.path.join(get_workspace_root_dir(), "TODO.txt"),
        os.path.join(root, "ToDo.txt"),
        os.path.join(root, "TODO.txt"),
    ]
    legacy = [p for p in _unique_paths(legacy_candidates) if os.path.abspath(p) != os.path.abspath(canonical)]
    return canonical, legacy


def _ensure_todo_file():
    canonical, legacy_paths = _todo_paths()
    if os.path.isfile(canonical):
        return canonical, None

    for legacy in legacy_paths:
        if not os.path.isfile(legacy):
            continue
        try:
            content = _read_text(legacy)
        except Exception:
            continue
        if content:
            _write_text(canonical, content)
            return canonical, legacy

    return canonical, None


def _get_app_data_dir():
    return str(app_data_dir())


def _workspace_history_path():
    return str(workspace_history_path())

def _upload_image_dir():
    path = os.path.join(_get_app_data_dir(), "uploads", "images")
    os.makedirs(path, exist_ok=True)
    return path


def _safe_upload_image_path(filename):
    name = os.path.basename(str(filename or ""))
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    if not name:
        name = "image.png"
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        ext = ".png"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(_upload_image_dir(), f"{stamp}-{uuid.uuid4().hex[:8]}-{stem[:40] or 'image'}{ext}")


def _decode_image_data_url(data_url, fallback_mime="image/png"):
    raw = str(data_url or "")
    mime = fallback_mime
    payload = raw
    if raw.startswith("data:"):
        header, _, payload = raw.partition(",")
        m = re.match(r"data:([^;,]+)", header)
        if m:
            mime = m.group(1)
        if ";base64" not in header:
            return None, mime
    try:
        return base64.b64decode(payload, validate=False), mime
    except Exception:
        return None, mime

def _read_workspace_history():
    path = _workspace_history_path()
    try:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            out = []
            for x in data:
                if isinstance(x, str) and x and os.path.isdir(x):
                    out.append(x)
            return out
    except Exception:
        return []
    return []

def _write_workspace_history(items):
    path = _workspace_history_path()
    _create_user_backup_safe("before-workspace-history")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

def _add_workspace_history(path):
    if not path or not os.path.isdir(path):
        return
    path = os.path.abspath(path)
    items = _read_workspace_history()
    items = [x for x in items if x != path]
    items.insert(0, path)
    items = items[:30]
    _write_workspace_history(items)

def _find_sop_src_root():
    candidates = []
    env_dir = os.environ.get("GA_SOP_SRC_DIR")
    if isinstance(env_dir, str) and env_dir:
        candidates.append(env_dir)
    candidates.extend([
        os.path.join(BASE_DIR, "memory"),
    ])
    try:
        candidates.append(str(resource_path("memory")))
    except Exception:
        pass

    for p in candidates:
        try:
            ap = os.path.abspath(p)
            if not os.path.isdir(ap):
                continue
            for root, dirs, files in os.walk(ap):
                dirs[:] = [d for d in dirs if isinstance(d, str) and d not in ("__pycache__",) and not d.startswith(".")]
                for f in files:
                    if isinstance(f, str) and not f.startswith(".") and not f.endswith(".pyc"):
                        return ap
        except Exception:
            continue
    return None


def _bundled_memory_src_root():
    candidates = [
        os.path.join(BASE_DIR, "memory"),
    ]
    try:
        candidates.append(str(resource_path("memory")))
    except Exception:
        pass

    seen = set()
    for p in candidates:
        try:
            ap = os.path.abspath(p)
        except Exception:
            continue
        if ap in seen:
            continue
        seen.add(ap)
        if os.path.isdir(ap):
            return ap
    return None


def _user_memory_dir():
    base = get_user_data_dir()
    mem_dir = os.path.join(base, "memory")
    os.makedirs(mem_dir, exist_ok=True)
    return os.path.abspath(mem_dir)


def _incoming_defaults_memory_dir():
    base = get_user_data_dir()
    mem_dir = os.path.join(base, "_incoming_defaults", "memory")
    os.makedirs(mem_dir, exist_ok=True)
    return os.path.abspath(mem_dir)


def _files_differ(path_a, path_b):
    try:
        if not os.path.isfile(path_a) or not os.path.isfile(path_b):
            return True
        if os.path.getsize(path_a) != os.path.getsize(path_b):
            return True
        with open(path_a, "rb") as fa, open(path_b, "rb") as fb:
            while True:
                a = fa.read(1024 * 1024)
                b = fb.read(1024 * 1024)
                if a != b:
                    return True
                if not a:
                    return False
    except Exception:
        return True


def _source_is_newer(src, dst):
    try:
        return os.path.getmtime(src) > os.path.getmtime(dst)
    except Exception:
        return True


def _ensure_default_user_memory():
    source_root = _bundled_memory_src_root()
    if not source_root:
        return
    user_root = _user_memory_dir()
    incoming_root = _incoming_defaults_memory_dir()
    for cur_root, filename in _iter_copyable_files(source_root):
        rel_dir = os.path.relpath(cur_root, source_root)
        rel_path = filename if rel_dir == "." else os.path.join(rel_dir, filename)
        src = os.path.join(cur_root, filename)
        dst = os.path.join(user_root, rel_path)
        if not os.path.exists(dst) or os.path.getsize(dst) <= 0:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            continue
        if _files_differ(src, dst) and _source_is_newer(src, dst):
            incoming = os.path.join(incoming_root, rel_path)
            os.makedirs(os.path.dirname(incoming), exist_ok=True)
            shutil.copy2(src, incoming)

def _iter_copyable_files(root):
    root = os.path.abspath(root)
    for cur_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if isinstance(d, str) and d not in ("__pycache__",) and not d.startswith(".")]
        for f in files:
            if not isinstance(f, str) or f.startswith(".") or f.endswith(".pyc"):
                continue
            yield cur_root, f

def _copy_tree_defaults(source_root, dest_root, overwrite_if_source_newer=False):
    if not source_root or not dest_root:
        return
    source_root = os.path.abspath(source_root)
    dest_root = os.path.abspath(dest_root)
    if source_root == dest_root or not os.path.isdir(source_root):
        return
    os.makedirs(dest_root, exist_ok=True)
    for cur_root, filename in _iter_copyable_files(source_root):
        rel = os.path.relpath(cur_root, source_root)
        target_dir = dest_root if rel == "." else os.path.join(dest_root, rel)
        os.makedirs(target_dir, exist_ok=True)
        src = os.path.join(cur_root, filename)
        dst = os.path.join(target_dir, filename)
        if not _should_copy_file(src, dst, overwrite_if_source_newer=overwrite_if_source_newer):
            continue
        shutil.copy2(src, dst)


def _backup_root_dir():
    return os.path.join(_get_app_data_dir(), "backups")


def _backup_ignore(_dir, names):
    ignored = {"__pycache__", ".DS_Store"}
    return {name for name in names if name in ignored or str(name).endswith(".pyc")}


def _backup_safe_label(label):
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(label or "manual")).strip("._")
    return label[:40] or "manual"


def _copy_to_backup(src, dst):
    if not src or not os.path.exists(src):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst, ignore=_backup_ignore, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    return True


def _collect_user_state_paths():
    app_root = os.path.abspath(_get_app_data_dir())
    workspace_root = os.path.abspath(get_workspace_root_dir())
    active_cfg = os.path.abspath(get_user_data_dir())
    candidates = [
        active_cfg,
        os.path.join(app_root, config_dir_name()),
        os.path.join(app_root, "memory"),
        os.path.join(app_root, "workspace", config_dir_name()),
        os.path.join(app_root, "workspace", "memory"),
        os.path.join(app_root, "workspace", "mykey.py"),
        os.path.join(app_root, "workspace", "mykey.json"),
        os.path.join(app_root, "desktop_pet.json"),
        os.path.join(app_root, "workspace_history.json"),
    ]
    if workspace_root and workspace_root != app_root:
        candidates.extend([
            os.path.join(workspace_root, config_dir_name()),
            os.path.join(workspace_root, "memory"),
            os.path.join(workspace_root, "mykey.py"),
            os.path.join(workspace_root, "mykey.json"),
        ])

    result = []
    seen = set()
    backup_root = os.path.abspath(_backup_root_dir())
    for src in candidates:
        try:
            src = os.path.abspath(src)
        except Exception:
            continue
        if src in seen or not os.path.exists(src):
            continue
        if src == backup_root or src.startswith(backup_root + os.sep):
            continue
        seen.add(src)
        try:
            if src == active_cfg:
                rel = "active_ga_config"
            elif src.startswith(app_root + os.sep):
                rel = os.path.relpath(src, app_root)
            else:
                rel = os.path.join("external", re.sub(r"[^A-Za-z0-9_.-]+", "_", src).strip("_"))
        except Exception:
            rel = os.path.basename(src)
        result.append((src, rel))
    return result


def _prune_backups(keep=30):
    root = _backup_root_dir()
    try:
        if not os.path.isdir(root):
            return
        entries = []
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if os.path.isdir(path):
                entries.append((os.path.getmtime(path), path))
        entries.sort(reverse=True)
        for _mtime, path in entries[keep:]:
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def _create_user_backup(reason="manual"):
    root = _backup_root_dir()
    os.makedirs(root, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = _backup_safe_label(reason)
    backup_dir = os.path.join(root, f"{stamp}-{label}")
    counter = 1
    while os.path.exists(backup_dir):
        counter += 1
        backup_dir = os.path.join(root, f"{stamp}-{label}-{counter}")

    copied = []
    errors = []
    os.makedirs(backup_dir, exist_ok=True)
    for src, rel in _collect_user_state_paths():
        try:
            dst = os.path.join(backup_dir, rel)
            if _copy_to_backup(src, dst):
                copied.append({"source": src, "path": rel})
        except Exception as e:
            errors.append({"source": src, "error": str(e)})

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "reason": reason,
        "backup_dir": backup_dir,
        "app_data_dir": _get_app_data_dir(),
        "workspace_root": get_workspace_root_dir(),
        "user_data_dir": get_user_data_dir(),
        "copied": copied,
        "errors": errors,
    }
    with open(os.path.join(backup_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    _prune_backups()
    return manifest


def _create_user_backup_safe(reason="auto"):
    try:
        return _create_user_backup(reason)
    except Exception as e:
        _debug_log("backup_failed", reason=reason, error=str(e))
        return None


def _list_user_backups():
    root = _backup_root_dir()
    items = []
    if not os.path.isdir(root):
        return {"root": root, "items": items}
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        manifest_path = os.path.join(path, "manifest.json")
        manifest = {}
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            pass
        try:
            size = 0
            for cur_root, _dirs, files in os.walk(path):
                for filename in files:
                    try:
                        size += os.path.getsize(os.path.join(cur_root, filename))
                    except Exception:
                        pass
        except Exception:
            size = 0
        items.append({
            "name": name,
            "path": path,
            "created_at": manifest.get("created_at") or datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds"),
            "reason": manifest.get("reason") or "",
            "files": len(manifest.get("copied") or []),
            "size": size,
        })
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"root": root, "items": items}

def _find_ga_config_src_root():
    candidates = []
    env_dir = os.environ.get("GA_CONFIG_SRC_DIR")
    if isinstance(env_dir, str) and env_dir:
        candidates.append(env_dir)
    candidates.extend([
        os.path.join(BASE_DIR, "ga_config"),
        os.path.join(BASE_DIR, "..", "ga_config"),
        os.path.join(BASE_DIR, "..", "..", "ga_config"),
    ])
    try:
        candidates.append(str(resource_path("ga_config")))
    except Exception:
        pass

    seen = set()
    for p in candidates:
        try:
            ap = os.path.abspath(p)
        except Exception:
            continue
        if ap in seen:
            continue
        seen.add(ap)
        if os.path.isdir(ap) and os.path.isdir(os.path.join(ap, "memory")):
            return ap
    return None

def _ensure_default_ga_config(base):
    source_root = _find_ga_config_src_root()
    if source_root:
        target = _resolve_ga_config_target(base)
        _migrate_legacy_ga_config(target)
        _copy_tree_defaults(source_root, target)
    _ensure_default_user_memory()

def _ensure_default_sops(base):
    try:
        _ensure_default_ga_config(base)
    except Exception:
        return

def _sop_memory_dir():
    _ensure_default_user_memory()
    return _user_memory_dir()

try:
    _base = get_user_data_dir()
    _create_user_backup_safe("startup-before-defaults")
    _ensure_default_ga_config(_base)
    _ensure_default_mykey(_base)
except Exception:
    pass


@app.on_event("startup")
async def _log_startup():
    try:
        _create_user_backup_safe("startup")
        _ensure_default_ga_config(_base)
        _ensure_default_mykey(_base)
    except Exception:
        pass
    try:
        _workspace_root = get_workspace_root_dir()
        _app_root = str(app_root_dir())
        print(
            "[Startup] resolved data dir="
            f"{_base} workspace_root={_workspace_root} app_root={_app_root}"
        )
        _debug_log(
            "startup_data_dir",
            resolved_data_dir=_base,
            workspace_root=_workspace_root,
            app_root=_app_root,
            config_dir=config_dir_name(),
        )
    except Exception:
        pass
    _debug_log(
        "startup",
        base_dir=BASE_DIR,
        frontend_dir=resolve_frontend_dir(),
        pid=os.getpid(),
    )

@app.post("/api/workspace/set")
async def set_workspace(request: Request):
    # Workspace 切换功能已禁用
    return JSONResponse(
        status_code=403,
        content={"error": "Workspace switching is disabled. Configuration is always stored alongside the executable."}
    )

@app.get("/api/workspace/get")
def get_workspace():
    root = get_workspace_root_dir()
    base = get_user_data_dir()
    _ensure_default_ga_config(base)
    _ensure_default_mykey(base)
    return {"workspace": root}

@app.get("/api/workspace/options")
def get_workspace_options():
    current = get_workspace_root_dir()
    history = _read_workspace_history()

    options = []
    if isinstance(current, str) and current and os.path.isdir(current):
        options.append(os.path.abspath(current))

    for p in history:
        if p not in options and os.path.isdir(p):
            options.append(os.path.abspath(p))

    app_data_dir = _get_app_data_dir()
    if app_data_dir and os.path.isdir(app_data_dir):
        p = os.path.abspath(app_data_dir)
        if p not in options:
            options.append(p)

    try:
        home = os.path.expanduser("~")
        candidates = [
            home,
            os.path.join(home, "Documents"),
            os.path.join(home, "Desktop"),
        ]
        for p in candidates:
            if p and os.path.isdir(p):
                ap = os.path.abspath(p)
                if ap not in options:
                    options.append(ap)

        docs = os.path.join(home, "Documents")
        if os.path.isdir(docs):
            picked = []
            for name in os.listdir(docs):
                if len(picked) >= 20:
                    break
                fp = os.path.join(docs, name)
                if not os.path.isdir(fp):
                    continue
                low = name.lower()
                cfg = os.path.join(fp, config_dir_name())
                if (
                    "ga" in low
                    or os.path.exists(os.path.join(fp, "mykey.json"))
                    or os.path.exists(os.path.join(fp, "mykey.py"))
                    or os.path.isdir(os.path.join(fp, "memory"))
                    or os.path.exists(os.path.join(cfg, "mykey.json"))
                    or os.path.exists(os.path.join(cfg, "mykey.py"))
                    or os.path.isdir(os.path.join(cfg, "memory"))
                ):
                    picked.append(os.path.abspath(fp))
            for p in picked:
                if p not in options:
                    options.append(p)
    except Exception:
        pass

    return {"current": current, "options": options}


@app.get("/api/backups")
def list_backups():
    return _list_user_backups()


@app.post("/api/backups/create")
async def create_backup(request: Request):
    reason = "manual"
    try:
        data = await request.json()
        if isinstance(data, dict) and isinstance(data.get("reason"), str) and data.get("reason").strip():
            reason = data.get("reason").strip()
    except Exception:
        pass
    manifest = _create_user_backup(reason)
    return {"status": "created", "backup": manifest, "list": _list_user_backups()}

def _safe_name(name: str):
    if not isinstance(name, str) or not name:
        return None
    if "/" in name or "\\" in name or name.startswith(".") or ".." in name:
        return None
    return name

def _safe_rel_path(path: str):
    if not isinstance(path, str) or not path:
        return None
    if "\x00" in path:
        return None
    if "\\" in path:
        return None
    if path.startswith("/") or path.startswith("."):
        return None
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    for p in parts:
        if p in (".", "..") or p.startswith("."):
            return None
        if not _safe_name(p):
            return None
    return "/".join(parts)

def _looks_like_human_request(text):
    s = str(text or "")
    if not s:
        return False
    patterns = [
        r"Waiting for your answer",
        r"请选择",
        r"请提供输入",
        r"请回复",
        r"需要用户",
        r"HUMAN_INTERVENTION",
        r"INTERRUPT",
    ]
    return any(re.search(p, s, re.IGNORECASE) for p in patterns)

def _read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def _write_text(path, content):
    try:
        ap = os.path.abspath(path)
        backup_root = os.path.abspath(_backup_root_dir())
        existing = _read_text(ap) if os.path.isfile(ap) else None
        if not ap.startswith(backup_root + os.sep) and existing != content:
            _create_user_backup_safe("before-write")
    except Exception:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def _find_history_archive_path():
    candidates = [
        os.path.join(BASE_DIR, "memory", "chat_history.json"),
        os.path.join(BASE_DIR, "..", "memory", "chat_history.json"),
        os.path.join(BASE_DIR, "..", "..", "memory", "chat_history.json"),
        os.path.join(get_user_data_dir(), "memory", "chat_history.json"),
    ]
    try:
        candidates.append(str(resource_path("memory", "chat_history.json")))
    except Exception:
        pass
    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    return ""

def _read_json_text(path):
    try:
        raw = _read_text(path)
    except Exception:
        return None, ""
    try:
        return json.loads(raw), raw
    except Exception:
        return None, raw

def _history_item_to_text(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        role = str(item.get("role") or item.get("speaker") or item.get("name") or "item")
        content = item.get("content")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if isinstance(block.get("text"), str):
                        parts.append(block["text"])
                    elif isinstance(block.get("content"), str):
                        parts.append(block["content"])
                elif isinstance(block, str):
                    parts.append(block)
            content = "\n".join([p for p in parts if p])
        elif isinstance(content, dict):
            try:
                content = json.dumps(content, ensure_ascii=False, indent=2)
            except Exception:
                content = str(content)
        elif content is None:
            content = ""
        else:
            content = str(content)
        prefix = f"[{role}]"
        ts = item.get("timestamp") or item.get("time") or item.get("created_at")
        if ts:
            prefix += f" {ts}"
        return f"{prefix}\n{content}".strip()
    try:
        return json.dumps(item, ensure_ascii=False, indent=2)
    except Exception:
        return str(item)


def _conversation_root_dir():
    path = os.path.join(_get_app_data_dir(), "conversations")
    os.makedirs(path, exist_ok=True)
    return path


def _current_conversation_path():
    return os.path.join(_conversation_root_dir(), "current_session.json")


def _archived_conversation_dir():
    path = os.path.join(_conversation_root_dir(), "sessions")
    os.makedirs(path, exist_ok=True)
    return path


def _live_conversation_dir():
    path = os.path.join(_conversation_root_dir(), "live_sessions")
    os.makedirs(path, exist_ok=True)
    return path


def _new_conversation_doc():
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "session_id": uuid.uuid4().hex,
        "created_at": now,
        "updated_at": now,
        "title": "新对话",
        "summary": "",
        "messages": [],
    }


def _message_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(x for x in parts if x)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("content") or "")
    return str(value or "")


def _compact_text(text, limit=220):
    text = re.sub(r"\s+", " ", _message_text(text)).strip()
    text = re.sub(r"<thinking>.*?</thinking>", " ", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<tool_use>.*?</tool_use>", " ", text, flags=re.DOTALL | re.I)
    text = re.sub(r"`````.*?`````|````.*?````|```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"\*\*LLM Running.*?\*\*", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _message_preview(msg, limit=220):
    content = _message_text(msg.get("content") if isinstance(msg, dict) else msg)
    if isinstance(msg, dict) and msg.get("role") == "assistant":
        summaries = re.findall(r"<summary>(.*?)</summary>", content, flags=re.DOTALL | re.I)
        if summaries:
            return _compact_text(summaries[-1], limit)
    return _compact_text(content, limit)


def _conversation_markdown(data):
    data = _normalize_conversation_doc(data)
    lines = [
        f"# {data.get('title') or 'A3Agent Session'}",
        "",
        f"- Session: {data.get('session_id') or ''}",
        f"- Created: {data.get('created_at') or ''}",
        f"- Updated: {data.get('updated_at') or ''}",
        "",
    ]
    summary = data.get("summary") or ""
    if summary:
        lines.extend(["## Summary", "", summary, ""])
    lines.extend(["## Messages", ""])
    for msg in data.get("messages") or []:
        role = str(msg.get("role") or "entry")
        stamp = str(msg.get("created_at") or msg.get("timestamp") or "")
        content = _message_text(msg.get("content"))
        lines.append(f"### {role}" + (f" · {stamp}" if stamp else ""))
        lines.append("")
        lines.append(content or "")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_MODE_BOILERPLATE_PREFIXES = (
    "@plan 请进入计划模式：先把目标拆成可执行步骤，确认风险和验证方式，再按步骤推进。",
    "@watch 请以监察者模式运行：检查当前 workspace、ToDo、计划任务和潜在问题，必要时提醒我确认。",
    "@sop 请先匹配最相关的 SOP，再严格按 SOP 步骤执行并说明使用了哪个 SOP。",
    "@review 请进入审查模式：优先列出缺陷、风险、回归点和缺失验证，不要先做泛泛总结。",
    "@goal 请进入目标模式：先明确最终目标、成功标准和当前约束，再持续围绕目标推进；必要时主动拆解子目标、更新进展并提醒我关键决策。",
)

_GENERIC_TITLE_TEXTS = {
    "继续",
    "继续吧",
    "好的",
    "ok",
    "OK",
    "可以",
    "重启一下吧",
    "重新跑吧",
}


def _clean_title_candidate(text):
    text = _compact_text(text, 180)
    if not text:
        return ""
    text = re.sub(
        r"/(?:[^\s，,。；;：:！？!?]+/)*[^\s，,。；;：:！？!?]+",
        lambda m: os.path.basename(m.group(0).rstrip("/")) or "项目",
        text,
    )
    for prefix in _MODE_BOILERPLATE_PREFIXES:
        if text == prefix:
            return ""
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    text = re.sub(r"^@(plan|watch|watcher|sop|review|goal)\s*", "", text, flags=re.I).strip()
    text = re.sub(r"^(请)?(进入计划模式|以监察者模式运行|先匹配最相关的\s*SOP|进入审查模式|进入目标模式)[：:，,\s]*", "", text, flags=re.I).strip()
    text = re.sub(r"^(先把目标拆成可执行步骤|检查当前 workspace、ToDo、计划任务和潜在问题|严格按 SOP 步骤执行|优先列出缺陷、风险、回归点和缺失验证|先明确最终目标、成功标准和当前约束).*", "", text, flags=re.I).strip()
    text = re.sub(r"^(帮我|请你|麻烦你|能不能|可以帮我)\s*", "", text).strip()
    text = re.sub(r"^关于当前", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip(" ，,。；;：:")
    return text


def _short_title(text, limit=20):
    text = _clean_title_candidate(text)
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"[。！？!?；;\n]", text) if p.strip()]
    if parts:
        text = parts[0]
    text = re.sub(r"[\"'“”‘’`]+", "", text).strip()
    text = text.strip(" ，,。；;：:")
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip(" ，,。；;：:")


def _conversation_title(messages):
    candidates = []
    for idx, msg in enumerate(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            title = _short_title(_message_preview(msg, 180))
            if title and title not in _GENERIC_TITLE_TEXTS:
                candidates.append((min(len(title), 20), idx, title))
    if candidates:
        return max(candidates)[2]
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            title = _short_title(_message_preview(msg, 180))
            if title:
                return title
    return "新对话"


def _conversation_summary(messages):
    if not messages:
        return "空对话"
    user_count = sum(1 for m in messages if m.get("role") == "user")
    assistant_count = sum(1 for m in messages if m.get("role") == "assistant")
    first_user = ""
    last_assistant = ""
    for msg in messages:
        if msg.get("role") == "user":
            first_user = _message_preview(msg, 90)
            break
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            last_assistant = _message_preview(msg, 120)
            break
    parts = [f"{user_count} 轮用户输入 / {assistant_count} 轮助手回复"]
    if first_user:
        parts.append(f"起始：{first_user}")
    if last_assistant:
        parts.append(f"最近回复：{last_assistant}")
    return "；".join(parts)


def _normalize_conversation_doc(data):
    if not isinstance(data, dict):
        data = _new_conversation_doc()
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = []
    data["messages"] = messages
    data.setdefault("session_id", uuid.uuid4().hex)
    data.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    data.setdefault("updated_at", data.get("created_at"))
    if not data.get("title_locked") or not str(data.get("title") or "").strip():
        data["title"] = _conversation_title(messages)
    data["summary"] = _conversation_summary(messages)
    return data


def _read_current_conversation():
    path = _current_conversation_path()
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return _normalize_conversation_doc(data)
    except Exception:
        pass
    return _new_conversation_doc()


def _write_current_conversation(data):
    data = _normalize_conversation_doc(data)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if not data.get("title_locked") or not str(data.get("title") or "").strip():
        data["title"] = _conversation_title(data.get("messages") or [])
    data["summary"] = _conversation_summary(data.get("messages") or [])
    path = _current_conversation_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _append_current_conversation(role, content, source="user", run_id=None, request_id=None):
    if not isinstance(content, str) or not content:
        return
    try:
        data = _read_current_conversation()
        data.setdefault("messages", []).append({
            "id": uuid.uuid4().hex,
            "role": role,
            "content": content,
            "source": source,
            "run_id": run_id or "",
            "request_id": request_id or "",
            "timestamp": time.strftime("%H:%M:%S"),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })
        _write_current_conversation(data)
    except Exception as e:
        _debug_log("conversation_append_failed", role=role, error=str(e))


def _conversation_session_payload(data, path="", current=False):
    data = _normalize_conversation_doc(data)
    messages = data.get("messages") or []
    last_message = messages[-1] if messages else {}
    return {
        "session_id": data.get("session_id"),
        "title": data.get("title") or _conversation_title(messages),
        "summary": data.get("summary") or _conversation_summary(messages),
        "created_at": data.get("created_at") or "",
        "updated_at": data.get("updated_at") or "",
        "message_count": len(messages),
        "last_role": last_message.get("role", "") if isinstance(last_message, dict) else "",
        "last_preview": _message_preview(last_message if isinstance(last_message, dict) else {}, 120),
        "current": bool(current),
        "path": path,
    }


def _search_norm(text):
    text = _message_text(text).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[\s\r\n\t]+", " ", text)
    return text.strip()


def _search_tokens(text):
    text = _search_norm(text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    words = re.findall(r"[a-z0-9_]{2,}", text)
    grams = set()
    compact = re.sub(r"\s+", "", text)
    for n in (2, 3):
        for i in range(max(0, len(compact) - n + 1)):
            grams.add(compact[i:i + n])
    return set(cjk) | set(words) | grams


def _conversation_search_score(query, haystack, mode="auto"):
    q = _search_norm(query)
    h = _search_norm(haystack)
    if not q or not h:
        return 0.0

    terms = [t for t in re.split(r"\s+", q) if t]
    keyword_score = 0.0
    for term in terms:
        count = h.count(term)
        if count:
            keyword_score += 3.0 + min(count, 8) * 0.4
    if q in h:
        keyword_score += 6.0

    q_tokens = _search_tokens(q)
    h_tokens = _search_tokens(h)
    semantic_score = 0.0
    if q_tokens and h_tokens:
        overlap = q_tokens & h_tokens
        semantic_score = len(overlap) / max(1, len(q_tokens))
        semantic_score += 0.35 * (len(overlap) / max(1, len(h_tokens)))
        if q in h:
            semantic_score += 0.5

    fuzzy_score = 0.0
    compact_q = re.sub(r"\s+", "", q)
    compact_h = re.sub(r"\s+", "", h)
    if compact_q and compact_h:
        if len(compact_h) > 5000:
            idx = compact_h.find(compact_q[: max(2, min(len(compact_q), 12))])
            if idx >= 0:
                start = max(0, idx - 800)
                compact_h = compact_h[start:start + 2000]
            else:
                compact_h = compact_h[:5000]
        fuzzy_score = SequenceMatcher(None, compact_q, compact_h).ratio()

    mode = str(mode or "auto").lower()
    if mode == "keyword":
        return keyword_score
    if mode == "semantic":
        return semantic_score
    return max(keyword_score, semantic_score * 8.0, fuzzy_score * 5.0)


def _conversation_snippet(text, query, limit=260):
    raw = _message_text(text)
    flat = re.sub(r"\s+", " ", raw).strip()
    if len(flat) <= limit:
        return flat
    q = _search_norm(query)
    lower = flat.lower()
    idx = lower.find(q) if q else -1
    if idx < 0:
        terms = [t for t in re.split(r"\s+", q) if t]
        idxs = [lower.find(t) for t in terms if lower.find(t) >= 0]
        idx = min(idxs) if idxs else 0
    start = max(0, idx - limit // 3)
    end = min(len(flat), start + limit)
    start = max(0, end - limit)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(flat) else ""
    return prefix + flat[start:end].strip() + suffix


def _write_conversation_file(kind, path, data):
    data = _normalize_conversation_doc(data)
    if kind == "current":
        _write_current_conversation(data)
        return
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if not data.get("title_locked") or not str(data.get("title") or "").strip():
        data["title"] = _conversation_title(data.get("messages") or [])
    data["summary"] = _conversation_summary(data.get("messages") or [])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _read_conversation_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return _normalize_conversation_doc(json.load(f))


def _conversation_file_candidates():
    out = []
    current_path = _current_conversation_path()
    if os.path.isfile(current_path):
        out.append(("current", current_path))
    session_dir = _archived_conversation_dir()
    for name in sorted(os.listdir(session_dir), reverse=True):
        if name.endswith(".json"):
            out.append(("archived", os.path.join(session_dir, name)))
    return out


def _find_conversation_file(session_id):
    target = str(session_id or "")
    for kind, path in _conversation_file_candidates():
        try:
            data = _read_conversation_file(path)
        except Exception:
            continue
        if target in ("current", data.get("session_id"), os.path.basename(path)):
            return kind, path, data
    return None, "", None


def _sync_agent_context_from_conversation(data):
    data = _normalize_conversation_doc(data)
    messages = data.get("messages") or []
    summary = data.get("summary") or _conversation_summary(messages)
    history_info = [f"[Agent] 已恢复历史会话：{summary}"]
    for msg in messages[-24:]:
        role = msg.get("role")
        content = _message_preview(msg, 360)
        if not content:
            continue
        if role == "user":
            history_info.append(f"[USER]: {content}")
        elif role == "assistant":
            history_info.append(f"[Agent] {content}")
    try:
        state.agent.history = history_info
    except Exception:
        pass

    llm_history = []
    if summary:
        llm_history.append({
            "role": "user",
            "content": [{"type": "text", "text": f"以下是已恢复对话的压缩上下文，后续回答应延续该上下文：\n{summary}"}],
        })
        llm_history.append({
            "role": "assistant",
            "content": [{"type": "text", "text": "已读取恢复会话上下文，将在后续对话中延续。"}],
        })
    for msg in messages[-8:]:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _message_preview(msg, 2000)
        if text:
            llm_history.append({"role": role, "content": [{"type": "text", "text": text}]})
    try:
        backend = getattr(getattr(state.agent, "llmclient", None), "backend", None)
        if backend is not None:
            backend.history = llm_history
    except Exception:
        pass


def _sync_agent_from_session(sess):
    data = _normalize_conversation_doc(sess.data)
    messages = data.get("messages") or []
    summary = data.get("summary") or _conversation_summary(messages)
    history_info = [f"[Agent] 当前多会话上下文：{summary}"]
    for msg in messages[-24:]:
        role = msg.get("role")
        content = _message_preview(msg, 360)
        if not content:
            continue
        if role == "user":
            history_info.append(f"[USER]: {content}")
        elif role == "assistant":
            history_info.append(f"[Agent] {content}")
    try:
        sess.agent.history = history_info
    except Exception:
        pass

    llm_history = []
    if summary:
        llm_history.append({
            "role": "user",
            "content": [{"type": "text", "text": f"以下是当前会话的压缩上下文，后续回答应延续该上下文：\n{summary}"}],
        })
        llm_history.append({
            "role": "assistant",
            "content": [{"type": "text", "text": "已读取当前会话上下文，将在后续对话中延续。"}],
        })
    for msg in messages[-8:]:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _message_preview(msg, 2000)
        if text:
            llm_history.append({"role": role, "content": [{"type": "text", "text": text}]})
    try:
        backend = getattr(getattr(sess.agent, "llmclient", None), "backend", None)
        if backend is not None:
            backend.history = llm_history
    except Exception:
        pass


def _append_session_conversation(sess, role, content, source="user", run_id=None, request_id=None):
    if not isinstance(content, str) or not content:
        return
    with sess.lock:
        sess.data.setdefault("messages", []).append({
            "id": uuid.uuid4().hex,
            "role": role,
            "content": content,
            "source": source,
            "run_id": run_id or "",
            "request_id": request_id or "",
            "timestamp": time.strftime("%H:%M:%S"),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })
        sess.data = _normalize_conversation_doc(sess.data)
        session_manager._save(sess)


def _archive_current_conversation(reason="new_conversation"):
    data = _read_current_conversation()
    messages = data.get("messages") or []
    archived_path = ""
    if messages:
        try:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            sid = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(data.get("session_id") or "session"))[:32]
            archived_path = os.path.join(_archived_conversation_dir(), f"{stamp}-{sid}.json")
            data["archived_at"] = datetime.now().isoformat(timespec="seconds")
            data["archive_reason"] = reason
            with open(archived_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _debug_log("conversation_archive_failed", error=str(e))
    fresh = _new_conversation_doc()
    _write_current_conversation(fresh)
    return fresh, archived_path


import json

def _load_mykey_module_from_path(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        if str(path).endswith(".py"):
            spec = importlib.util.spec_from_file_location(f"_mykey_api_{uuid.uuid4().hex}", path)
            if not spec or not spec.loader:
                return {}
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return {k: v for k, v in vars(module).items() if not k.startswith("_")}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return {}

def _extract_llm_configs_from_module(module):
    configs = []
    if not module or not isinstance(module, dict):
        return configs
    for k, v in module.items():
        if isinstance(v, dict) and all(x in v for x in ("apikey", "apibase", "model")):
            apikey = str(v.get("apikey") or "")
            tp = v.get("type")
            if not tp:
                tp = "claude" if "claude" in k else ("oai" if ("oai" in k or "model" in k) else "other")
            configs.append({
                "id": k,
                "type": tp,
                "apibase": str(v.get("apibase") or ""),
                "model": str(v.get("model") or ""),
                "has_key": bool(apikey),
                "key_last4": apikey[-4:] if len(apikey) >= 4 else apikey
            })
        elif k == "sider_cookie" and isinstance(v, str):
            cookie = v.strip()
            configs.append({
                "id": k,
                "type": "sider",
                "apibase": "",
                "model": "",
                "has_key": bool(cookie),
                "key_last4": cookie[-4:] if len(cookie) >= 4 else ""
            })
    return configs

def _is_simple_value(v):
    return isinstance(v, (str, int, float, bool, dict, list))

def _read_mykey_simple_assignments(module):
    order = []
    values = {}
    if not module or not isinstance(module, dict):
        return order, values
    for k, v in module.items():
        if not isinstance(k, str) or k.startswith("__"):
            continue
        if _is_simple_value(v):
            order.append(k)
            values[k] = v
    return order, values

def _alloc_config_name(existing_ids, prefix):
    if prefix not in existing_ids:
        return prefix
    i = 1
    while True:
        cand = f"{prefix}{i}"
        if cand not in existing_ids:
            return cand
        i += 1

def _render_mykey_py(order, values):
    out = {}
    for k in order:
        if k in values:
            out[k] = values[k]
    return json.dumps(out, indent=4, ensure_ascii=False) + "\n"

def _reload_agent_state():
    state.cancel_runs(None)
    state.clear_human_input()
    state.agent, state.agent_init_error = init_agent()
    return state.agent_init_error

def _normalize_api_base(apibase):
    if not isinstance(apibase, str):
        return ""
    return apibase.strip().rstrip("/")

def _auto_make_url(base, path):
    b = (base or "").strip().rstrip("/")
    p = (path or "").strip().lstrip("/")
    return f"{b}/{p}" if p else b


COMMUNICATION_TOOLS = {
    "feishu": {
        "label": "飞书",
        "name": "Feishu",
        "id_key": "fs_app_id",
        "secret_key": "fs_app_secret",
        "allowed_key": "fs_allowed_users",
        "script": "fsapp.py",
        "process_keywords": ("frontends/fsapp.py", "fsapp.py"),
    },
    "wecom": {
        "label": "企业微信",
        "name": "WeCom",
        "id_key": "wecom_bot_id",
        "secret_key": "wecom_secret",
        "allowed_key": "wecom_allowed_users",
        "script": "wecomapp.py",
        "process_keywords": ("frontends/wecomapp.py", "wecomapp.py"),
    },
    "qq": {
        "label": "QQ",
        "name": "QQ",
        "id_key": "qq_app_id",
        "secret_key": "qq_app_secret",
        "allowed_key": "qq_allowed_users",
        "script": "qqapp.py",
        "process_keywords": ("frontends/qqapp.py", "qqapp.py"),
    },
    "dingtalk": {
        "label": "钉钉",
        "name": "DingTalk",
        "id_key": "dingtalk_client_id",
        "secret_key": "dingtalk_client_secret",
        "allowed_key": "dingtalk_allowed_users",
        "script": "dingtalkapp.py",
        "process_keywords": ("frontends/dingtalkapp.py", "dingtalkapp.py"),
    },
}


def _mask_config_secret(value):
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * max(4, len(value) - 4) + value[-4:]


def _process_snapshot():
    try:
        return subprocess.check_output(["ps", "-ef"], text=True, stderr=subprocess.DEVNULL, timeout=3)
    except Exception:
        return ""


def _communication_script_path(spec):
    script = spec.get("script")
    if not script:
        return ""
    candidates = [
        os.path.join(BASE_DIR, "frontends", script),
        os.path.join(BASE_DIR, "..", "frontends", script),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontends", script),
    ]
    for candidate in candidates:
        path = os.path.abspath(os.path.normpath(candidate))
        if os.path.exists(path):
            return path
    return os.path.abspath(os.path.join(BASE_DIR, "frontends", script))


def _communication_python_path():
    candidates = [
        os.environ.get("GA_COMM_PYTHON"),
        os.path.join(os.path.expanduser("~"), "anaconda3", "envs", "kw", "bin", "python"),
        "/opt/anaconda3/envs/kw/bin/python",
        sys.executable,
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return sys.executable


def _communication_tool_status(tool_id, spec, values, process_text):
    app_id = str(values.get(spec["id_key"], "") or "").strip()
    secret = str(values.get(spec["secret_key"], "") or "").strip()
    allowed = values.get(spec.get("allowed_key", ""), [])
    if isinstance(allowed, str):
        allowed = [allowed] if allowed.strip() else []
    elif not isinstance(allowed, list):
        allowed = []
    configured = bool(app_id and (secret or spec.get("optional")))
    running = bool(configured and process_text and any(k in process_text for k in spec.get("process_keywords", ())))
    if not configured:
        status = "unconfigured"
    elif running:
        status = "ok"
    else:
        status = "failed"
    return {
        "id": tool_id,
        "label": spec["label"],
        "name": spec.get("name", ""),
        "status": status,
        "configured": configured,
        "running": running,
        "id_key": spec["id_key"],
        "secret_key": spec["secret_key"],
        "allowed_key": spec.get("allowed_key", ""),
        "app_id": app_id,
        "has_secret": bool(secret),
        "secret_masked": _mask_config_secret(secret),
        "allowed_users": [str(x) for x in allowed if str(x).strip()],
    }


def _communication_log_path(tool_id):
    root = ensure_dir(os.path.join(get_user_data_dir(), "logs"))
    return os.path.join(root, f"communication-{tool_id}.log")

def log_api(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(API_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

@app.middleware("http")
async def capture_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        log_api(f"{request.method} {request.url.path} -> {e}")
        log_api(traceback.format_exc())
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "error": str(e)})

# Stream Manager for Global Broadcasting
class StreamManager:
    def __init__(self):
        self.queues = []
        self.lock = threading.Lock()

    def add_queue(self):
        q = queue.Queue()
        with self.lock:
            self.queues.append(q)
        return q

    def remove_queue(self, q):
        with self.lock:
            if q in self.queues:
                self.queues.remove(q)

    def broadcast(self, data):
        with self.lock:
            for q in self.queues:
                q.put(data)

stream_manager = StreamManager()

# Helper to bridge Agent Queue to Stream Manager
def process_agent_output(display_queue, source="user", prompt_text=None, run_id=None, cancel_event=None, request_id=None):
    finished_normally = False
    def broadcast_state(state_name, reason=""):
        payload = {
            "type": "state",
            "state": state_name,
            "source": source,
            "run_id": run_id,
            "request_id": request_id,
        }
        if reason:
            payload["reason"] = reason
        state.ui_state = state_name
        print(f"[Status] broadcast state={state_name} source={source} run_id={run_id} reason={reason}")
        _debug_log("state", state=state_name, source=source, run_id=run_id, request_id=request_id, reason=reason)
        stream_manager.broadcast(json.dumps(payload))

    # If we have the prompt text (e.g. for autonomous), broadcast it as a user message first
    # This ensures the UI shows what triggered the action
    if prompt_text:
        _debug_log("message", phase="prompt", source=source, run_id=run_id, request_id=request_id, prompt_len=len(prompt_text))
        stream_manager.broadcast(json.dumps({
            'type': 'message', 
            'role': 'user', 
            'content': prompt_text,
            'source': source,
            'run_id': run_id,
            'request_id': request_id,
            'timestamp': time.strftime('%H:%M:%S')
        }))
        _append_current_conversation("user", prompt_text, source=source, run_id=run_id, request_id=request_id)

    # Notify start of assistant response
    _debug_log("start", source=source, run_id=run_id, request_id=request_id, has_prompt=bool(prompt_text))
    stream_manager.broadcast(json.dumps({
        'type': 'start', 
        'source': source,
        'run_id': run_id
        , 'request_id': request_id
    }))
    broadcast_state("running", "stream start")
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                stream_manager.broadcast(json.dumps({
                    'type': 'done',
                    'content': '',
                    'source': source,
                    'run_id': run_id,
                    'stopped': True
                }))
                break
            try:
                item = display_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if 'next' in item:
                if cancel_event is None or not cancel_event.is_set():
                    chunk_text = item.get('next', '')
                    _debug_log("chunk", source=source, run_id=run_id, request_id=request_id, chunk_len=len(chunk_text), preview=str(chunk_text)[:120])
                    stream_manager.broadcast(json.dumps({
                        'type': 'chunk', 
                        'content': chunk_text,
                        'source': source,
                        'run_id': run_id,
                        'request_id': request_id
                    }))
            if 'done' in item:
                if cancel_event is None or not cancel_event.is_set():
                    done_text = item.get('done', '')
                    _debug_log("done", source=source, run_id=run_id, request_id=request_id, done_len=len(done_text), human_like=_looks_like_human_request(done_text))
                    if _looks_like_human_request(done_text):
                        state.set_human_input(item.get('done', ''), [])
                        broadcast_state("need-user", "done suggests human input")
                    else:
                        broadcast_state("idle", "stream done")
                    finished_normally = True
                    stream_manager.broadcast(json.dumps({
                        'type': 'done', 
                        'content': item['done'],
                        'source': source,
                        'run_id': run_id,
                        'request_id': request_id
                    }))
                    _append_current_conversation("assistant", done_text, source=source, run_id=run_id, request_id=request_id)
                break
    finally:
        try:
            state.finish_run(run_id)
        except Exception:
            pass
        if not finished_normally and not getattr(state.agent, "is_running", False):
            broadcast_state("idle", "run finished")


def process_session_agent_output(sess, display_queue, source="user", prompt_text=None, run_id=None, cancel_event=None, request_id=None):
    finished_normally = False

    def emit(payload):
        payload["session_id"] = sess.id
        stream_manager.broadcast(json.dumps(payload))

    def broadcast_state(state_name, reason=""):
        sess.status = state_name
        payload = {
            "type": "state",
            "state": state_name,
            "source": source,
            "run_id": run_id,
            "request_id": request_id,
            "session_id": sess.id,
        }
        if reason:
            payload["reason"] = reason
        _debug_log("session_state", session_id=sess.id, state=state_name, source=source, run_id=run_id, request_id=request_id, reason=reason)
        stream_manager.broadcast(json.dumps(payload))

    if prompt_text:
        _debug_log("session_message", phase="prompt", session_id=sess.id, source=source, run_id=run_id, request_id=request_id, prompt_len=len(prompt_text))
        emit({
            "type": "message",
            "role": "user",
            "content": prompt_text,
            "source": source,
            "run_id": run_id,
            "request_id": request_id,
            "timestamp": time.strftime("%H:%M:%S"),
        })
        _append_session_conversation(sess, "user", prompt_text, source=source, run_id=run_id, request_id=request_id)

    emit({"type": "start", "source": source, "run_id": run_id, "request_id": request_id})
    broadcast_state("running", "stream start")
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                emit({"type": "done", "content": "", "source": source, "run_id": run_id, "request_id": request_id, "stopped": True})
                break
            try:
                item = display_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if "next" in item:
                if cancel_event is None or not cancel_event.is_set():
                    chunk_text = item.get("next", "")
                    emit({"type": "chunk", "content": chunk_text, "source": source, "run_id": run_id, "request_id": request_id})
            if "done" in item:
                if cancel_event is None or not cancel_event.is_set():
                    done_text = item.get("done", "")
                    if _looks_like_human_request(done_text):
                        broadcast_state("need-user", "done suggests human input")
                    else:
                        broadcast_state("idle", "stream done")
                    finished_normally = True
                    emit({"type": "done", "content": done_text, "source": source, "run_id": run_id, "request_id": request_id})
                    _append_session_conversation(sess, "assistant", done_text, source=source, run_id=run_id, request_id=request_id)
                break
    finally:
        session_manager.finish_run(sess, run_id)
        if not finished_normally and not getattr(sess.agent, "is_running", False):
            broadcast_state("idle", "run finished")

# Global State
class AppState:
    def __init__(self):
        self.autonomous_enabled = False
        self.last_activity_time = time.time()
        self.autonomous_threshold = 1800 # Default 30 minutes
        self.agent = None
        self.agent_init_error = None
        self.needs_human_input = False
        self.human_question = ""
        self.human_candidates = []
        self.scheduler_enabled = False
        self.scheduler_interval = 60
        self.run_lock = threading.Lock()
        self.active_runs = {}
        self.ui_state = "idle"
        self.stopping = False

    def new_run(self):
        run_id = uuid.uuid4().hex
        cancel_event = threading.Event()
        with self.run_lock:
            self.active_runs[run_id] = cancel_event
        return run_id, cancel_event

    def cancel_runs(self, run_ids=None):
        with self.run_lock:
            if run_ids is None:
                run_ids = list(self.active_runs.keys())
            else:
                run_ids = [rid for rid in run_ids if rid in self.active_runs]
            for rid in run_ids:
                try:
                    self.active_runs[rid].set()
                except Exception:
                    pass
        return run_ids

    def finish_run(self, run_id):
        if not run_id:
            return
        with self.run_lock:
            self.active_runs.pop(run_id, None)

    def clear_human_input(self):
        self.needs_human_input = False
        self.human_question = ""
        self.human_candidates = []
        self.ui_state = "idle"

    def set_human_input(self, question, candidates=None):
        self.needs_human_input = True
        self.human_question = question or ""
        self.human_candidates = candidates or []
        self.ui_state = "need-user"

class FallbackAgent:
    def __init__(self, err):
        self.llmclient = None
        self.is_running = False
        self.history = []
        self._err = err
    def get_llm_name(self):
        return "Unavailable"
    def abort(self):
        return None
    def next_llm(self):
        return None
    def run(self):
        return None
    def put_task(self, query, source="user", images=None):
        q = queue.Queue()
        q.put({"done": f"服务初始化失败：{self._err}"})
        return q

state = AppState()


class ChatSession:
    def __init__(self, data=None):
        data = _normalize_conversation_doc(data or _new_conversation_doc())
        self.id = str(data.get("session_id") or uuid.uuid4().hex)
        data["session_id"] = self.id
        self.data = data
        self.agent = None
        self.agent_init_error = None
        self.thread = None
        self.status = "idle"
        self.active_runs = {}
        self.lock = threading.RLock()


class ChatSessionManager:
    def __init__(self):
        self.sessions = {}
        self.active_session_id = ""
        self.lock = threading.RLock()

    def _path(self, session_id):
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(session_id or "session"))[:64]
        return os.path.join(_live_conversation_dir(), f"{safe}.json")

    def _save(self, sess):
        data = _normalize_conversation_doc(sess.data)
        data["status"] = sess.status
        path = self._path(sess.id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def _load_live(self):
        for name in sorted(os.listdir(_live_conversation_dir())):
            if not name.endswith(".json"):
                continue
            path = os.path.join(_live_conversation_dir(), name)
            try:
                data = _read_conversation_file(path)
            except Exception:
                continue
            sid = str(data.get("session_id") or os.path.splitext(name)[0])
            if sid not in self.sessions:
                self.sessions[sid] = ChatSession(data)

    def ensure_started(self):
        with self.lock:
            self._load_live()
            if not self.sessions:
                sess = ChatSession()
                self.sessions[sess.id] = sess
                self.active_session_id = sess.id
                self._save(sess)
            elif not self.active_session_id or self.active_session_id not in self.sessions:
                self.active_session_id = next(iter(self.sessions))
            return self.active_session_id

    def list(self):
        self.ensure_started()
        with self.lock:
            out = []
            for sess in self.sessions.values():
                payload = _conversation_session_payload(sess.data, path=self._path(sess.id), current=(sess.id == self.active_session_id))
                payload["status"] = sess.status
                payload["active"] = sess.id == self.active_session_id
                out.append(payload)
            out.sort(key=lambda x: (not x.get("active"), x.get("updated_at") or ""), reverse=False)
            return out

    def get(self, session_id=None):
        self.ensure_started()
        sid = str(session_id or self.active_session_id or "")
        with self.lock:
            sess = self.sessions.get(sid)
            if sess is None:
                raise KeyError(sid)
            return sess

    def create(self, title=""):
        with self.lock:
            data = _new_conversation_doc()
            if title:
                data["title"] = str(title)[:80]
                data["title_locked"] = True
            sess = ChatSession(data)
            self.sessions[sess.id] = sess
            self.active_session_id = sess.id
            self._save(sess)
            return sess

    def activate(self, session_id):
        sess = self.get(session_id)
        with self.lock:
            self.active_session_id = sess.id
        return sess

    def delete(self, session_id):
        self.ensure_started()
        sid = str(session_id or "")
        with self.lock:
            sess = self.sessions.get(sid)
            if sess is None:
                raise KeyError(sid)
            was_active = sid == self.active_session_id
            self.cancel(sess)
            self.sessions.pop(sid, None)
            try:
                path = self._path(sid)
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                _debug_log("session_delete_file_failed", session_id=sid, error=str(e))
            next_id = ""
            if self.sessions:
                if was_active or self.active_session_id not in self.sessions:
                    self.active_session_id = next(iter(self.sessions))
                next_id = self.active_session_id
            else:
                next_sess = ChatSession()
                self.sessions[next_sess.id] = next_sess
                self.active_session_id = next_sess.id
                self._save(next_sess)
                next_id = next_sess.id
            return next_id

    def _make_agent(self, sess):
        if state.agent_init_error:
            return FallbackAgent(state.agent_init_error), state.agent_init_error
        try:
            importlib.invalidate_caches()
            import agentmain
            agent = agentmain.GeneraticAgent()
            agent.inc_out = True
            threading.Thread(target=agent.run, daemon=True, name=f"a3-session-{sess.id[:8]}").start()
            return agent, None
        except Exception as e:
            return FallbackAgent(str(e)), str(e)

    def ensure_agent(self, sess):
        with sess.lock:
            if sess.agent is None:
                sess.agent, sess.agent_init_error = self._make_agent(sess)
                _sync_agent_from_session(sess)
            return sess.agent

    def new_run(self, sess):
        run_id = uuid.uuid4().hex
        cancel_event = threading.Event()
        with sess.lock:
            sess.active_runs[run_id] = cancel_event
            sess.status = "running"
        return run_id, cancel_event

    def finish_run(self, sess, run_id):
        with sess.lock:
            sess.active_runs.pop(run_id, None)
            if not sess.active_runs and sess.status == "running":
                sess.status = "idle"
            self._save(sess)

    def cancel(self, sess):
        with sess.lock:
            for ev in sess.active_runs.values():
                try:
                    ev.set()
                except Exception:
                    pass
            if sess.agent and hasattr(sess.agent, "abort"):
                try:
                    sess.agent.abort()
                except Exception:
                    pass
            sess.status = "idle"
            self._save(sess)


session_manager = ChatSessionManager()

def init_agent():
    try:
        importlib.invalidate_caches()
        if "mykey" in sys.modules:
            del sys.modules["mykey"]
        if "llmcore" in sys.modules:
            importlib.reload(sys.modules["llmcore"])
        else:
            import llmcore  # noqa: F401
        if "agent_loop" in sys.modules:
            importlib.reload(sys.modules["agent_loop"])
        try:
            from plugins.hooks import discover_and_load
            discover_and_load(reload=True)
        except Exception:
            pass
        try:
            if "sidercall" in sys.modules:
                importlib.reload(sys.modules["sidercall"])
            else:
                import sidercall  # noqa: F401
        except ModuleNotFoundError:
            # Current GenericAgent core does not require sidercall; keep it optional
            # so the fixed frontend/API layer can survive backend-only py swaps.
            pass
        if "agentmain" in sys.modules:
            importlib.reload(sys.modules["agentmain"])
        import agentmain
        agent = agentmain.GeneraticAgent()
        agent.inc_out = True
        if agent.llmclient is None:
            print("Warning: No LLM client configured.")
        threading.Thread(target=agent.run, daemon=True).start()
        return agent, None
    except Exception as e:
        err = str(e)
        print(f"Warning: agent init failed: {err}")
        return FallbackAgent(err), err

state.agent, state.agent_init_error = init_agent()

# Autonomous Monitor Thread
def autonomous_monitor():
    while True:
        time.sleep(10)
        if state.autonomous_enabled and state.agent_init_error is None:
            idle_time = time.time() - state.last_activity_time
            if idle_time > state.autonomous_threshold: 
                if not state.agent.is_running:
                    print(f"Triggering autonomous action (Idle: {int(idle_time)}s)")
                    # Update time to prevent double trigger
                    state.last_activity_time = time.time()
                    
                    # Construct the autonomous prompt
                    prompt = f"Current Time: {time.strftime('%Y-%m-%d %H:%M:%S')}. You are in autonomous mode (idle for >{int(state.autonomous_threshold/60)}m). Check pending tasks, explore, or perform maintenance."
                    display_queue = state.agent.put_task(prompt, source="autonomous")
                    run_id, cancel_event = state.new_run()
                    # Start background task to broadcast output
                    threading.Thread(target=process_agent_output, args=(display_queue, "autonomous", prompt, run_id, cancel_event), daemon=True).start()
        
threading.Thread(target=autonomous_monitor, daemon=True).start()

def _parse_task_time(filename):
    m = re.match(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_", filename)
    if not m:
        return None
    try:
        date_part = m.group(1)
        hm = m.group(2)
        ts = f"{date_part} {hm[:2]}:{hm[2:]}"
        return time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M"))
    except Exception:
        return None

def scheduler_monitor():
    while True:
        time.sleep(1)
        if not state.scheduler_enabled or state.agent_init_error is not None:
            time.sleep(1)
            continue
        try:
            base = get_user_data_dir()
            pending_dir = os.path.join(base, "sche_tasks", "pending")
            running_dir = os.path.join(base, "sche_tasks", "running")
            os.makedirs(pending_dir, exist_ok=True)
            os.makedirs(running_dir, exist_ok=True)
            now = time.time()
            due = []
            for fn in os.listdir(pending_dir):
                ts = _parse_task_time(fn)
                if ts is not None and ts <= now:
                    due.append((ts, fn))
            due.sort()
            for _, fn in due[:1]:
                src = os.path.join(pending_dir, fn)
                dst = os.path.join(running_dir, fn)
                try:
                    os.rename(src, dst)
                except Exception:
                    continue
                try:
                    raw = _read_text(dst)
                except Exception:
                    raw = ""
                prompt = f"按scheduled_task_sop执行任务文件 ./sche_tasks/running/{fn}（立刻移到done）\n内容：\n{raw}"
                display_queue = state.agent.put_task(prompt, source="scheduler")
                run_id, cancel_event = state.new_run()
                threading.Thread(target=process_agent_output, args=(display_queue, "scheduler", prompt, run_id, cancel_event), daemon=True).start()
        except Exception:
            pass
        time.sleep(max(1, int(state.scheduler_interval)))

threading.Thread(target=scheduler_monitor, daemon=True).start()

# CORS for development convenience
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/status")
def get_status():
    try:
        idle_time = int(time.time() - state.last_activity_time)
        llmclient = getattr(state.agent, "llmclient", None)
        llm_name = "No LLM"
        llm_list = []
        if llmclient:
            try:
                llm_name = state.agent.get_llm_name()
                llm_list = state.agent.list_llms()
            except Exception:
                llm_name = "LLM Unavailable"
        history = getattr(state.agent, "history", []) or []
        is_running = bool(getattr(state.agent, "is_running", False))
        return {
            "llm_name": llm_name,
            "llm_list": llm_list,
            "is_running": is_running,
            "ui_state": state.ui_state,
            "history_len": len(history),
            "token_usage": _token_usage_payload(),
            "autonomous_enabled": state.autonomous_enabled,
            "autonomous_threshold": state.autonomous_threshold,
            "idle_time": idle_time,
            "last_activity_time": state.last_activity_time,
            "agent_init_error": state.agent_init_error
            , "pending_interventions": bool(getattr(state.agent, "has_pending_interventions", lambda: False)())
            , "needs_human_input": state.needs_human_input
            , "human_question": state.human_question
            , "human_candidates": state.human_candidates
            , "scheduler_enabled": state.scheduler_enabled
            , "scheduler_interval": state.scheduler_interval
        }
    except Exception as e:
        return {
            "llm_name": "Status Error",
            "is_running": False,
            "ui_state": state.ui_state,
            "history_len": 0,
            "token_usage": {"available": False, "error": str(e)},
            "autonomous_enabled": state.autonomous_enabled,
            "autonomous_threshold": state.autonomous_threshold,
            "idle_time": 0,
            "last_activity_time": state.last_activity_time,
            "agent_init_error": state.agent_init_error,
            "pending_interventions": False,
            "needs_human_input": state.needs_human_input,
            "status_error": str(e)
        }

@app.get("/api/history")
def get_history():
    return {"history": state.agent.history}

@app.get("/api/history/raw")
def get_history_raw():
    archive_path = _find_history_archive_path()
    archive_data = None
    archive_raw = ""
    if archive_path:
        archive_data, archive_raw = _read_json_text(archive_path)
    current_history = []
    try:
        current_history = state.agent.history or []
    except Exception:
        current_history = []
    return {
        "current": current_history,
        "archive_path": archive_path,
        "archive_exists": bool(archive_path),
        "archive_json": archive_data,
        "archive_raw": archive_raw,
    }


@app.post("/api/uploads/images")
async def upload_images(request: Request):
    data = await request.json()
    items = data.get("images") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return JSONResponse(status_code=400, content={"error": "images must be a list"})
    saved = []
    for item in items[:12]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("filename") or "image.png"
        data_url = item.get("data_url") or item.get("dataUrl") or item.get("data")
        mime = str(item.get("mime") or item.get("type") or "image/png")
        blob, detected_mime = _decode_image_data_url(data_url, mime)
        if not blob:
            continue
        if len(blob) > 15 * 1024 * 1024:
            return JSONResponse(status_code=413, content={"error": f"image too large: {name}"})
        path = _safe_upload_image_path(name)
        guessed_ext = mimetypes.guess_extension(detected_mime or mime or "") or ""
        if guessed_ext.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp") and not path.lower().endswith(guessed_ext.lower()):
            path = os.path.splitext(path)[0] + guessed_ext.lower()
        with open(path, "wb") as f:
            f.write(blob)
        saved.append({
            "id": uuid.uuid4().hex,
            "name": os.path.basename(path),
            "path": path,
            "mime": detected_mime or mime,
            "size": len(blob),
        })
    return {"status": "saved", "images": saved}


@app.get("/api/sessions")
def list_live_sessions():
    return {
        "sessions": session_manager.list(),
        "active_session_id": session_manager.active_session_id,
    }


@app.post("/api/sessions")
async def create_live_session(request: Request):
    data = await request.json()
    sess = session_manager.create(title=str(data.get("title") or "").strip())
    return {
        "status": "created",
        "session": _conversation_session_payload(sess.data, path=session_manager._path(sess.id), current=True),
        "active_session_id": sess.id,
    }


@app.get("/api/sessions/{session_id}")
def get_live_session(session_id: str):
    try:
        sess = session_manager.get(session_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"error": "session not found"})
    payload = _conversation_session_payload(sess.data, path=session_manager._path(sess.id), current=(sess.id == session_manager.active_session_id))
    payload["messages"] = sess.data.get("messages") or []
    payload["status"] = sess.status
    return payload


@app.post("/api/sessions/{session_id}/activate")
async def activate_live_session(session_id: str):
    try:
        sess = session_manager.activate(session_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"error": "session not found"})
    return {"status": "active", "active_session_id": sess.id}


@app.delete("/api/sessions/{session_id}")
async def delete_live_session(session_id: str):
    try:
        next_id = session_manager.delete(session_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"error": "session not found"})
    return {
        "status": "deleted",
        "deleted_session_id": session_id,
        "active_session_id": next_id,
        "sessions": session_manager.list(),
    }


@app.post("/api/sessions/{session_id}/chat")
async def chat_live_session(session_id: str, request: Request):
    try:
        sess = session_manager.get(session_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"error": "session not found"})
    data = await request.json()
    prompt = data.get("prompt")
    request_id = data.get("request_id")
    raw_images = data.get("images") or []
    image_paths = []
    if isinstance(raw_images, list):
        for item in raw_images[:12]:
            path = item.get("path") if isinstance(item, dict) else item
            if not isinstance(path, str) or not path:
                continue
            ap = os.path.abspath(path)
            if os.path.isfile(ap):
                image_paths.append(ap)
    if not prompt:
        return JSONResponse(status_code=400, content={"error": "No prompt provided"})
    agent = session_manager.ensure_agent(sess)
    if getattr(agent, "is_running", False):
        return JSONResponse(status_code=409, content={"error": "session is already running"})
    prompt_for_display = prompt
    if image_paths:
        prompt_for_display = prompt.rstrip() + "\n\n" + "\n".join(f"![{os.path.basename(p)}]({p})" for p in image_paths)
    state.last_activity_time = time.time()
    display_queue = agent.put_task(prompt, source="user", images=image_paths)
    run_id, cancel_event = session_manager.new_run(sess)
    _debug_log("session_chat_queued", session_id=sess.id, run_id=run_id, request_id=request_id, prompt_len=len(prompt), image_count=len(image_paths))
    threading.Thread(target=process_session_agent_output, args=(sess, display_queue, "user", prompt_for_display, run_id, cancel_event, request_id), daemon=True).start()
    return {"status": "queued", "session_id": sess.id, "run_id": run_id, "request_id": request_id}


@app.post("/api/sessions/{session_id}/cancel")
async def cancel_live_session(session_id: str):
    try:
        sess = session_manager.get(session_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"error": "session not found"})
    session_manager.cancel(sess)
    return {"status": "cancelled", "session_id": sess.id}


@app.get("/api/goal/status")
def get_goal_status():
    return _goal_payload()


@app.post("/api/goal/start")
async def start_goal_mode(request: Request):
    data = await request.json()
    objective = str(data.get("objective") or "").strip()
    if not objective:
        return JSONResponse(status_code=400, content={"error": "objective is required"})
    budget_minutes = float(data.get("budget_minutes") or 30)
    budget_minutes = max(1, min(budget_minutes, 24 * 60))
    max_turns = int(data.get("max_turns") or 80)
    max_turns = max(1, min(max_turns, 500))
    done_prompt = str(data.get("done_prompt") or "").strip()

    if _goal_proc_alive():
        return JSONResponse(status_code=409, content={"error": "goal mode is already running", **_goal_payload()})

    state_doc = {
        "objective": objective,
        "budget_seconds": int(budget_minutes * 60),
        "start_time": time.time(),
        "turns_used": 0,
        "max_turns": max_turns,
        "status": "running",
        "done_prompt": done_prompt,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    state_path = _goal_state_path()
    log_path = _goal_log_path()
    try:
        proc = _start_goal_reflect_process(state_doc, state_path, log_path)
        goal_process.update({"proc": proc, "state_path": state_path, "started_at": time.time()})
    except Exception as e:
        state_doc["status"] = "error"
        state_doc["error"] = str(e)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state_doc, f, ensure_ascii=False, indent=2)
        return JSONResponse(status_code=500, content={"error": str(e), **_goal_payload()})
    return {"status": "started", **_goal_payload()}


@app.post("/api/goal/stop")
async def stop_goal_mode():
    _stop_goal_process("stopped")
    return {"status": "stopped", **_goal_payload()}


HIVE_MASTER_DUTY = """Hive Master 职责：
1. 你**负责任务调度和团队组织**，不允许亲自干活导致 worker 空转，耗时执行与复杂复核应拆给 worker
2. 终极目标是要做到**完美的找不到任何问题的**任务交付结果，保证用户满意，围绕核心产出（不太需要额外产出）
3. 针对任务目标设计要做的子任务，发到bbs上，worker会接任务并完成
4. 如果子任务很多，worker做不过来，可以参照Goal Hive Mode SOP拉起更多worker
5. 只要时间没到，就持续验收结果、检查问题、寻找下一个改进点，并继续设计新子任务
6. 时间没到不允许交付，必须头脑风暴找改进点和检查点，也可发动worker一起寻找改进点
7. BBS 中 human 发出的 @master、@hive-master、@all 是高优先级人工干预，必须优先回应并据此调整计划；@worker-N 指令要转发/协调给对应 worker"""

HIVE_DONE_PROMPT = "关闭所有你拉起的worker，并在BBS发一条帖子，宣告你管理的任务结束，worker除了明确追加任务外，不应再回应。"


def _hive_http_json(url, payload, key):
    import urllib.request
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "X-API-Key": key})
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _hive_http_get_json(url, key):
    import urllib.request
    req = urllib.request.Request(url, headers={"X-API-Key": key})
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else []


def _hive_target_procs(target):
    target = str(target or "all").lower().strip()
    procs = []
    if target in ("all", "master", "hive-master"):
        procs.append(("master", hive_process.get("master")))
    workers = hive_process.get("workers") or []
    if target in ("all", "workers", "worker", "all-workers"):
        procs.extend((f"worker-{i}", p) for i, p in enumerate(workers, start=1))
    else:
        m = re.match(r"worker[-_]?(\d+)$", target)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(workers):
                procs.append((f"worker-{idx + 1}", workers[idx]))
    return [(name, proc) for name, proc in procs if _proc_alive(proc)]


def _hive_post_system(content):
    data = _read_json_file(_hive_state_path()) or {}
    base_url = data.get("base_url")
    board_key = data.get("board_key")
    if not base_url or not board_key or not content:
        return
    try:
        token = data.get("control_token")
        if not token:
            token = _hive_http_json(f"{base_url}/register", {"name": "human-control"}, board_key).get("token")
            data["control_token"] = token
            _write_hive_state(data)
        _hive_http_json(f"{base_url}/post", {"token": token, "content": content}, board_key)
    except Exception:
        pass


@app.get("/api/hive/status")
def get_hive_status():
    return _hive_payload()


@app.get("/api/hive/posts")
def get_hive_posts(limit: int = 50):
    data = _read_json_file(_hive_state_path()) or {}
    base_url = data.get("base_url")
    board_key = data.get("board_key")
    if not base_url or not board_key:
        return {"posts": [], "bbs_url": "", "error": ""}
    if data.get("status") in ("stopped", "done_budget", "done", "error") and not _hive_payload().get("bbs_running"):
        return {"posts": [], "bbs_url": data.get("bbs_url") or "", "error": "", "offline": True}
    try:
        posts = _hive_http_get_json(f"{base_url}/posts?limit={max(1, min(int(limit or 50), 200))}", board_key)
        posts = list(reversed(posts)) if isinstance(posts, list) else []
        return {"posts": posts, "bbs_url": data.get("bbs_url") or f"{base_url}/?key={board_key}", "error": ""}
    except Exception as e:
        msg = str(e)
        if "Connection refused" in msg or "Errno 61" in msg or "timed out" in msg:
            return {"posts": [], "bbs_url": data.get("bbs_url") or "", "error": "", "offline": True}
        return {"posts": [], "bbs_url": data.get("bbs_url") or "", "error": msg}


@app.post("/api/hive/start")
async def start_hive_mode(request: Request):
    data = await request.json()
    objective = str(data.get("objective") or "").strip()
    if not objective:
        return JSONResponse(status_code=400, content={"error": "objective is required"})
    if _hive_payload().get("running"):
        return JSONResponse(status_code=409, content={"error": "hive mode is already running", **_hive_payload()})
    if _goal_proc_alive():
        return JSONResponse(status_code=409, content={"error": "goal mode is already running; stop it before starting hive", **_goal_payload()})

    budget_minutes = max(1, min(float(data.get("budget_minutes") or 30), 24 * 60))
    max_turns = max(1, min(int(data.get("max_turns") or 80), 500))
    worker_count = max(1, min(int(data.get("worker_count") or 1), 6))
    port = int(data.get("port") or _free_port())
    board_key = "hive_" + uuid.uuid4().hex[:12]
    base_url = f"http://127.0.0.1:{port}"
    hive_root = os.path.join(_hive_dir(), "workspace")
    output_dir = os.path.join(hive_root, "outputs")
    os.makedirs(hive_root, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    state_doc = {
        "objective": objective,
        "status": "starting",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "budget_minutes": budget_minutes,
        "max_turns": max_turns,
        "worker_count": worker_count,
        "port": port,
        "base_url": base_url,
        "board_key": board_key,
        "hive_root": hive_root,
        "output_dir": output_dir,
        "bbs_url": f"{base_url}/?key={board_key}",
        "logs": {
            "bbs": _hive_log_path("bbs"),
            "master": _hive_log_path("master"),
            "workers": [_hive_log_path(f"worker_{i}") for i in range(1, worker_count + 1)],
        }
    }
    _write_hive_state(state_doc)

    try:
        bbs_log = open(_hive_log_path("bbs"), "a", encoding="utf-8")
        bbs_proc = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "assets", "agent_bbs.py"), "--cwd", hive_root, "--port", str(port), "--key", board_key],
            cwd=BASE_DIR,
            stdout=bbs_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        hive_process.update({"bbs": bbs_proc, "workers": [], "master": None, "state_path": _hive_state_path(), "started_at": time.time()})
        time.sleep(1.0)

        token = _hive_http_json(f"{base_url}/register", {"name": "hive-seed"}, board_key).get("token")
        state_doc["seed_token"] = token
        _write_hive_state(state_doc)
        first_post = (
            f"任务目标：\n{objective}\n\n"
            f"BBS：{base_url}/readme?key={board_key}\n"
            f"工作目录：{hive_root}\n\n"
            f"产出目录：{output_dir}\n\n"
            f"{HIVE_MASTER_DUTY}\n\n"
            "附加说明：此为最终目标，worker不要接单，先等hive master拆分子任务。"
            "所有交付文件必须写入产出目录，BBS只写进度、分工、阻塞和最终清单。"
        )
        _hive_http_json(f"{base_url}/post", {"token": token, "content": first_post}, board_key)

        workers = []
        for i in range(1, worker_count + 1):
            worker_log = open(_hive_log_path(f"worker_{i}"), "a", encoding="utf-8")
            proc = subprocess.Popen(
                [
                    sys.executable, os.path.join(BASE_DIR, "agentmain.py"),
                    "--reflect", os.path.join(BASE_DIR, "reflect", "agent_team_worker.py"),
                    "--base_url", base_url,
                    "--board_key", board_key,
                    "--name", f"hive-worker-{i}",
                ],
                cwd=hive_root,
                env={**os.environ.copy(), "GA_HIVE_ROOT": hive_root, "GA_HIVE_OUTPUT_DIR": output_dir},
                stdout=worker_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            workers.append(proc)
        hive_process["workers"] = workers

        master_objective = (
            f"{objective}\n\n"
            f"BBS: {base_url}/readme?key={board_key}\n"
            f"BBS_CWD: {hive_root}\n\n"
            f"HIVE_OUTPUT_DIR: {output_dir}\n"
            "所有最终产出、进度文件和交付文件必须写入 HIVE_OUTPUT_DIR；不要写到 A3Agent/temp 或当前项目根目录。\n"
            "在 BBS 发帖请使用 /readme 中给出的 register/post JSON 示例，不要自行猜测 /posts 或 /api/posts。\n\n"
            f"{HIVE_MASTER_DUTY}"
        )
        master_state_path = os.path.join(_hive_dir(), "master_goal_state.json")
        master_state = {
            "objective": master_objective,
            "budget_seconds": int(budget_minutes * 60),
            "start_time": time.time(),
            "turns_used": 0,
            "max_turns": max_turns,
            "status": "running",
            "done_prompt": HIVE_DONE_PROMPT,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "hive": True,
        }
        master_proc = _start_goal_reflect_process(
            master_state,
            master_state_path,
            _hive_log_path("master"),
            cwd=hive_root,
            extra_env={"GA_HIVE_ROOT": hive_root, "GA_HIVE_OUTPUT_DIR": output_dir},
        )
        hive_process["master"] = master_proc
        state_doc.update({
            "status": "running",
            "master_goal_state_path": master_state_path,
            "pids": {
                "bbs": bbs_proc.pid,
                "master": master_proc.pid,
                "workers": [p.pid for p in workers],
            }
        })
        _write_hive_state(state_doc)
        return {"status": "started", **_hive_payload()}
    except Exception as e:
        state_doc["status"] = "error"
        state_doc["error"] = str(e)
        _write_hive_state(state_doc)
        _stop_hive_processes("error")
        return JSONResponse(status_code=500, content={"error": str(e), **_hive_payload()})


@app.post("/api/hive/stop")
async def stop_hive_mode():
    _stop_hive_processes("stopped")
    return {"status": "stopped", **_hive_payload()}


@app.post("/api/hive/extend")
async def extend_hive_mode(request: Request):
    data = await request.json()
    add_minutes = max(0.0, min(float(data.get("minutes") or 0), 24 * 60))
    add_turns = max(0, min(int(data.get("turns") or 0), 500))
    state_data = _read_json_file(_hive_state_path()) or {}
    master_path = state_data.get("master_goal_state_path") or os.path.join(_hive_dir(), "master_goal_state.json")
    master_state = _read_json_file(master_path) or {}
    if not master_state:
        return JSONResponse(status_code=400, content={"error": "master state is not available"})
    if add_minutes:
        master_state["budget_seconds"] = int(float(master_state.get("budget_seconds") or 0) + add_minutes * 60)
        state_data["budget_minutes"] = round(float(state_data.get("budget_minutes") or 0) + add_minutes, 2)
    if add_turns:
        master_state["max_turns"] = int(master_state.get("max_turns") or 0) + add_turns
        state_data["max_turns"] = int(state_data.get("max_turns") or 0) + add_turns
    if master_state.get("status") in ("done_budget", "wrapping_up"):
        master_state["status"] = "running"
        master_state.pop("end_time", None)
        state_data["status"] = "running"
        state_data.pop("end_time", None)
    _write_hive_state(state_data)
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master_state, f, ensure_ascii=False, indent=2)
    _hive_post_system(f"@all [人工控制] 已追加 Hive 预算：+{add_minutes:g} 分钟，+{add_turns} 轮。Master 请重新评估剩余任务并继续/收口。")
    return {"status": "extended", **_hive_payload()}


@app.post("/api/hive/control")
async def control_hive_agent(request: Request):
    data = await request.json()
    action = str(data.get("action") or "").lower().strip()
    target = str(data.get("target") or "all").lower().strip()
    if action not in ("pause", "resume", "stop"):
        return JSONResponse(status_code=400, content={"error": "action must be pause, resume, or stop"})
    targets = _hive_target_procs(target)
    if not targets:
        return JSONResponse(status_code=404, content={"error": f"no running target: {target}"})
    state_data = _read_json_file(_hive_state_path()) or {}
    paused = set(state_data.get("paused_targets") or [])
    changed = []
    sig = None
    if action == "pause":
        sig = signal.SIGSTOP
    elif action == "resume":
        sig = signal.SIGCONT
    for name, proc in targets:
        try:
            if action == "stop":
                _terminate_proc(proc)
                paused.discard(name)
            else:
                os.kill(proc.pid, sig)
                if action == "pause":
                    paused.add(name)
                else:
                    paused.discard(name)
            changed.append(name)
        except Exception:
            pass
    state_data["paused_targets"] = sorted(paused)
    if action == "stop":
        state_data.setdefault("stopped_targets", [])
        state_data["stopped_targets"] = sorted(set(state_data["stopped_targets"]) | set(changed))
    _write_hive_state(state_data)
    label = {"pause": "暂停", "resume": "继续", "stop": "停止"}[action]
    _hive_post_system(f"@all [人工控制] 已{label}：{', '.join(changed) or target}。相关 agent 请按此状态调整，不要绕过人工控制。")
    return {"status": action, "target": target, "changed": changed, **_hive_payload()}


@app.post("/api/hive/post")
async def post_hive_message(request: Request):
    data = await request.json()
    content = str(data.get("content") or "").strip()
    author = str(data.get("author") or "human").strip() or "human"
    if not content:
        return JSONResponse(status_code=400, content={"error": "content is required"})
    state_data = _read_json_file(_hive_state_path()) or {}
    base_url = state_data.get("base_url")
    board_key = state_data.get("board_key")
    if not base_url or not board_key:
        return JSONResponse(status_code=400, content={"error": "hive bbs is not available"})
    try:
        token = state_data.get("human_token")
        if not token or state_data.get("human_author") != author:
            token = _hive_http_json(f"{base_url}/register", {"name": author}, board_key).get("token")
            state_data["human_token"] = token
            state_data["human_author"] = author
            _write_hive_state(state_data)
        result = _hive_http_json(f"{base_url}/post", {"token": token, "content": content}, board_key)
        return {"status": "posted", "post": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/conversation/current")
def get_current_conversation():
    data = _read_current_conversation()
    return {
        "session_id": data.get("session_id"),
        "title": data.get("title"),
        "summary": data.get("summary"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "messages": data.get("messages") or [],
        "path": _current_conversation_path(),
    }


@app.get("/api/conversations")
def list_conversations():
    sessions = []
    for kind, path in _conversation_file_candidates():
        try:
            data = _read_conversation_file(path)
        except Exception as e:
            _debug_log("conversation_list_read_failed", path=path, error=str(e))
            continue
        sessions.append(_conversation_session_payload(data, path=path, current=(kind == "current")))
    sessions.sort(key=lambda item: (0 if item.get("current") else 1, item.get("updated_at") or ""), reverse=False)
    if sessions:
        current = [s for s in sessions if s.get("current")]
        archived = [s for s in sessions if not s.get("current")]
        archived.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
        sessions = current + archived
    return {"sessions": sessions, "root": _conversation_root_dir()}


@app.get("/api/conversations/search")
def search_conversations(q: str = "", mode: str = "auto", limit: int = 30):
    query = str(q or "").strip()
    mode_raw = str(mode or "auto").lower()
    mode = mode_raw if mode_raw in ("auto", "keyword", "semantic") else "auto"
    try:
        limit = max(1, min(int(limit), 100))
    except Exception:
        limit = 30
    if not query:
        return {"query": query, "mode": mode, "results": []}

    results = []
    for kind, path in _conversation_file_candidates():
        try:
            data = _read_conversation_file(path)
        except Exception as e:
            _debug_log("conversation_search_read_failed", path=path, error=str(e))
            continue
        payload = _conversation_session_payload(data, path=path, current=(kind == "current"))
        session_text = "\n".join([
            str(payload.get("title") or ""),
            str(payload.get("summary") or ""),
            str(payload.get("last_preview") or ""),
        ])
        best_score = _conversation_search_score(query, session_text, mode)
        matches = []
        for idx, msg in enumerate(data.get("messages") or []):
            content = _message_text(msg.get("content") if isinstance(msg, dict) else msg)
            msg_score = _conversation_search_score(query, content, mode)
            if msg_score <= 0:
                continue
            best_score = max(best_score, msg_score)
            matches.append({
                "message_index": idx,
                "message_id": msg.get("id", "") if isinstance(msg, dict) else "",
                "role": msg.get("role", "") if isinstance(msg, dict) else "",
                "timestamp": msg.get("timestamp") or msg.get("created_at") or "" if isinstance(msg, dict) else "",
                "snippet": _conversation_snippet(content, query),
                "score": round(float(msg_score), 4),
            })
        if best_score <= 0:
            continue
        matches.sort(key=lambda x: x.get("score", 0), reverse=True)
        payload["score"] = round(float(best_score), 4)
        payload["matches"] = matches[:5]
        results.append(payload)

    results.sort(key=lambda item: (item.get("score", 0), item.get("updated_at") or ""), reverse=True)
    return {"query": query, "mode": mode, "results": results[:limit]}


@app.get("/api/conversations/{session_id}")
def get_conversation(session_id: str):
    kind, path, data = _find_conversation_file(session_id)
    if not data:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    payload = _conversation_session_payload(data, path=path, current=(kind == "current"))
    payload["messages"] = data.get("messages") or []
    return payload


@app.post("/api/conversations/{session_id}/restore")
async def restore_conversation(session_id: str):
    kind, path, data = _find_conversation_file(session_id)
    if not data:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    state.cancel_runs(None)
    archived_current_path = ""
    current = _read_current_conversation()
    if current.get("session_id") != data.get("session_id") and (current.get("messages") or []):
        _, archived_current_path = _archive_current_conversation("restore_other_conversation")
    restored = _normalize_conversation_doc(dict(data))
    _write_current_conversation(restored)
    _sync_agent_context_from_conversation(restored)
    return {
        "status": "restored",
        "session_id": restored.get("session_id"),
        "archived_current_path": archived_current_path,
        "source_path": path,
    }


@app.post("/api/conversations/{session_id}/rename")
async def rename_conversation(session_id: str, request: Request):
    kind, path, data = _find_conversation_file(session_id)
    if not data:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    body = await request.json()
    title = str(body.get("title") or "").strip()
    if not title:
        return JSONResponse({"error": "title required"}, status_code=400)
    data["title"] = title[:80]
    data["title_locked"] = True
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_conversation_file(kind, path, data)
    return {"status": "renamed", "session": _conversation_session_payload(data, path=path, current=(kind == "current"))}


@app.get("/api/conversations/{session_id}/export")
def export_conversation(session_id: str):
    kind, path, data = _find_conversation_file(session_id)
    if not data:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    export_dir = os.path.join(_conversation_root_dir(), "exports")
    os.makedirs(export_dir, exist_ok=True)
    safe_title = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+", "_", str(data.get("title") or "session")).strip("_")[:48] or "session"
    out_path = os.path.join(export_dir, f"{safe_title}-{data.get('session_id')}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_conversation_markdown(data))
    return FileResponse(out_path, media_type="text/markdown", filename=os.path.basename(out_path))


@app.get("/api/memory/list")
def list_memory_files():
    mem_dir = _user_memory_dir()
    _ensure_default_user_memory()
    if not os.path.isdir(mem_dir):
        return {"root": mem_dir, "files": []}
    out = []
    for root, dirs, files in os.walk(mem_dir):
        dirs[:] = [d for d in dirs if isinstance(d, str) and not d.startswith(".") and d != "__pycache__"]
        for name in files:
            if not isinstance(name, str) or name.startswith("."):
                continue
            abs_path = os.path.abspath(os.path.join(root, name))
            if not abs_path.startswith(mem_dir + os.sep):
                continue
            rel = os.path.relpath(abs_path, mem_dir).replace(os.sep, "/")
            try:
                stat = os.stat(abs_path)
                size = int(stat.st_size)
                mtime = int(stat.st_mtime)
            except Exception:
                size = 0
                mtime = 0
            out.append({
                "name": rel,
                "size": size,
                "mtime": mtime,
            })
    out.sort(key=lambda x: x["name"])
    return {"root": mem_dir, "files": out}

@app.get("/api/memory/read")
def read_memory_file(name: str):
    safe = _safe_rel_path(name)
    if not safe:
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    mem_dir = _user_memory_dir()
    _ensure_default_user_memory()
    path = os.path.abspath(os.path.join(mem_dir, safe))
    if not path.startswith(mem_dir + os.sep):
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "not found"})
    raw = _read_text(path)
    return {
        "name": safe,
        "path": path,
        "content": raw,
    }

@app.get("/api/stream")
async def stream(request: Request):
    async def event_generator():
        q = stream_manager.add_queue()
        last_heartbeat = time.monotonic()
        _debug_log("stream_connect", client=str(id(q)), queues=len(stream_manager.queues))
        try:
            while True:
                if await request.is_disconnected():
                    break
                # Poll the queue (non-blocking in thread, blocking in async)
                # Since queue.get() is blocking, we use a loop with small sleep to be async friendly
                try:
                    # Get all available messages
                    while not q.empty():
                        msg = q.get_nowait()
                        try:
                            parsed = json.loads(msg)
                            _debug_log(
                                "stream_emit",
                                client=str(id(q)),
                                type=parsed.get("type"),
                                state=parsed.get("state"),
                                run_id=parsed.get("run_id"),
                                content_len=len(str(parsed.get("content", ""))) if "content" in parsed else None,
                            )
                        except Exception:
                            _debug_log("stream_emit", client=str(id(q)), raw_preview=str(msg)[:120])
                        yield f"data: {msg}\n\n"
                        last_heartbeat = time.monotonic()
                    if time.monotonic() - last_heartbeat >= 15:
                        heartbeat = json.dumps({"type": "heartbeat", "ts": time.time()}, ensure_ascii=False)
                        yield f"data: {heartbeat}\n\n"
                        last_heartbeat = time.monotonic()
                    await asyncio.sleep(0.1)
                except Exception:
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            stream_manager.remove_queue(q)
            _debug_log("stream_disconnect", client=str(id(q)), queues=len(stream_manager.queues))
            print("Client disconnected from stream")
        finally:
            stream_manager.remove_queue(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/chat")
async def chat(request: Request):
    if state.agent_init_error:
        return {"error": f"Agent init failed: {state.agent_init_error}"}
    t0 = time.time()
    while state.stopping and time.time() - t0 < 5:
        await asyncio.sleep(0.05)
    state.clear_human_input()
    data = await request.json()
    prompt = data.get("prompt")
    request_id = data.get("request_id")
    raw_images = data.get("images") or []
    image_paths = []
    if isinstance(raw_images, list):
        for item in raw_images[:12]:
            path = item.get("path") if isinstance(item, dict) else item
            if not isinstance(path, str) or not path:
                continue
            ap = os.path.abspath(path)
            if os.path.isfile(ap):
                image_paths.append(ap)
    if not prompt:
        return {"error": "No prompt provided"}
    prompt_for_display = prompt
    if image_paths:
        prompt_for_display = prompt.rstrip() + "\n\n" + "\n".join(f"![{os.path.basename(p)}]({p})" for p in image_paths)
    _debug_log("chat_received", prompt_len=len(prompt), image_count=len(image_paths), request_id=request_id, stopping=state.stopping, is_running=getattr(state.agent, "is_running", False))
    
    # Update activity time
    state.last_activity_time = time.time()
    
    # Put task into agent's queue
    display_queue = state.agent.put_task(prompt, source="user", images=image_paths)
    run_id, cancel_event = state.new_run()
    _debug_log("chat_queued", run_id=run_id, request_id=request_id, prompt_len=len(prompt), stopping=state.stopping, is_running=getattr(state.agent, "is_running", False))
    
    # Start background task to broadcast output
    # Note: We pass prompt_text=prompt so it gets broadcasted back to all clients (including sender)
    # This simplifies frontend logic (just listen to stream)
    threading.Thread(target=process_agent_output, args=(display_queue, "user", prompt_for_display, run_id, cancel_event, request_id), daemon=True).start()
    
    return {"status": "queued", "run_id": run_id, "request_id": request_id}

@app.post("/api/intervene")
async def intervene(request: Request):
    if state.agent_init_error:
        return {"error": f"Agent init failed: {state.agent_init_error}"}
    data = await request.json()
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse(status_code=400, content={"error": "prompt required"})
    queued = state.agent.add_intervention(prompt)
    state.last_activity_time = time.time()
    _debug_log("intervene_queued", prompt_len=len(prompt), queued=queued)
    stream_manager.broadcast(json.dumps({
        "type": "system",
        "content": f"已加入引导队列，将在下一次回合切换时生效：{prompt}",
        "source": "intervention",
        "timestamp": time.strftime('%H:%M:%S')
    }, ensure_ascii=False))
    return {"status": "queued", "queued": queued}

@app.post("/api/control")
async def control(request: Request):
    data = await request.json()
    action = data.get("action")
    if state.agent_init_error and action != "reload_agent":
        return {"error": f"Agent init failed: {state.agent_init_error}"}
    
    # Always update activity time on user interaction
    state.last_activity_time = time.time()
    
    if action == "stop":
        state.stopping = True
        _debug_log("stop_received", run_ids=data.get("run_ids"), is_running=getattr(state.agent, "is_running", False))
        try:
            run_ids = data.get("run_ids")
            if isinstance(run_ids, list) and run_ids:
                canceled = state.cancel_runs(run_ids)
            else:
                canceled = state.cancel_runs(None)
            state.agent.abort()
            t0 = time.time()
            while time.time() - t0 < 1.5:
                if not getattr(state.agent, "is_running", False):
                    break
                time.sleep(0.05)
            if getattr(state.agent, "is_running", False):
                old = state.agent
                state.agent, state.agent_init_error = init_agent()
                try:
                    old.abort()
                except Exception:
                    pass
                _debug_log("stop_forced_restart", canceled_run_ids=canceled, agent_init_error=state.agent_init_error)
                return {"status": "stopped", "forced_restart": True, "agent_init_error": state.agent_init_error, "canceled_run_ids": canceled}
            _debug_log("stop_completed", forced_restart=False, canceled_run_ids=canceled)
            return {"status": "stopped", "forced_restart": False, "canceled_run_ids": canceled}
        finally:
            state.stopping = False
    elif action == "switch_llm":
        idx = data.get("index")
        if idx is not None:
            try:
                state.agent.next_llm(int(idx))
            except Exception as e:
                return {"error": str(e)}
        else:
            state.agent.next_llm()
        return {"status": "switched", "llm_name": state.agent.get_llm_name()}
    elif action in ("new_conversation", "clear_history"):
        state.cancel_runs(None)
        conversation, archived_path = _archive_current_conversation("new_conversation")
        if hasattr(state.agent, "clear_history"):
            state.agent.clear_history()
        else:
            state.agent.history = []
            try:
                if state.agent.llmclient and hasattr(state.agent.llmclient, "backend"):
                    state.agent.llmclient.backend.history = []
            except Exception:
                pass
        return {
            "status": "created",
            "session_id": conversation.get("session_id"),
            "archived_path": archived_path,
        }
    elif action == "toggle_autonomous":
        state.autonomous_enabled = not state.autonomous_enabled
        return {"status": "toggled", "enabled": state.autonomous_enabled}
    elif action == "trigger_autonomous":
        # Force trigger by setting time back enough to trigger immediately
        state.last_activity_time = time.time() - (state.autonomous_threshold + 10)
        return {"status": "triggered"}
    elif action == "set_autonomous_threshold":
        threshold = data.get("value")
        if threshold:
            state.autonomous_threshold = int(threshold)
        return {"status": "updated", "threshold": state.autonomous_threshold}
    elif action == "inject_sys_prompt":
        if state.agent.llmclient:
            state.agent.llmclient.last_tools = ''
        return {"status": "injected"}
    elif action == "reload_agent":
        _reload_agent_state()
        return {"status": "reloaded", "agent_init_error": state.agent_init_error}
    elif action == "toggle_scheduler":
        state.scheduler_enabled = not state.scheduler_enabled
        return {"status": "toggled", "enabled": state.scheduler_enabled}
    elif action == "set_scheduler_interval":
        val = data.get("value")
        if val:
            state.scheduler_interval = int(val)
        return {"status": "updated", "scheduler_interval": state.scheduler_interval}
    
    return {"error": "Unknown action"}

@app.get("/api/config/mykey")
def get_mykey():
    base = get_user_data_dir()
    path = resolve_mykey_path(base, prefer_existing=True)
    return {"exists": bool(path and os.path.exists(path)), "path": str(path) if path else ""}

@app.post("/api/config/mykey")
async def save_mykey(request: Request):
    data = await request.json()
    content = data.get("content")
    if not isinstance(content, str):
        return JSONResponse(status_code=400, content={"error": "content must be string"})
    base = get_user_data_dir()
    path = resolve_mykey_path(base, prefer_existing=False)
    _write_text(path, content)
    return {"status": "saved"}

@app.get("/api/llm_configs")
def list_llm_configs():
    base = get_user_data_dir()
    path = resolve_mykey_path(base, prefer_existing=True)
    module = _load_mykey_module_from_path(path)
    configs = _extract_llm_configs_from_module(module)
    return {"configs": configs}

@app.post("/api/llm_configs/test")
async def test_llm_config(request: Request):
    data = await request.json()
    cid = data.get("id")
    ctp = data.get("type")
    apibase = data.get("apibase")
    model = data.get("model")
    apikey = data.get("apikey")

    if ctp not in ("oai", "claude"):
        return {"ok": False, "error": "unsupported type"}

    if isinstance(apibase, str):
        apibase = _normalize_api_base(apibase)
    else:
        apibase = ""

    if isinstance(model, str):
        model = model.strip()
    else:
        model = ""

    if isinstance(apikey, str):
        apikey = apikey.strip()
    else:
        apikey = ""

    if cid and not apikey:
        try:
            base = get_user_data_dir()
            path = resolve_mykey_path(base, prefer_existing=True)
            module = _load_mykey_module_from_path(path)
            v = module.get(cid)
            if isinstance(v, dict):
                k = v.get("apikey")
                if isinstance(k, str) and k.strip():
                    apikey = k.strip()
        except Exception:
            pass

    if not apibase:
        return {"ok": False, "error": "apibase required"}
    if not model:
        return {"ok": False, "error": "model required"}
    if not apikey:
        return {"ok": False, "error": "apikey required"}

    try:
        import requests
    except Exception:
        return {"ok": False, "error": "requests not available"}

    try:
        if ctp == "claude":
            url = _auto_make_url(apibase, "messages")
            headers = {"x-api-key": apikey, "Content-Type": "application/json", "anthropic-version": "2023-06-01", "Accept-Encoding": "identity"}
            payload = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
        else:
            url = _auto_make_url(apibase, "chat/completions")
            auth = apikey if apikey.lower().startswith("bearer ") else f"Bearer {apikey}"
            headers = {"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json", "Accept-Encoding": "identity"}
            payload = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1, "temperature": 0}

        r = requests.post(url, headers=headers, json=payload, timeout=(5, 15))
        if r.status_code >= 400:
            body = (r.text or "").strip()
            body = body[:600]
            return {"ok": False, "url": url, "status_code": r.status_code, "error": body or f"HTTP {r.status_code}"}
        return {"ok": True, "url": url, "status_code": r.status_code}
    except Exception as e:
        msg = str(e)
        if "decompressing data" in msg or "ContentDecodingError" in type(e).__name__:
            msg = "上游 API 返回的压缩响应不完整。已改为请求未压缩响应，请重试；如果仍出现，多半是 API 网关/代理截断响应。"
        return {"ok": False, "url": url if "url" in locals() else "", "error": msg}

@app.post("/api/llm_configs/upsert")
async def upsert_llm_config(request: Request):
    data = await request.json()
    cid = data.get("id")
    ctp = data.get("type")
    apibase = data.get("apibase")
    model = data.get("model")
    apikey = data.get("apikey")
    cookie = data.get("cookie")

    if ctp not in ("oai", "claude", "sider"):
        return JSONResponse(status_code=400, content={"error": "invalid type"})

    try:
        base = get_user_data_dir()
        path = resolve_mykey_path(base, prefer_existing=False)
        module = _load_mykey_module_from_path(path)
        order, values = _read_mykey_simple_assignments(module)
        existing_ids = set()
        for k in order:
            v = values.get(k)
            if k == "sider_cookie" and isinstance(v, str):
                existing_ids.add(k)
            elif isinstance(v, dict) and all(x in v for x in ("apikey", "apibase", "model")):
                existing_ids.add(k)

        if ctp == "sider":
            if not isinstance(cookie, str) or not cookie.strip():
                return JSONResponse(status_code=400, content={"error": "cookie required"})
            values["sider_cookie"] = cookie
            if "sider_cookie" not in order:
                order.append("sider_cookie")
            content = _render_mykey_py(order, values)
            _write_text(path, content)
            err = _reload_agent_state()
            return {"status": "saved", "id": "sider_cookie", "agent_init_error": err, "configs": _extract_llm_configs_from_module(values), "llm_list": state.agent.list_llms() if not err else []}

        if not isinstance(apibase, str) or not isinstance(model, str):
            return JSONResponse(status_code=400, content={"error": "apibase/model required"})
        apibase = _normalize_api_base(apibase)

        if cid:
            if cid not in existing_ids:
                return JSONResponse(status_code=404, content={"error": "unknown id"})
            v = values.get(cid)
            if not isinstance(v, dict) or not all(x in v for x in ("apikey", "apibase", "model")):
                return JSONResponse(status_code=400, content={"error": "id is not a model config"})
            v["apibase"] = apibase
            v["model"] = model
            v["type"] = ctp
            if isinstance(apikey, str) and apikey.strip():
                v["apikey"] = apikey
        else:
            if not isinstance(apikey, str) or not apikey.strip():
                return JSONResponse(status_code=400, content={"error": "apikey required for new config"})
            prefix = "claude_config" if ctp == "claude" else "oai_config"
            cid = _alloc_config_name(existing_ids, prefix)
            values[cid] = {
                "type": ctp,
                "apikey": apikey,
                "apibase": apibase,
                "model": model,
            }
            order.append(cid)

        content = _render_mykey_py(order, values)
        _write_text(path, content)
        err = _reload_agent_state()
        return {"status": "saved", "id": cid, "agent_init_error": err, "configs": _extract_llm_configs_from_module(values), "llm_list": state.agent.list_llms() if not err else []}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/llm_configs/delete")
async def delete_llm_config(request: Request):
    data = await request.json()
    cid = data.get("id")
    if not isinstance(cid, str) or not cid:
        return JSONResponse(status_code=400, content={"error": "id required"})
    base = get_user_data_dir()
    path = resolve_mykey_path(base, prefer_existing=False)
    module = _load_mykey_module_from_path(path)
    order, values = _read_mykey_simple_assignments(module)
    if cid in values:
        del values[cid]
    order = [k for k in order if k != cid]
    content = _render_mykey_py(order, values)
    _write_text(path, content)
    err = _reload_agent_state()
    return {"status": "deleted", "agent_init_error": err, "configs": _extract_llm_configs_from_module(values), "llm_list": state.agent.list_llms() if not err else []}


@app.get("/api/communication_configs")
def list_communication_configs():
    base = get_user_data_dir()
    path = resolve_mykey_path(base, prefer_existing=True)
    values = _load_mykey_module_from_path(path)
    process_text = _process_snapshot()
    tools = [
        _communication_tool_status(tool_id, spec, values, process_text)
        for tool_id, spec in COMMUNICATION_TOOLS.items()
    ]
    return {"tools": tools, "path": str(path) if path else ""}


@app.post("/api/communication_configs/upsert")
async def upsert_communication_config(request: Request):
    data = await request.json()
    tool_id = str(data.get("id") or "").strip()
    spec = COMMUNICATION_TOOLS.get(tool_id)
    if not spec:
        return JSONResponse(status_code=400, content={"error": "unknown communication tool"})

    app_id = data.get("app_id")
    secret = data.get("secret")
    allowed_users = data.get("allowed_users", [])
    if not isinstance(app_id, str):
        return JSONResponse(status_code=400, content={"error": "app_id must be string"})
    if secret is not None and not isinstance(secret, str):
        return JSONResponse(status_code=400, content={"error": "secret must be string"})
    if isinstance(allowed_users, str):
        allowed_users = [x.strip() for x in re.split(r"[\n,，]+", allowed_users) if x.strip()]
    elif isinstance(allowed_users, list):
        allowed_users = [str(x).strip() for x in allowed_users if str(x).strip()]
    else:
        return JSONResponse(status_code=400, content={"error": "allowed_users must be list or string"})

    base = get_user_data_dir()
    path = resolve_mykey_path(base, prefer_existing=False)
    module = _load_mykey_module_from_path(path)
    order, values = _read_mykey_simple_assignments(module)
    for key in (spec["id_key"], spec["secret_key"], spec.get("allowed_key", "")):
        if key and key not in order:
            order.append(key)

    values[spec["id_key"]] = app_id.strip()
    if secret is not None and secret.strip():
        values[spec["secret_key"]] = secret.strip()
    elif spec["secret_key"] not in values:
        values[spec["secret_key"]] = ""
    if spec.get("allowed_key"):
        values[spec["allowed_key"]] = allowed_users

    content = _render_mykey_py(order, values)
    _write_text(path, content)
    process_text = _process_snapshot()
    tool = _communication_tool_status(tool_id, spec, values, process_text)
    return {"status": "saved", "tool": tool, "path": str(path)}


@app.post("/api/communication_configs/action")
async def communication_config_action(request: Request):
    data = await request.json()
    tool_id = str(data.get("id") or "").strip()
    action = str(data.get("action") or "").strip()
    spec = COMMUNICATION_TOOLS.get(tool_id)
    if not spec:
        return JSONResponse(status_code=400, content={"error": "unknown communication tool"})
    if action not in ("test", "start", "stop"):
        return JSONResponse(status_code=400, content={"error": "unknown action"})

    if action == "start":
        path = _communication_script_path(spec)
        if not os.path.exists(path):
            return JSONResponse(status_code=404, content={"error": f"script not found: {path}"})
        process_text = _process_snapshot()
        if not any(k in process_text for k in spec.get("process_keywords", ())):
            log_path = _communication_log_path(tool_id)
            python_path = _communication_python_path()
            with open(log_path, "ab") as log_file:
                subprocess.Popen(
                    [python_path, "-u", path],
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            time.sleep(1)
    elif action == "stop":
        script = spec.get("script", "")
        if script:
            try:
                subprocess.run(["pkill", "-f", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            except Exception:
                pass
            time.sleep(0.5)

    base = get_user_data_dir()
    path = resolve_mykey_path(base, prefer_existing=True)
    values = _load_mykey_module_from_path(path)
    process_text = _process_snapshot()
    tool = _communication_tool_status(tool_id, spec, values, process_text)
    return {"status": "ok", "action": action, "tool": tool, "python": _communication_python_path()}

@app.get("/api/todo")
def get_todo():
    path, migrated_from = _ensure_todo_file()
    if os.path.exists(path):
        return {"exists": True, "content": _read_text(path), "path": path, "migrated_from": migrated_from}
    return {"exists": False, "content": "", "path": path, "migrated_from": migrated_from}

@app.post("/api/todo")
async def save_todo(request: Request):
    data = await request.json()
    content = data.get("content")
    if not isinstance(content, str):
        return JSONResponse(status_code=400, content={"error": "content must be string"})
    path, migrated_from = _ensure_todo_file()
    _write_text(path, content)
    return {"status": "saved", "path": path, "migrated_from": migrated_from}

@app.get("/api/sop/list")
def list_sops():
    mem_dir = _sop_memory_dir()
    if not os.path.isdir(mem_dir):
        return {"files": []}
    out = []
    mem_dir_abs = os.path.abspath(mem_dir)
    for root, dirs, files in os.walk(mem_dir_abs):
        dirs[:] = [d for d in dirs if isinstance(d, str) and d not in ("__pycache__",) and not d.startswith(".")]
        for f in files:
            if not isinstance(f, str) or not f.endswith(".md") or f.startswith("."):
                continue
            abs_path = os.path.abspath(os.path.join(root, f))
            if not abs_path.startswith(mem_dir_abs + os.sep):
                continue
            rel = os.path.relpath(abs_path, mem_dir_abs).replace(os.sep, "/")
            safe = _safe_rel_path(rel)
            if safe and safe.endswith(".md"):
                out.append(safe)
    out.sort()
    return {"files": out}

@app.get("/api/sop/read")
def read_sop(name: str):
    safe = _safe_rel_path(name)
    if not safe or not safe.endswith(".md"):
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    mem_dir = _sop_memory_dir()
    mem_dir_abs = os.path.abspath(mem_dir)
    path = os.path.abspath(os.path.join(mem_dir_abs, safe))
    if not path.startswith(mem_dir_abs + os.sep):
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "not found"})
    return {"content": _read_text(path)}

@app.post("/api/sop/write")
async def write_sop(request: Request):
    data = await request.json()
    name = data.get("name")
    content = data.get("content")
    safe = _safe_rel_path(name)
    if not safe or not safe.endswith(".md"):
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    if not isinstance(content, str):
        return JSONResponse(status_code=400, content={"error": "content must be string"})
    mem_dir = _sop_memory_dir()
    mem_dir_abs = os.path.abspath(mem_dir)
    path = os.path.abspath(os.path.join(mem_dir_abs, safe))
    if not path.startswith(mem_dir_abs + os.sep):
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    _write_text(path, content)
    return {"status": "saved"}

@app.get("/api/schedule/list")
def list_schedule():
    base = get_user_data_dir()
    result = {}
    for bucket in ("pending", "running", "done"):
        d = os.path.join(base, "sche_tasks", bucket)
        os.makedirs(d, exist_ok=True)
        files = [f for f in os.listdir(d) if f.endswith(".md") and _safe_name(f)]
        files.sort()
        result[bucket] = files
    return result

@app.get("/api/schedule/read")
def read_schedule(bucket: str, name: str):
    if bucket not in ("pending", "running", "done"):
        return JSONResponse(status_code=400, content={"error": "invalid bucket"})
    safe = _safe_name(name)
    if not safe or not safe.endswith(".md"):
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    base = get_user_data_dir()
    path = os.path.join(base, "sche_tasks", bucket, safe)
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "not found"})
    return {"content": _read_text(path)}

@app.post("/api/schedule/write")
async def write_schedule(request: Request):
    data = await request.json()
    bucket = data.get("bucket")
    name = data.get("name")
    content = data.get("content")
    if bucket not in ("pending", "running", "done"):
        return JSONResponse(status_code=400, content={"error": "invalid bucket"})
    safe = _safe_name(name)
    if not safe or not safe.endswith(".md"):
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    if not isinstance(content, str):
        return JSONResponse(status_code=400, content={"error": "content must be string"})
    base = get_user_data_dir()
    path = os.path.join(base, "sche_tasks", bucket, safe)
    _write_text(path, content)
    return {"status": "saved"}

@app.post("/api/schedule/delete")
async def delete_schedule(request: Request):
    data = await request.json()
    bucket = data.get("bucket")
    name = data.get("name")
    if bucket not in ("pending", "running", "done"):
        return JSONResponse(status_code=400, content={"error": "invalid bucket"})
    safe = _safe_name(name)
    if not safe or not safe.endswith(".md"):
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    base = get_user_data_dir()
    path = os.path.join(base, "sche_tasks", bucket, safe)
    try:
        os.remove(path)
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    return {"status": "deleted"}

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

DESKTOP_PET_LEGACY_PREVIEW = resource_path("frontends", "pet.gif")


def _desktop_pet_config_path():
    return os.path.join(_get_app_data_dir(), "desktop_pet.json")


def _sanitize_desktop_pet_config(data):
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

    allowed_positions = {"right-bottom", "right-top", "left-bottom", "left-top", "center", "custom"}
    if cfg.get("position") not in allowed_positions:
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
    skin_name = cfg.get("skin_name") or DESKTOP_PET_DEFAULT_CONFIG["skin_name"]
    if skin_name != "legacy-pet":
        skin_dir = os.path.join(resource_path("frontends", "skins"), str(skin_name))
        if not os.path.isdir(skin_dir):
            skin_name = DESKTOP_PET_DEFAULT_CONFIG["skin_name"]
    cfg["skin_name"] = skin_name
    return cfg


def _read_desktop_pet_config():
    path = _desktop_pet_config_path()
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return _sanitize_desktop_pet_config(json.load(f))
    except Exception:
        pass
    return dict(DESKTOP_PET_DEFAULT_CONFIG)


def _write_desktop_pet_config(config):
    cfg = _sanitize_desktop_pet_config(config)
    path = _desktop_pet_config_path()
    _create_user_backup_safe("before-desktop-pet")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


def _desktop_pet_skins_dir():
    return resource_path("frontends", "skins")


def _desktop_pet_skin_list():
    skins_dir = _desktop_pet_skins_dir()
    result = [{
        "name": "legacy-pet",
        "label": "默认桌宠",
        "description": "当前内置 pet.gif 桌宠",
        "style": "legacy",
        "preview_url": "/api/desktop_pet/skin_preview?name=legacy-pet",
    }]
    if not os.path.isdir(skins_dir):
        return result
    for name in sorted(os.listdir(skins_dir)):
        skin_dir = os.path.join(skins_dir, name)
        skin_json = os.path.join(skin_dir, "skin.json")
        if not os.path.isdir(skin_dir) or not os.path.isfile(skin_json):
            continue
        try:
            with open(skin_json, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            meta = {}
        result.append({
            "name": name,
            "label": meta.get("name") or name,
            "description": meta.get("description") or "",
            "style": meta.get("style") or meta.get("format") or "",
            "preview_url": f"/api/desktop_pet/skin_preview?name={name}",
        })
    return result


def _desktop_pet_skin_preview_path(name):
    name = os.path.basename(str(name or ""))
    if name == "legacy-pet":
        return DESKTOP_PET_LEGACY_PREVIEW
    skin_dir = os.path.join(_desktop_pet_skins_dir(), name)
    skin_json = os.path.join(skin_dir, "skin.json")
    if not os.path.isfile(skin_json):
        return None
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with open(skin_json, "r", encoding="utf-8") as f:
            meta = json.load(f)
        animations = meta.get("animations") or {}
        if not animations:
            return None
        anim_name = "idle" if "idle" in animations else next(iter(animations))
        anim = animations.get(anim_name) or {}
        asset = os.path.join(skin_dir, anim.get("file") or "")
        if not os.path.isfile(asset):
            return None
        img = Image.open(asset).convert("RGBA")
        if str(meta.get("format") or "").lower() == "gif" or asset.lower().endswith(".gif"):
            return asset
        sprite = anim.get("sprite") or {}
        fw = int(sprite.get("frameWidth") or img.width)
        fh = int(sprite.get("frameHeight") or img.height)
        start = int(sprite.get("startFrame") or 0)
        cols = max(1, int(sprite.get("columns") or 1))
        row = start // cols
        col = start % cols
        box = (col * fw, row * fh, col * fw + fw, row * fh + fh)
        frame = img.crop(box)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
        preview = os.path.join(_get_app_data_dir(), f"desktop_pet_preview_{safe_name}.png")
        os.makedirs(os.path.dirname(preview), exist_ok=True)
        frame.save(preview, format="PNG")
        return preview
    except Exception:
        return None


def _delete_desktop_pet_skin(name):
    safe_name = os.path.basename(str(name or ""))
    if not safe_name or safe_name == "legacy-pet":
        return False, "内置桌宠不能删除"
    skin_dir = os.path.abspath(os.path.join(_desktop_pet_skins_dir(), safe_name))
    skins_root = os.path.abspath(_desktop_pet_skins_dir())
    if not (skin_dir == skins_root or skin_dir.startswith(skins_root + os.sep)):
        return False, "无效的桌宠名称"
    if not os.path.isdir(skin_dir):
        return False, "桌宠形象不存在"
    skin_json = os.path.join(skin_dir, "skin.json")
    if not os.path.isfile(skin_json):
        return False, "不是可删除的桌宠皮肤目录"
    _create_user_backup_safe("before-delete-desktop-pet-skin")
    shutil.rmtree(skin_dir)

    cfg = _read_desktop_pet_config()
    if cfg.get("skin_name") == safe_name:
        cfg["skin_name"] = DESKTOP_PET_DEFAULT_CONFIG["skin_name"]
        cfg = _write_desktop_pet_config(cfg)
    return True, cfg


@app.get("/api/desktop_pet/config")
def get_desktop_pet_config():
    return {
        "config": _read_desktop_pet_config(),
        "path": _desktop_pet_config_path(),
    }


@app.post("/api/desktop_pet/config")
async def save_desktop_pet_config(request: Request):
    data = await request.json()
    cfg = _write_desktop_pet_config(data.get("config") if isinstance(data, dict) and "config" in data else data)
    return {
        "status": "saved",
        "config": cfg,
        "path": _desktop_pet_config_path(),
    }


@app.get("/api/desktop_pet/skins")
def get_desktop_pet_skins():
    return {
        "skins": _desktop_pet_skin_list(),
    }


@app.post("/api/desktop_pet/skins/delete")
async def delete_desktop_pet_skin(request: Request):
    data = await request.json()
    ok, result = _delete_desktop_pet_skin(data.get("name") if isinstance(data, dict) else "")
    if not ok:
        return JSONResponse(status_code=400, content={"error": result})
    return {
        "status": "deleted",
        "config": result,
        "skins": _desktop_pet_skin_list(),
    }


@app.get("/api/desktop_pet/skin_preview")
def get_desktop_pet_skin_preview(name: str):
    path = _desktop_pet_skin_preview_path(name)
    if not path or not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "not found"})
    media_type = "image/gif" if str(path).lower().endswith(".gif") else "image/png"
    return FileResponse(path, media_type=media_type)

# Mount the fixed frontend for the decoupled Web runtime. The frontend only
# talks to /api/*, so backend developers can keep replacing Python/SOP files
# without changing static assets.
frontend_dir = resolve_frontend_dir()
if frontend_dir:
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    print(f"Frontend serving enabled: {frontend_dir}")
else:
    print("Frontend directory not found; API-only mode")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
