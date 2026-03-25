import os
import sys
import threading
import json
import time
import asyncio
import queue
import traceback
import shutil
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

BASE_DIR = os.environ.get("GA_BASE_DIR") or os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)


def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

def resolve_frontend_dir():
    env_dir = os.environ.get("GA_FRONTEND_DIR")
    if env_dir and os.path.exists(os.path.join(env_dir, "index.html")):
        return env_dir
    candidates = [
        os.path.join(BASE_DIR, "frontend"),
        os.path.join(BASE_DIR, "..", "frontend"),
        os.path.join(BASE_DIR, "..", "..", "frontend"),
        os.path.join(BASE_DIR, "..", "..", "..", "frontend"),
    ]
    exe_path = os.path.abspath(sys.executable)
    candidates.append(os.path.join(os.path.dirname(exe_path), "..", "Resources", "frontend"))
    for path in candidates:
        p = os.path.abspath(path)
        if os.path.exists(os.path.join(p, "index.html")):
            return p
    return None

app = FastAPI()
API_LOG = "/tmp/generic-agent-api.log"

def _ensure_default_mykey(base):
    try:
        base = os.path.abspath(base)
        dst = os.path.join(base, "mykey.json")
        if os.path.exists(dst):
            return
        data = {}
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        return

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
    app_name = os.environ.get("GA_APP_NAME") or "GenericAgent"
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
        root = _normalize_workspace_root(app.current_workspace)
        _try_mkdir(root)
        os.environ.setdefault("GA_WORKSPACE_ROOT", root)
        return root

    root = _normalize_workspace_root(os.environ.get("GA_WORKSPACE_ROOT"))
    if isinstance(root, str) and root:
        _try_mkdir(root)
        return root

    root = _normalize_workspace_root(os.environ.get("GA_USER_DATA_DIR"))
    if isinstance(root, str) and root:
        _try_mkdir(root)
        os.environ.setdefault("GA_WORKSPACE_ROOT", root)
        return root

    root = _default_workspace_dir()
    os.environ.setdefault("GA_WORKSPACE_ROOT", root)
    return root

def get_user_data_dir():
    root = get_workspace_root_dir()
    cfg = _workspace_config_dir(root)
    os.environ["GA_WORKSPACE_ROOT"] = root
    os.environ["GA_USER_DATA_DIR"] = cfg
    return cfg

def _get_app_data_dir():
    root = os.environ.get("GA_APP_DATA_DIR")
    if isinstance(root, str) and root:
        os.makedirs(root, exist_ok=True)
        return root
    return _default_app_root_dir()

def _workspace_history_path():
    return os.path.join(_get_app_data_dir(), "workspace_history.json")

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
        candidates.append(get_resource_path("memory"))
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

def _ensure_default_sops(base):
    try:
        base = os.path.abspath(base)
        dest_root = os.path.join(base, "memory")
        os.makedirs(dest_root, exist_ok=True)
        src_root = _find_sop_src_root()
        if not src_root:
            return
        for root, dirs, files in os.walk(src_root):
            dirs[:] = [d for d in dirs if isinstance(d, str) and d not in ("__pycache__",) and not d.startswith(".")]
            rel = os.path.relpath(root, src_root)
            dest_dir = dest_root if rel == "." else os.path.join(dest_root, rel)
            os.makedirs(dest_dir, exist_ok=True)
            for f in files:
                if not isinstance(f, str) or f.startswith(".") or f.endswith(".pyc") or not f.endswith(".md"):
                    continue
                src = os.path.join(root, f)
                dst = os.path.join(dest_dir, f)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copyfile(src, dst)
    except Exception:
        return

try:
    _base = get_user_data_dir()
    _ensure_default_sops(_base)
    _ensure_default_mykey(_base)
except Exception:
    pass

@app.post("/api/workspace/set")
async def set_workspace(request: Request):
    data = await request.json()
    path = _normalize_workspace_root(data.get("path"))
    if not path or not os.path.isdir(path):
        return JSONResponse(status_code=400, content={"error": "Invalid directory path"})
    if "GA_APP_DATA_DIR" not in os.environ:
        cur = os.environ.get("GA_USER_DATA_DIR")
        if isinstance(cur, str) and cur:
            os.environ["GA_APP_DATA_DIR"] = cur
    app.current_workspace = path
    os.environ["GA_WORKSPACE_ROOT"] = path
    cfg = get_user_data_dir()
    _add_workspace_history(path)
    _ensure_default_sops(cfg)
    _ensure_default_mykey(cfg)
    return {"status": "ok", "workspace": path}

