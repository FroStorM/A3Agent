import os
import sys
import threading
import json
WORKSPACE_SWITCH_ENABLED = False
import time
import asyncio
import queue
import traceback
import shutil
import sqlite3
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import importlib
import importlib.util
import re
import uuid
import user_store
from runtime_context import scoped_runtime_context, get_runtime_value
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
SESSION_COOKIE_NAME = "ga_session"


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def should_serve_frontend():
    return _env_flag("GA_SERVE_FRONTEND", default=True)


def _get_auth_store_root():
    return str(app_data_dir())


def _safe_username(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", value):
        return None
    return value


def _safe_email(value):
    try:
        return user_store.normalize_email(value)
    except Exception:
        return None


def _slugify_username(value):
    return _safe_username(value)


def get_user_workspace_root(username):
    workspace_root = get_workspace_root_dir()
    safe = _slugify_username(username)
    if not safe:
        raise ValueError("invalid username")
    return os.path.join(workspace_root, "users", safe)


def get_user_data_dir_for_username(username):
    root = get_user_workspace_root(username)
    cfg = os.path.join(root, _config_dir_name())
    os.makedirs(cfg, exist_ok=True)
    _ensure_default_ga_config(cfg)
    _ensure_default_mykey(cfg)
    return cfg


def _session_token_from_request(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def get_request_user(request: Request):
    user = getattr(request.state, "user", None)
    if user:
        return user
    token = _session_token_from_request(request)
    if not token:
        return None
    user = user_store.get_user_by_session(_get_auth_store_root(), token)
    request.state.user = user
    return user


def require_user(request: Request):
    user = get_request_user(request)
    if not user:
        raise PermissionError("login required")
    return user


def require_admin(request: Request):
    user = require_user(request)
    if not user.get("is_admin"):
        raise PermissionError("admin required")
    return user


def get_request_data_dir(request: Request, target_username=None, allow_admin_override=False):
    user = require_user(request)
    effective_username = user["username"]
    if target_username:
        safe_target = _safe_username(target_username)
        if not safe_target:
            raise ValueError("invalid target username")
        if safe_target != effective_username:
            if not allow_admin_override or not user.get("is_admin"):
                raise PermissionError("admin required")
            effective_username = safe_target
    return get_user_data_dir_for_username(effective_username), effective_username


def get_user_runtime(request: Request):
    user = require_user(request)
    runtime = runtime_registry.get_or_create(user["username"])
    request.state.runtime = runtime
    return runtime


def _admin_file_root(base, scope):
    if scope == "memory":
        return os.path.join(base, "memory")
    if scope == "schedule":
        return os.path.join(base, "sche_tasks")
    if scope == "config":
        return base
    raise ValueError("invalid scope")


def _admin_safe_path(scope, rel_path):
    if scope in ("memory", "schedule", "config"):
        return _safe_rel_path(rel_path)
    return None


def _admin_root_and_path(username, scope, rel_path):
    safe_username = _safe_username(username)
    safe_path = _admin_safe_path(scope, rel_path)
    if not safe_username or not safe_path:
        raise ValueError("invalid username or path")
    base = get_user_data_dir_for_username(safe_username)
    root = os.path.abspath(_admin_file_root(base, scope))
    target = os.path.abspath(os.path.join(root, safe_path))
    if target != root and not target.startswith(root + os.sep):
        raise ValueError("invalid path")
    return safe_username, root, target, safe_path


def _write_audit_log(actor_username, action, target_username=None, detail=None):
    try:
        user_store.add_audit_log(
            _get_auth_store_root(),
            actor_username=actor_username,
            action=action,
            target_username=target_username,
            detail=json.dumps(detail, ensure_ascii=False) if isinstance(detail, (dict, list)) else detail,
        )
    except Exception:
        pass


def _get_user_limits(username):
    user = user_store.get_user_by_username(_get_auth_store_root(), username)
    if not user:
        return {"max_parallel_runs": 1, "max_prompt_chars": 20000, "max_upload_bytes": 10485760}
    return {
        "max_parallel_runs": max(1, int(user.get("max_parallel_runs") or 1)),
        "max_prompt_chars": max(100, int(user.get("max_prompt_chars") or 20000)),
        "max_upload_bytes": max(1024, int(user.get("max_upload_bytes") or 10485760)),
    }


@app.middleware("http")
async def load_request_user(request: Request, call_next):
    try:
        token = _session_token_from_request(request)
        request.state.user = user_store.get_user_by_session(_get_auth_store_root(), token) if token else None
    except Exception:
        request.state.user = None
    response = await call_next(request)
    return response


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
        newest_source_mtime = max(os.path.getmtime(src) for src in bundled_sources)
        for name in ("mykey.json", "mykey.py"):
            dst = os.path.join(target_root, name)
            if not os.path.isfile(dst):
                continue
            try:
                if os.path.getsize(dst) <= 0 or os.path.getmtime(dst) < newest_source_mtime:
                    os.remove(dst)
            except Exception:
                pass
        for src in bundled_sources:
            dst = os.path.join(target_root, os.path.basename(src))
            if _should_copy_file(src, dst, overwrite_if_source_newer=True):
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
    root = os.environ.get("GA_WORKSPACE_ROOT")
    if isinstance(root, str) and root:
        os.makedirs(root, exist_ok=True)
        return root
    root = str(resource_dir())
    os.makedirs(root, exist_ok=True)
    return root

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
    runtime_root = get_runtime_value("workspace_root")
    if runtime_root:
        ensure_dir(runtime_root)
        return str(runtime_root)
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
    runtime_data_dir = get_runtime_value("user_data_dir")
    if runtime_data_dir:
        os.environ["GA_USER_DATA_DIR"] = str(runtime_data_dir)
        return str(runtime_data_dir)
    root = get_workspace_root_dir()
    cfg = workspace_config_dir(root)
    os.environ["GA_WORKSPACE_ROOT"] = root
    os.environ["GA_USER_DATA_DIR"] = str(cfg)
    return str(cfg)


def _get_app_data_dir():
    return str(app_data_dir())


def _workspace_history_path():
    return str(workspace_history_path())

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

def _ensure_default_sops(base):
    try:
        _ensure_default_ga_config(base)
    except Exception:
        return

try:
    _base = get_user_data_dir()
    _ensure_default_ga_config(_base)
    _ensure_default_mykey(_base)
    user_store.init_store(_get_auth_store_root())
    user_store.ensure_bootstrap_admin(_get_auth_store_root())
except Exception:
    pass


@app.on_event("startup")
async def _log_startup():
    try:
        _ensure_default_ga_config(_base)
        _ensure_default_mykey(_base)
    except Exception:
        pass
    try:
        user_store.init_store(_get_auth_store_root())
        user_store.ensure_bootstrap_admin(_get_auth_store_root())
        user_store.cleanup_expired_sessions(_get_auth_store_root())
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
    if not WORKSPACE_SWITCH_ENABLED:
        return JSONResponse(status_code=403, content={"error": "workspace switching is disabled"})
    data = await request.json()
    path_input = data.get("path")
    # 确保路径是字符串类型
    if not isinstance(path_input, str):
        path_input = str(path_input) if path_input else None
    path = normalize_workspace_root(path_input)
    if not path or not os.path.isdir(path):
        return JSONResponse(status_code=400, content={"error": "Invalid directory path"})

    # 保存旧的配置目录路径
    old_cfg = get_user_data_dir()

    if "GA_APP_DATA_DIR" not in os.environ:
        cur = os.environ.get("GA_USER_DATA_DIR")
        if isinstance(cur, str) and cur:
            os.environ["GA_APP_DATA_DIR"] = cur

    # 更新workspace环境变量
    app.current_workspace = str(path)
    os.environ["GA_WORKSPACE_ROOT"] = str(path)

    # 获取新的配置目录路径
    new_cfg = get_user_data_dir()

    # 如果新旧路径不同，且旧配置目录存在，则移动ga_config
    if old_cfg != new_cfg and os.path.isdir(old_cfg):
        try:
            # 如果新配置目录已存在，先删除（或者可以选择合并）
            if os.path.exists(new_cfg):
                import shutil
                shutil.rmtree(new_cfg, ignore_errors=True)
            # 移动整个ga_config目录
            import shutil
            shutil.move(old_cfg, new_cfg)
            print(f"[workspace] Moved ga_config from {old_cfg} to {new_cfg}")
        except Exception as e:
            print(f"[workspace] Failed to move ga_config: {e}")
            # 如果移动失败，至少确保新目录存在
            _ensure_default_ga_config(new_cfg)
            _ensure_default_mykey(new_cfg)
    else:
        # 确保新配置目录存在
        _ensure_default_ga_config(new_cfg)
        _ensure_default_mykey(new_cfg)

    # 更新环境变量指向新的配置目录
    os.environ["GA_USER_DATA_DIR"] = new_cfg

    _add_workspace_history(str(path))
    return {"status": "ok", "workspace": str(path)}

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
    options = [current] if isinstance(current, str) and current and os.path.isdir(current) else []
    return {"current": current, "options": options, "switch_enabled": WORKSPACE_SWITCH_ENABLED}

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

def _mirror_mykey_config(content, source_path):
    """Keep bundled/portable mykey.json copies in sync with the writable config."""
    try:
        src = os.path.abspath(str(source_path))
    except Exception:
        return

    candidate_roots = []

    def add_root(value):
        if not value:
            return
        try:
            root = os.path.abspath(str(value))
        except Exception:
            return
        if root not in candidate_roots:
            candidate_roots.append(root)

    add_root(os.path.dirname(sys.executable) if getattr(sys, "executable", None) else None)
    add_root(os.environ.get("GA_BASE_DIR"))
    try:
        res_root = resource_dir()
        add_root(res_root)
        try:
            res_root_path = os.path.abspath(str(res_root))
            if os.path.basename(res_root_path) == "Resources":
                add_root(os.path.join(os.path.dirname(res_root_path), "MacOS"))
        except Exception:
            pass
    except Exception:
        pass
    add_root(BASE_DIR)

    for root in candidate_roots:
        if not root:
            continue
        cfg_root = root if os.path.basename(root) == _config_dir_name() else os.path.join(root, _config_dir_name())
        target = os.path.join(cfg_root, os.path.basename(src))
        if os.path.abspath(target) == src:
            continue
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            _write_text(target, content)
        except Exception as e:
            print(f"[WARN] mirror mykey config failed for {target}: {e}")

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
            for q in list(self.queues):
                q.put(data)

# Helper to bridge Agent Queue to Stream Manager
def process_agent_output(user_state, stream_manager, display_queue, source="user", prompt_text=None, run_id=None, cancel_event=None, request_id=None):
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
        user_state.ui_state = state_name
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
                        user_state.set_human_input(item.get('done', ''), [])
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
                break
    finally:
        try:
            user_state.finish_run(run_id)
        except Exception:
            pass
        if not finished_normally and not getattr(user_state.agent, "is_running", False):
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
    def put_task(self, query, source="user"):
        q = queue.Queue()
        q.put({"done": f"服务初始化失败：{self._err}"})
        return q

class UserRuntime(AppState):
    def __init__(self, username, workspace_root, user_data_dir):
        super().__init__()
        self.username = username
        self.workspace_root = workspace_root
        self.user_data_dir = user_data_dir
        self.stream_manager = StreamManager()


class RuntimeRegistry:
    def __init__(self):
        self.lock = threading.Lock()
        self._runtimes = {}

    def get(self, username):
        with self.lock:
            return self._runtimes.get(username)

    def get_or_create(self, username):
        with self.lock:
            runtime = self._runtimes.get(username)
            if runtime is not None:
                return runtime
            user_data_dir = get_user_data_dir_for_username(username)
            workspace_root = get_user_workspace_root(username)
            runtime = UserRuntime(username, workspace_root, user_data_dir)
            runtime.agent, runtime.agent_init_error = init_agent(runtime)
            self._runtimes[username] = runtime
            return runtime

    def all(self):
        with self.lock:
            return list(self._runtimes.values())


runtime_registry = RuntimeRegistry()


def get_runtime_by_username(username):
    return runtime_registry.get(username)


def get_current_runtime():
    username = get_runtime_value("username")
    if not username:
        return None
    return runtime_registry.get(username)


def _run_agent_thread(runtime, agent):
    def _runner():
        with scoped_runtime_context(
            username=runtime.username,
            workspace_root=runtime.workspace_root,
            user_data_dir=runtime.user_data_dir,
        ):
            agent.run()
    threading.Thread(target=_runner, daemon=True).start()


def init_agent(runtime):
    try:
        with scoped_runtime_context(
            username=runtime.username,
            workspace_root=runtime.workspace_root,
            user_data_dir=runtime.user_data_dir,
        ):
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
                print(f"Warning: No LLM client configured for user {runtime.username}.")
            _run_agent_thread(runtime, agent)
            return agent, None
    except Exception as e:
        err = str(e)
        print(f"Warning: agent init failed for user {runtime.username}: {err}")
        return FallbackAgent(err), err

# Autonomous Monitor Thread
def autonomous_monitor():
    while True:
        time.sleep(10)
        for runtime in runtime_registry.all():
            try:
                if not runtime.autonomous_enabled or runtime.agent_init_error is not None:
                    continue
                limits = _get_user_limits(runtime.username)
                if len(runtime.active_runs) >= limits["max_parallel_runs"]:
                    continue
                idle_time = time.time() - runtime.last_activity_time
                if idle_time <= runtime.autonomous_threshold:
                    continue
                if runtime.agent.is_running:
                    continue
                print(f"Triggering autonomous action for {runtime.username} (Idle: {int(idle_time)}s)")
                runtime.last_activity_time = time.time()
                prompt = f"Current Time: {time.strftime('%Y-%m-%d %H:%M:%S')}. You are in autonomous mode (idle for >{int(runtime.autonomous_threshold/60)}m). Check pending tasks, explore, or perform maintenance."
                with scoped_runtime_context(username=runtime.username, workspace_root=runtime.workspace_root, user_data_dir=runtime.user_data_dir):
                    display_queue = runtime.agent.put_task(prompt, source="autonomous")
                run_id, cancel_event = runtime.new_run()
                threading.Thread(
                    target=process_agent_output,
                    args=(runtime, runtime.stream_manager, display_queue, "autonomous", prompt, run_id, cancel_event),
                    daemon=True,
                ).start()
            except Exception:
                pass


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
        for runtime in runtime_registry.all():
            if not runtime.scheduler_enabled or runtime.agent_init_error is not None:
                continue
            limits = _get_user_limits(runtime.username)
            if len(runtime.active_runs) >= limits["max_parallel_runs"]:
                time.sleep(max(1, int(runtime.scheduler_interval)))
                continue
            try:
                with scoped_runtime_context(username=runtime.username, workspace_root=runtime.workspace_root, user_data_dir=runtime.user_data_dir):
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
                        display_queue = runtime.agent.put_task(prompt, source="scheduler")
                        run_id, cancel_event = runtime.new_run()
                        threading.Thread(
                            target=process_agent_output,
                            args=(runtime, runtime.stream_manager, display_queue, "scheduler", prompt, run_id, cancel_event),
                            daemon=True,
                        ).start()
            except Exception:
                pass
            time.sleep(max(1, int(runtime.scheduler_interval)))

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
def get_status(request: Request):
    try:
        state = get_user_runtime(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
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
def get_history(request: Request):
    try:
        state = get_user_runtime(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    return {"history": state.agent.history}


@app.get("/api/auth/me")
def auth_me(request: Request):
    user = get_request_user(request)
    return {"authenticated": bool(user), "user": user}


@app.post("/api/auth/login")
async def auth_login(request: Request):
    data = await request.json()
    username = _safe_username(data.get("username"))
    password = data.get("password")
    if not username or not isinstance(password, str) or not password:
        return JSONResponse(status_code=400, content={"error": "username/password required"})
    user = user_store.authenticate_user(_get_auth_store_root(), username, password)
    if not user:
        return JSONResponse(status_code=401, content={"error": "invalid credentials"})
    session = user_store.create_session(_get_auth_store_root(), user["id"])
    response = JSONResponse({"status": "ok", "user": user, "expires_at": session["expires_at"]})
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session["token"],
        httponly=True,
        samesite="lax",
        max_age=user_store.SESSION_TTL_SECONDS,
        path="/",
    )
    return response


@app.post("/api/auth/register")
async def auth_register(request: Request):
    data = await request.json()
    username = _safe_username(data.get("username"))
    email = _safe_email(data.get("email"))
    password = data.get("password")
    confirm_password = data.get("confirm_password")
    if not username:
        return JSONResponse(status_code=400, content={"error": "valid username required"})
    if not email:
        return JSONResponse(status_code=400, content={"error": "valid email required"})
    if not isinstance(password, str) or len(password) < 6:
        return JSONResponse(status_code=400, content={"error": "password must be at least 6 characters"})
    if confirm_password is not None and password != confirm_password:
        return JSONResponse(status_code=400, content={"error": "password confirmation does not match"})
    try:
        user = user_store.create_user(_get_auth_store_root(), username, password, is_admin=False, email=email)
    except sqlite3.IntegrityError as e:
        detail = str(e).lower()
        if "email" in detail:
            return JSONResponse(status_code=409, content={"error": "email already exists"})
        return JSONResponse(status_code=409, content={"error": "username already exists"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    get_user_data_dir_for_username(username)
    session = user_store.create_session(_get_auth_store_root(), user["id"])
    _write_audit_log(user["username"], "self_register", target_username=user["username"], detail={"email": email})
    response = JSONResponse({"status": "ok", "user": user, "expires_at": session["expires_at"]})
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session["token"],
        httponly=True,
        samesite="lax",
        max_age=user_store.SESSION_TTL_SECONDS,
        path="/",
    )
    return response


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    token = _session_token_from_request(request)
    if token:
        user_store.delete_session(_get_auth_store_root(), token)
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


@app.post("/api/auth/change_password")
async def auth_change_password(request: Request):
    try:
        user = require_user(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    data = await request.json()
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")
    if not isinstance(old_password, str) or not old_password:
        return JSONResponse(status_code=400, content={"error": "old password required"})
    if not isinstance(new_password, str) or len(new_password) < 6:
        return JSONResponse(status_code=400, content={"error": "new password must be at least 6 characters"})
    if confirm_password is not None and new_password != confirm_password:
        return JSONResponse(status_code=400, content={"error": "password confirmation does not match"})
    try:
        user_store.change_password(_get_auth_store_root(), user["username"], old_password, new_password)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    token = _session_token_from_request(request)
    session = user_store.create_session(_get_auth_store_root(), user["id"])
    response = JSONResponse({"status": "ok"})
    if token:
        user_store.delete_session(_get_auth_store_root(), token)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session["token"],
        httponly=True,
        samesite="lax",
        max_age=user_store.SESSION_TTL_SECONDS,
        path="/",
    )
    return response


@app.get("/api/admin/users")
def admin_list_users(
    request: Request,
    q: str = "",
    role: str = "all",
    status: str = "all",
    page: int = 1,
    page_size: int = 200,
):
    try:
        require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    users = user_store.list_users(_get_auth_store_root())
    q = str(q or "").strip().lower()
    role = str(role or "all").strip().lower()
    status = str(status or "all").strip().lower()
    if q:
        users = [u for u in users if q in str(u.get("username") or "").lower()]
    if role == "admin":
        users = [u for u in users if u.get("is_admin")]
    elif role == "member":
        users = [u for u in users if not u.get("is_admin")]
    if status == "active":
        users = [u for u in users if u.get("is_active")]
    elif status == "disabled":
        users = [u for u in users if not u.get("is_active")]
    total = len(users)
    page = max(1, int(page or 1))
    page_size = min(500, max(1, int(page_size or 200)))
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "users": users[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.post("/api/admin/users")
async def admin_create_user(request: Request):
    try:
        admin_user = require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    data = await request.json()
    username = _safe_username(data.get("username"))
    email = _safe_email(data.get("email")) if data.get("email") else None
    password = data.get("password")
    is_admin = bool(data.get("is_admin"))
    if not username or not isinstance(password, str) or len(password) < 6:
        return JSONResponse(status_code=400, content={"error": "valid username and password required"})
    try:
        user = user_store.create_user(_get_auth_store_root(), username, password, is_admin=is_admin, email=email)
    except sqlite3.IntegrityError:
        return JSONResponse(status_code=409, content={"error": "username or email already exists"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    get_user_data_dir_for_username(username)
    _write_audit_log(admin_user["username"], "admin_create_user", target_username=username, detail={"is_admin": is_admin})
    return {"status": "created", "user": user}


@app.post("/api/admin/users/password")
async def admin_reset_user_password(request: Request):
    try:
        admin_user = require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    data = await request.json()
    username = _safe_username(data.get("username"))
    new_password = data.get("new_password")
    if not username:
        return JSONResponse(status_code=400, content={"error": "valid username required"})
    if not isinstance(new_password, str) or len(new_password) < 6:
        return JSONResponse(status_code=400, content={"error": "new password must be at least 6 characters"})
    try:
        user = user_store.update_password(_get_auth_store_root(), username, new_password)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    _write_audit_log(admin_user["username"], "admin_reset_password", target_username=username)
    return {"status": "updated", "user": user}


@app.post("/api/admin/users/status")
async def admin_update_user_status(request: Request):
    try:
        admin_user = require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    data = await request.json()
    username = _safe_username(data.get("username"))
    is_active = data.get("is_active")
    if not username or not isinstance(is_active, bool):
        return JSONResponse(status_code=400, content={"error": "valid username and is_active required"})
    if username == admin_user["username"] and not is_active:
        return JSONResponse(status_code=400, content={"error": "cannot disable current admin account"})
    try:
        user = user_store.set_user_active(_get_auth_store_root(), username, is_active)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    _write_audit_log(admin_user["username"], "admin_update_user_status", target_username=username, detail={"is_active": is_active})
    return {"status": "updated", "user": user}


@app.post("/api/admin/users/limits")
async def admin_update_user_limits(request: Request):
    try:
        admin_user = require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    data = await request.json()
    username = _safe_username(data.get("username"))
    if not username:
        return JSONResponse(status_code=400, content={"error": "valid username required"})
    try:
        user = user_store.set_user_limits(
            _get_auth_store_root(),
            username,
            max_parallel_runs=data.get("max_parallel_runs"),
            max_prompt_chars=data.get("max_prompt_chars"),
            max_upload_bytes=data.get("max_upload_bytes"),
        )
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    _write_audit_log(
        admin_user["username"],
        "admin_update_user_limits",
        target_username=username,
        detail={
            "max_parallel_runs": user.get("max_parallel_runs"),
            "max_prompt_chars": user.get("max_prompt_chars"),
            "max_upload_bytes": user.get("max_upload_bytes"),
        },
    )
    return {"status": "updated", "user": user}


@app.get("/api/admin/files/tree")
def admin_file_tree(request: Request, username: str, scope: str):
    try:
        require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    safe_username = _safe_username(username)
    if not safe_username:
        return JSONResponse(status_code=400, content={"error": "invalid username"})
    try:
        base = get_user_data_dir_for_username(safe_username)
        root = _admin_file_root(base, scope)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    os.makedirs(root, exist_ok=True)
    items = []
    root_abs = os.path.abspath(root)
    for cur_root, dirs, files in os.walk(root_abs):
        dirs[:] = [d for d in dirs if isinstance(d, str) and not d.startswith(".") and d != "__pycache__"]
        rel_dir = os.path.relpath(cur_root, root_abs)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        for d in dirs:
            items.append({"path": f"{rel_dir}/{d}".strip("/"), "kind": "dir"})
        for f in files:
            if f.startswith("."):
                continue
            items.append({"path": f"{rel_dir}/{f}".strip("/"), "kind": "file"})
    items.sort(key=lambda x: (x["kind"], x["path"]))
    return {"items": items}


@app.get("/api/admin/files/read")
def admin_file_read(request: Request, username: str, scope: str, path: str):
    try:
        require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    safe_username = _safe_username(username)
    safe_path = _admin_safe_path(scope, path)
    if not safe_username or not safe_path:
        return JSONResponse(status_code=400, content={"error": "invalid username or path"})
    try:
        base = get_user_data_dir_for_username(safe_username)
        root = os.path.abspath(_admin_file_root(base, scope))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    target = os.path.abspath(os.path.join(root, safe_path))
    if target != root and not target.startswith(root + os.sep):
        return JSONResponse(status_code=400, content={"error": "invalid path"})
    if not os.path.isfile(target):
        return JSONResponse(status_code=404, content={"error": "not found"})
    return {"content": _read_text(target)}


@app.post("/api/admin/files/write")
async def admin_file_write(request: Request):
    try:
        admin_user = require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    data = await request.json()
    safe_username = _safe_username(data.get("username"))
    scope = data.get("scope")
    safe_path = _admin_safe_path(scope, data.get("path"))
    content = data.get("content")
    if not safe_username or not safe_path or not isinstance(content, str):
        return JSONResponse(status_code=400, content={"error": "invalid write request"})
    try:
        base = get_user_data_dir_for_username(safe_username)
        root = os.path.abspath(_admin_file_root(base, scope))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    target = os.path.abspath(os.path.join(root, safe_path))
    if target != root and not target.startswith(root + os.sep):
        return JSONResponse(status_code=400, content={"error": "invalid path"})
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    _write_audit_log(
        admin_user["username"],
        "admin_write_file",
        target_username=safe_username,
        detail={"scope": scope, "path": safe_path, "content_length": len(content)},
    )
    return {"status": "saved", "path": safe_path}


@app.post("/api/admin/files/create")
async def admin_file_create(request: Request):
    try:
        admin_user = require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    data = await request.json()
    username = data.get("username")
    scope = data.get("scope")
    path = data.get("path")
    kind = str(data.get("kind") or "file").strip().lower()
    try:
        safe_username, _root, target, safe_path = _admin_root_and_path(username, scope, path)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    if os.path.exists(target):
        return JSONResponse(status_code=409, content={"error": "path already exists"})
    try:
        if kind == "dir":
            os.makedirs(target, exist_ok=False)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write("")
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    _write_audit_log(admin_user["username"], "admin_create_path", target_username=safe_username, detail={"scope": scope, "path": safe_path, "kind": kind})
    return {"status": "created", "path": safe_path, "kind": kind}


@app.post("/api/admin/files/rename")
async def admin_file_rename(request: Request):
    try:
        admin_user = require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    data = await request.json()
    username = data.get("username")
    scope = data.get("scope")
    old_path = data.get("old_path")
    new_path = data.get("new_path")
    try:
        safe_username, _root, source, safe_old_path = _admin_root_and_path(username, scope, old_path)
        _safe_username2, _root2, target, safe_new_path = _admin_root_and_path(username, scope, new_path)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    if not os.path.exists(source):
        return JSONResponse(status_code=404, content={"error": "source not found"})
    if os.path.exists(target):
        return JSONResponse(status_code=409, content={"error": "target already exists"})
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        os.rename(source, target)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    _write_audit_log(admin_user["username"], "admin_rename_path", target_username=safe_username, detail={"scope": scope, "old_path": safe_old_path, "new_path": safe_new_path})
    return {"status": "renamed", "old_path": safe_old_path, "new_path": safe_new_path}


@app.post("/api/admin/files/delete")
async def admin_file_delete(request: Request):
    try:
        admin_user = require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    data = await request.json()
    username = data.get("username")
    scope = data.get("scope")
    path = data.get("path")
    try:
        safe_username, _root, target, safe_path = _admin_root_and_path(username, scope, path)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    if not os.path.exists(target):
        return JSONResponse(status_code=404, content={"error": "path not found"})
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
            kind = "dir"
        else:
            os.remove(target)
            kind = "file"
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    _write_audit_log(admin_user["username"], "admin_delete_path", target_username=safe_username, detail={"scope": scope, "path": safe_path, "kind": kind})
    return {"status": "deleted", "path": safe_path, "kind": kind}


@app.post("/api/admin/files/copy")
async def admin_file_copy(request: Request):
    try:
        admin_user = require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    data = await request.json()
    source_username = _safe_username(data.get("source_username"))
    target_username = _safe_username(data.get("target_username"))
    scope = data.get("scope")
    rel_path = _admin_safe_path(scope, data.get("path"))
    target_path = _admin_safe_path(scope, data.get("target_path") or data.get("path"))
    if not source_username or not target_username or not rel_path or not target_path:
        return JSONResponse(status_code=400, content={"error": "invalid copy request"})
    try:
        source_base = get_user_data_dir_for_username(source_username)
        target_base = get_user_data_dir_for_username(target_username)
        source_root = os.path.abspath(_admin_file_root(source_base, scope))
        target_root = os.path.abspath(_admin_file_root(target_base, scope))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    source_file = os.path.abspath(os.path.join(source_root, rel_path))
    target_file = os.path.abspath(os.path.join(target_root, target_path))
    if source_file != source_root and not source_file.startswith(source_root + os.sep):
        return JSONResponse(status_code=400, content={"error": "invalid source path"})
    if target_file != target_root and not target_file.startswith(target_root + os.sep):
        return JSONResponse(status_code=400, content={"error": "invalid target path"})
    if not os.path.isfile(source_file):
        return JSONResponse(status_code=404, content={"error": "source not found"})
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    shutil.copy2(source_file, target_file)
    _write_audit_log(
        admin_user["username"],
        "admin_copy_file",
        target_username=target_username,
        detail={"source_username": source_username, "scope": scope, "path": rel_path, "target_path": target_path},
    )
    return {"status": "copied"}


@app.post("/api/admin/files/copy_batch")
async def admin_file_copy_batch(request: Request):
    try:
        admin_user = require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    data = await request.json()
    source_username = _safe_username(data.get("source_username"))
    scope = data.get("scope")
    rel_path = _admin_safe_path(scope, data.get("path"))
    target_path = _admin_safe_path(scope, data.get("target_path") or data.get("path"))
    raw_targets = data.get("target_usernames") or []
    if not isinstance(raw_targets, list):
        return JSONResponse(status_code=400, content={"error": "target_usernames must be a list"})
    target_usernames = []
    for item in raw_targets:
        safe = _safe_username(item)
        if safe and safe not in target_usernames:
            target_usernames.append(safe)
    if not source_username or not rel_path or not target_path or not target_usernames:
        return JSONResponse(status_code=400, content={"error": "invalid batch copy request"})
    try:
        source_base = get_user_data_dir_for_username(source_username)
        source_root = os.path.abspath(_admin_file_root(source_base, scope))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    source_file = os.path.abspath(os.path.join(source_root, rel_path))
    if source_file != source_root and not source_file.startswith(source_root + os.sep):
        return JSONResponse(status_code=400, content={"error": "invalid source path"})
    if not os.path.isfile(source_file):
        return JSONResponse(status_code=404, content={"error": "source not found"})

    copied = []
    skipped = []
    for username in target_usernames:
        try:
            target_base = get_user_data_dir_for_username(username)
            target_root = os.path.abspath(_admin_file_root(target_base, scope))
            target_file = os.path.abspath(os.path.join(target_root, target_path))
            if target_file != target_root and not target_file.startswith(target_root + os.sep):
                skipped.append({"username": username, "reason": "invalid target path"})
                continue
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            shutil.copy2(source_file, target_file)
            copied.append(username)
        except Exception as e:
            skipped.append({"username": username, "reason": str(e)})
    _write_audit_log(
        admin_user["username"],
        "admin_copy_file_batch",
        detail={
            "source_username": source_username,
            "scope": scope,
            "path": rel_path,
            "target_path": target_path,
            "copied": copied,
            "skipped": skipped,
        },
    )
    return {"status": "copied", "copied": copied, "skipped": skipped, "count": len(copied)}


@app.post("/api/admin/files/upload")
async def admin_file_upload(
    request: Request,
    source_username: str = Form(...),
    scope: str = Form(...),
    target_path: str = Form(""),
    file: UploadFile = File(...),
):
    try:
        admin_user = require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    safe_username = _safe_username(source_username)
    safe_target_path = _admin_safe_path(scope, target_path or getattr(file, "filename", ""))
    if not safe_username or not safe_target_path:
        return JSONResponse(status_code=400, content={"error": "invalid upload target"})
    limits = _get_user_limits(safe_username)
    try:
        base = get_user_data_dir_for_username(safe_username)
        root = os.path.abspath(_admin_file_root(base, scope))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    target_file = os.path.abspath(os.path.join(root, safe_target_path))
    if target_file != root and not target_file.startswith(root + os.sep):
        return JSONResponse(status_code=400, content={"error": "invalid target path"})
    content = await file.read()
    if len(content) > limits["max_upload_bytes"]:
        return JSONResponse(status_code=400, content={"error": f"upload exceeds limit ({limits['max_upload_bytes']} bytes)"})
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    with open(target_file, "wb") as f:
        f.write(content)
    _write_audit_log(
        admin_user["username"],
        "admin_upload_file",
        target_username=safe_username,
        detail={"scope": scope, "target_path": safe_target_path, "filename": getattr(file, "filename", ""), "size": len(content)},
    )
    return {"status": "uploaded", "path": safe_target_path, "size": len(content)}


@app.get("/api/admin/audit_logs")
def admin_audit_logs(request: Request, actor_username: str = "", target_username: str = "", action: str = "", limit: int = 100):
    try:
        require_admin(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    logs = user_store.list_audit_logs(
        _get_auth_store_root(),
        actor_username=_safe_username(actor_username) if actor_username else None,
        target_username=_safe_username(target_username) if target_username else None,
        action=str(action or "").strip() or None,
        limit=limit,
    )
    return {"logs": logs}

@app.get("/api/stream")
async def stream(request: Request):
    try:
        state = get_user_runtime(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    async def event_generator():
        stream_manager = state.stream_manager
        q = stream_manager.add_queue()
        _debug_log("stream_connect", client=str(id(q)), queues=len(stream_manager.queues))
        try:
            while True:
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
    try:
        user = require_user(request)
        state = get_user_runtime(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
    if state.agent_init_error:
        return {"error": f"Agent init failed: {state.agent_init_error}"}
    t0 = time.time()
    while state.stopping and time.time() - t0 < 5:
        await asyncio.sleep(0.05)
    state.clear_human_input()
    data = await request.json()
    prompt = data.get("prompt")
    request_id = data.get("request_id")
    if not prompt:
        return {"error": "No prompt provided"}
    limits = _get_user_limits(user["username"])
    if len(str(prompt)) > limits["max_prompt_chars"]:
        return JSONResponse(status_code=400, content={"error": f"prompt exceeds limit ({limits['max_prompt_chars']} chars)"})
    if len(getattr(state, "active_runs", {}) or {}) >= limits["max_parallel_runs"]:
        return JSONResponse(status_code=429, content={"error": f"concurrent run limit reached ({limits['max_parallel_runs']})"})
    _debug_log("chat_received", prompt_len=len(prompt), request_id=request_id, stopping=state.stopping, is_running=getattr(state.agent, "is_running", False))
    
    # Update activity time
    state.last_activity_time = time.time()
    
    # Put task into agent's queue
    with scoped_runtime_context(username=state.username, workspace_root=state.workspace_root, user_data_dir=state.user_data_dir):
        display_queue = state.agent.put_task(prompt, source="user")
    run_id, cancel_event = state.new_run()
    _debug_log("chat_queued", run_id=run_id, request_id=request_id, prompt_len=len(prompt), stopping=state.stopping, is_running=getattr(state.agent, "is_running", False))
    
    # Start background task to broadcast output
    # Note: We pass prompt_text=prompt so it gets broadcasted back to all clients (including sender)
    # This simplifies frontend logic (just listen to stream)
    threading.Thread(target=process_agent_output, args=(state, state.stream_manager, display_queue, "user", prompt, run_id, cancel_event, request_id), daemon=True).start()
    
    return {"status": "queued", "run_id": run_id, "request_id": request_id}

@app.post("/api/control")
async def control(request: Request):
    try:
        state = get_user_runtime(request)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": str(e)})
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
                state.agent, state.agent_init_error = init_agent(state)
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
                with scoped_runtime_context(username=state.username, workspace_root=state.workspace_root, user_data_dir=state.user_data_dir):
                    state.agent.next_llm(int(idx))
            except Exception as e:
                return {"error": str(e)}
        else:
            with scoped_runtime_context(username=state.username, workspace_root=state.workspace_root, user_data_dir=state.user_data_dir):
                state.agent.next_llm()
        return {"status": "switched", "llm_name": state.agent.get_llm_name()}
    elif action == "clear_history":
        state.cancel_runs(None)
        with scoped_runtime_context(username=state.username, workspace_root=state.workspace_root, user_data_dir=state.user_data_dir):
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
        with scoped_runtime_context(username=state.username, workspace_root=state.workspace_root, user_data_dir=state.user_data_dir):
            if hasattr(state.agent, "reload_config"):
                state.agent.reload_config()
            else:
                state.agent, state.agent_init_error = init_agent(state)
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
def get_mykey(request: Request, username: Optional[str] = None):
    try:
        base, _ = get_request_data_dir(request, username, allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
    path = resolve_mykey_path(base, prefer_existing=True)
    return {"exists": bool(path and os.path.exists(path)), "path": str(path) if path else ""}

@app.post("/api/config/mykey")
async def save_mykey(request: Request):
    data = await request.json()
    content = data.get("content")
    if not isinstance(content, str):
        return JSONResponse(status_code=400, content={"error": "content must be string"})
    try:
        base, effective_username = get_request_data_dir(request, data.get("username"), allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
    path = resolve_mykey_path(base, prefer_existing=False)
    _write_text(path, content)
    _mirror_mykey_config(content, path)
    return {"status": "saved"}

@app.get("/api/llm_configs")
def list_llm_configs(request: Request, username: Optional[str] = None):
    try:
        base, _ = get_request_data_dir(request, username, allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
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
    proxy = data.get("proxy")

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

    if isinstance(proxy, str):
        proxy = proxy.strip()
    else:
        proxy = ""

    try:
        base_for_request, _ = get_request_data_dir(request, data.get("username"), allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})

    if cid and not apikey:
        try:
            path = resolve_mykey_path(base_for_request, prefer_existing=True)
            module = _load_mykey_module_from_path(path)
            v = module.get(cid)
            if isinstance(v, dict):
                k = v.get("apikey")
                if isinstance(k, str) and k.strip():
                    apikey = k.strip()
                if not proxy:
                    p = v.get("proxy")
                    if isinstance(p, str) and p.strip():
                        proxy = p.strip()
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

        proxies = {"http": proxy, "https": proxy} if proxy else None
        r = requests.post(url, headers=headers, json=payload, timeout=(5, 45), proxies=proxies)
        if r.status_code >= 400:
            body = (r.text or "").strip()
            body = body[:600]
            return {"ok": False, "url": url, "status_code": r.status_code, "error": body or f"HTTP {r.status_code}"}
        return {"ok": True, "url": url, "status_code": r.status_code}
    except requests.exceptions.ReadTimeout:
        return {"ok": False, "url": url if "url" in locals() else "", "error": "请求超时：请检查 API Base、网络出口和代理设置"}
    except requests.exceptions.ConnectTimeout:
        return {"ok": False, "url": url if "url" in locals() else "", "error": "连接超时：请检查 API Base、网络出口和代理设置"}
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
        base, _ = get_request_data_dir(request, data.get("username"), allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})

    try:
        read_path = resolve_mykey_path(base, prefer_existing=True)
        path = resolve_mykey_path(base, prefer_existing=False)
        module = _load_mykey_module_from_path(read_path)
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
            _mirror_mykey_config(content, path)
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
            p = data.get("proxy")
            if isinstance(p, str) and p.strip():
                v["proxy"] = p.strip()
            elif "proxy" in v and not (isinstance(v.get("proxy"), str) and v.get("proxy").strip()):
                v.pop("proxy", None)
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
            p = data.get("proxy")
            if isinstance(p, str) and p.strip():
                values[cid]["proxy"] = p.strip()
            order.append(cid)

        content = _render_mykey_py(order, values)
        _write_text(path, content)
        _mirror_mykey_config(content, path)
        reload_error = ""
        try:
            runtime = get_runtime_by_username(effective_username)
            if runtime is not None and hasattr(runtime, "agent") and hasattr(runtime.agent, "reload_config"):
                with scoped_runtime_context(username=runtime.username, workspace_root=runtime.workspace_root, user_data_dir=runtime.user_data_dir):
                    runtime.agent.reload_config()
                runtime.agent_init_error = None
        except Exception as e:
            reload_error = str(e)
            print(f"[WARN] agent reload after config save failed: {e}")
        return {"status": "saved", "id": cid, "reloaded": not bool(reload_error), "reload_error": reload_error}
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
    try:
        base, effective_username = get_request_data_dir(request, data.get("username"), allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
    path = resolve_mykey_path(base, prefer_existing=False)
    read_path = resolve_mykey_path(base, prefer_existing=True)
    module = _load_mykey_module_from_path(read_path)
    order, values = _read_mykey_simple_assignments(module)
    if cid in values:
        del values[cid]
    order = [k for k in order if k != cid]
    content = _render_mykey_py(order, values)
    _write_text(path, content)
    _mirror_mykey_config(content, path)
    runtime = get_runtime_by_username(effective_username)
    if runtime is not None:
        try:
            with scoped_runtime_context(username=runtime.username, workspace_root=runtime.workspace_root, user_data_dir=runtime.user_data_dir):
                if hasattr(runtime.agent, "reload_config"):
                    runtime.agent.reload_config()
            runtime.agent_init_error = None
        except Exception as e:
            print(f"[WARN] agent reload after config delete failed: {e}")
    return {"status": "deleted"}

@app.get("/api/todo")
def get_todo(request: Request, username: Optional[str] = None):
    try:
        base, _ = get_request_data_dir(request, username, allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
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
    try:
        base, _ = get_request_data_dir(request, data.get("username"), allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
    path = os.path.join(base, "ToDo.txt")
    _write_text(path, content)
    return {"status": "saved"}

@app.get("/api/sop/list")
def list_sops(request: Request, username: Optional[str] = None):
    try:
        base, _ = get_request_data_dir(request, username, allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
    _ensure_default_ga_config(base)
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
def read_sop(request: Request, name: str, username: Optional[str] = None):
    safe = _safe_rel_path(name)
    if not safe or not safe.endswith(".md"):
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    try:
        base, _ = get_request_data_dir(request, username, allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
    _ensure_default_ga_config(base)
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
    try:
        base, _ = get_request_data_dir(request, data.get("username"), allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
    _ensure_default_ga_config(base)
    mem_dir = os.path.join(base, "memory")
    mem_dir_abs = os.path.abspath(mem_dir)
    path = os.path.abspath(os.path.join(mem_dir_abs, safe))
    if not path.startswith(mem_dir_abs + os.sep):
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    _write_text(path, content)
    return {"status": "saved"}

@app.get("/api/schedule/list")
def list_schedule(request: Request, username: Optional[str] = None):
    try:
        base, _ = get_request_data_dir(request, username, allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
    result = {}
    for bucket in ("pending", "running", "done"):
        d = os.path.join(base, "sche_tasks", bucket)
        os.makedirs(d, exist_ok=True)
        files = [f for f in os.listdir(d) if f.endswith(".md") and _safe_name(f)]
        files.sort()
        result[bucket] = files
    return result

@app.get("/api/schedule/read")
def read_schedule(request: Request, bucket: str, name: str, username: Optional[str] = None):
    if bucket not in ("pending", "running", "done"):
        return JSONResponse(status_code=400, content={"error": "invalid bucket"})
    safe = _safe_name(name)
    if not safe or not safe.endswith(".md"):
        return JSONResponse(status_code=400, content={"error": "invalid name"})
    try:
        base, _ = get_request_data_dir(request, username, allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
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
    try:
        base, _ = get_request_data_dir(request, data.get("username"), allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
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
    try:
        base, _ = get_request_data_dir(request, data.get("username"), allow_admin_override=True)
    except (PermissionError, ValueError) as e:
        return JSONResponse(status_code=403 if isinstance(e, PermissionError) else 400, content={"error": str(e)})
    path = os.path.join(base, "sche_tasks", bucket, safe)
    try:
        os.remove(path)
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    return {"status": "deleted"}

frontend_dir = resolve_frontend_dir()
if should_serve_frontend() and frontend_dir:
    @app.get("/admin")
    def admin_page():
        return RedirectResponse(url="/admin/accounts", status_code=307)

    @app.get("/admin/")
    def admin_page_slash():
        return RedirectResponse(url="/admin/accounts", status_code=307)

    @app.get("/admin/accounts")
    def admin_accounts_page():
        path = os.path.join(frontend_dir, "admin-accounts.html")
        if not os.path.isfile(path):
            return JSONResponse(status_code=404, content={"error": "admin accounts frontend not found"})
        return FileResponse(path)

    @app.get("/admin/accounts/")
    def admin_accounts_page_slash():
        path = os.path.join(frontend_dir, "admin-accounts.html")
        if not os.path.isfile(path):
            return JSONResponse(status_code=404, content={"error": "admin accounts frontend not found"})
        return FileResponse(path)

    @app.get("/admin/configs")
    def admin_configs_page():
        path = os.path.join(frontend_dir, "admin-configs.html")
        if not os.path.isfile(path):
            return JSONResponse(status_code=404, content={"error": "admin configs frontend not found"})
        return FileResponse(path)

    @app.get("/admin/configs/")
    def admin_configs_page_slash():
        path = os.path.join(frontend_dir, "admin-configs.html")
        if not os.path.isfile(path):
            return JSONResponse(status_code=404, content={"error": "admin configs frontend not found"})
        return FileResponse(path)

if should_serve_frontend() and frontend_dir:
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    print(f"Frontend serving enabled: {frontend_dir}")
else:
    print("Frontend serving disabled")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9550)