@app.get("/api/workspace/get")
def get_workspace():
    root = get_workspace_root_dir()
    base = get_user_data_dir()
    _ensure_default_sops(base)
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
                cfg = os.path.join(fp, _config_dir_name())
                if (
                    "ga" in low
                    or os.path.exists(os.path.join(fp, "mykey.json"))
                    or os.path.isdir(os.path.join(fp, "memory"))
                    or os.path.exists(os.path.join(cfg, "mykey.json"))
                    or os.path.isdir(os.path.join(cfg, "memory"))
                ):
                    picked.append(os.path.abspath(fp))
            for p in picked:
                if p not in options:
                    options.append(p)
    except Exception:
        pass

    return {"current": current, "options": options}

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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

import json

def _load_mykey_module_from_path(path):
    if not os.path.exists(path):
        return {}
    try:
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

def _normalize_api_base(apibase):
    if not isinstance(apibase, str):
        return ""
    return apibase.strip().rstrip("/")

def _auto_make_url(base, path):
    b = (base or "").strip().rstrip("/")
    p = (path or "").strip().lstrip("/")
    return f"{b}/{p}" if p else b

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
def process_agent_output(display_queue, source="user", prompt_text=None, run_id=None, cancel_event=None):
    finished_normally = False
    def broadcast_state(state_name, reason=""):
        payload = {
            "type": "state",
            "state": state_name,
            "source": source,
            "run_id": run_id,
        }
        if reason:
            payload["reason"] = reason
        state.ui_state = state_name
        print(f"[Status] broadcast state={state_name} source={source} run_id={run_id} reason={reason}")
        stream_manager.broadcast(json.dumps(payload))

    # If we have the prompt text (e.g. for autonomous), broadcast it as a user message first
    # This ensures the UI shows what triggered the action
    if prompt_text:
        stream_manager.broadcast(json.dumps({
            'type': 'message', 
            'role': 'user', 
            'content': prompt_text,
            'source': source,
            'run_id': run_id,
            'timestamp': time.strftime('%H:%M:%S')
        }))

    # Notify start of assistant response
    stream_manager.broadcast(json.dumps({
        'type': 'start', 
        'source': source,
        'run_id': run_id
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
                    stream_manager.broadcast(json.dumps({
                        'type': 'chunk', 
                        'content': item['next'],
                        'source': source,
                        'run_id': run_id
                    }))
                    if _looks_like_human_request(item.get('next', '')):
                        broadcast_state("need-user", "chunk suggests human input")
            if 'done' in item:
                if cancel_event is None or not cancel_event.is_set():
                    done_text = item.get('done', '')
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
                        'run_id': run_id
                    }))
                break
    finally:
        try:
            state.finish_run(run_id)
        except Exception:
            pass
        if not finished_normally and not getattr(state.agent, "is_running", False):
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
        self.scheduler_interval = 30
        self.run_lock = threading.Lock()
        self.active_runs = {}
        self.ui_state = "idle"

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
    def put_task(self, query, source="user"):
        q = queue.Queue()
        q.put({"done": f"服务初始化失败：{self._err}"})
        return q

state = AppState()

def init_agent():
    try:
        importlib.invalidate_caches()
        if "mykey" in sys.modules:
            del sys.modules["mykey"]
        if "llmcore" in sys.modules:
            importlib.reload(sys.modules["llmcore"])
        else:
            import llmcore  # noqa: F401
        if "sidercall" in sys.modules:
            importlib.reload(sys.modules["sidercall"])
        else:
            import sidercall  # noqa: F401
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
            "autonomous_enabled": state.autonomous_enabled,
            "autonomous_threshold": state.autonomous_threshold,
            "idle_time": idle_time,
            "last_activity_time": state.last_activity_time,
            "agent_init_error": state.agent_init_error
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
            "autonomous_enabled": state.autonomous_enabled,
            "autonomous_threshold": state.autonomous_threshold,
            "idle_time": 0,
            "last_activity_time": state.last_activity_time,
            "agent_init_error": state.agent_init_error,
            "needs_human_input": state.needs_human_input,
            "status_error": str(e)
        }

@app.get("/api/history")
def get_history():
    return {"history": state.agent.history}

@app.get("/api/stream")
async def stream(request: Request):
    async def event_generator():
        q = stream_manager.add_queue()
        try:
            while True:
                # Poll the queue (non-blocking in thread, blocking in async)
                # Since queue.get() is blocking, we use a loop with small sleep to be async friendly
                try:
                    # Get all available messages
                    while not q.empty():
                        msg = q.get_nowait()
                        yield f"data: {msg}\n\n"
                    await asyncio.sleep(0.1)
                except Exception:
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            stream_manager.remove_queue(q)
            print("Client disconnected from stream")
        finally:
            stream_manager.remove_queue(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/chat")
async def chat(request: Request):
    if state.agent_init_error:
        return {"error": f"Agent init failed: {state.agent_init_error}"}
    state.clear_human_input()
    data = await request.json()
    prompt = data.get("prompt")
    if not prompt:
        return {"error": "No prompt provided"}
    
    # Update activity time
    state.last_activity_time = time.time()
    
    # Put task into agent's queue
    display_queue = state.agent.put_task(prompt, source="user")
    run_id, cancel_event = state.new_run()
    
    # Start background task to broadcast output
    # Note: We pass prompt_text=prompt so it gets broadcasted back to all clients (including sender)
    # This simplifies frontend logic (just listen to stream)
    threading.Thread(target=process_agent_output, args=(display_queue, "user", prompt, run_id, cancel_event), daemon=True).start()
    
    return {"status": "queued", "run_id": run_id}

@app.post("/api/control")
async def control(request: Request):
    data = await request.json()
    action = data.get("action")
    if state.agent_init_error and action != "reload_agent":
        return {"error": f"Agent init failed: {state.agent_init_error}"}
    
    # Always update activity time on user interaction
    state.last_activity_time = time.time()
    
    if action == "stop":
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
            return {"status": "stopped", "forced_restart": True, "agent_init_error": state.agent_init_error, "canceled_run_ids": canceled}
        return {"status": "stopped", "forced_restart": False, "canceled_run_ids": canceled}
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
    elif action == "clear_history":
        state.cancel_runs(None)
        state.agent.clear_history()
        return {"status": "cleared"}
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
        state.cancel_runs(None)
        state.clear_human_input()
        if hasattr(state.agent, "reload_config"):
            state.agent.reload_config()
        else:
            state.agent, state.agent_init_error = init_agent()
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
    path = os.path.join(base, "mykey.json")
    if os.path.exists(path):
        return {"exists": True}
    return {"exists": False}

@app.post("/api/config/mykey")
async def save_mykey(request: Request):
    data = await request.json()
    content = data.get("content")
    if not isinstance(content, str):
        return JSONResponse(status_code=400, content={"error": "content must be string"})
    base = get_user_data_dir()
    path = os.path.join(base, "mykey.json")
    _write_text(path, content)
    return {"status": "saved"}

@app.get("/api/llm_configs")
def list_llm_configs():
    base = get_user_data_dir()
    path = os.path.join(base, "mykey.json")
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
            path = os.path.join(base, "mykey.json")
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
            headers = {"x-api-key": apikey, "Content-Type": "application/json", "anthropic-version": "2023-06-01"}
            payload = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
        else:
            url = _auto_make_url(apibase, "chat/completions")
            auth = apikey if apikey.lower().startswith("bearer ") else f"Bearer {apikey}"
            headers = {"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json"}
            payload = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1, "temperature": 0}

        r = requests.post(url, headers=headers, json=payload, timeout=(5, 15))
        if r.status_code >= 400:
            body = (r.text or "").strip()
            body = body[:600]
            return {"ok": False, "url": url, "status_code": r.status_code, "error": body or f"HTTP {r.status_code}"}
        return {"ok": True, "url": url, "status_code": r.status_code}
    except Exception as e:
        return {"ok": False, "url": url if "url" in locals() else "", "error": str(e)}

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
        path = os.path.join(base, "mykey.json")
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
            return {"status": "saved", "id": "sider_cookie"}

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
        return {"status": "saved", "id": cid}
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
    path = os.path.join(base, "mykey.json")
    module = _load_mykey_module_from_path(path)
    order, values = _read_mykey_simple_assignments(module)
    if cid in values:
        del values[cid]
    order = [k for k in order if k != cid]
    content = _render_mykey_py(order, values)
    _write_text(path, content)
    return {"status": "deleted"}

@app.get("/api/todo")
def get_todo():
    base = get_user_data_dir()
    path = os.path.join(base, "ToDo.txt")
    if os.path.exists(path):
        return {"exists": True, "content": _read_text(path)}
    return {"exists": False, "content": ""}

@app.post("/api/todo")
async def save_todo(request: Request):
    data = await request.json()
    content = data.get("content")
    if not isinstance(content, str):
        return JSONResponse(status_code=400, content={"error": "content must be string"})
    base = get_user_data_dir()
    path = os.path.join(base, "ToDo.txt")
    _write_text(path, content)
    return {"status": "saved"}

@app.get("/api/sop/list")
def list_sops():
    base = get_user_data_dir()
    _ensure_default_sops(base)
    mem_dir = os.path.join(base, "memory")
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
    base = get_user_data_dir()
    _ensure_default_sops(base)
    mem_dir = os.path.join(base, "memory")
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
    base = get_user_data_dir()
    _ensure_default_sops(base)
    mem_dir = os.path.join(base, "memory")
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

# Mount frontend static files
# We mount this last so API routes take precedence
frontend_dir = resolve_frontend_dir()
if frontend_dir:
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    print("Warning: frontend directory not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
