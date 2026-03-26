import os
import sys
from pathlib import Path


def backend_dir():
    return Path(__file__).resolve().parent


def resource_dir():
    try:
        bundled = Path(sys._MEIPASS).resolve()
        if bundled.exists():
            return bundled
    except Exception:
        pass

    root = os.environ.get("GA_BASE_DIR")
    if root:
        root_path = Path(root)
        if root_path.suffix == ".zip" and root_path.is_file():
            return root_path.parent.parent.resolve()
        return root_path.resolve()
    return backend_dir()


def data_dir():
    root = os.environ.get("GA_USER_DATA_DIR")
    if root:
        return Path(root).resolve()
    return resource_dir()


def app_root_dir(app_name=None):
    app_name = app_name or os.environ.get("GA_APP_NAME") or "Generic Agent"
    home = Path.home()
    if sys.platform == "darwin":
        root = home / "Library" / "Application Support" / app_name
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
        root = base / app_name
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (home / ".local" / "share"))
        root = base / app_name
    return ensure_dir(root)


def workspace_root_dir(current_workspace=None):
    root = current_workspace or os.environ.get("GA_WORKSPACE_ROOT") or os.environ.get("GA_USER_DATA_DIR")
    if not root:
        root = app_root_dir() / "workspace"
    root = normalize_workspace_root(root)
    if root is None:
        root = app_root_dir() / "workspace"
    return ensure_dir(root)


def config_dir_name():
    name = os.environ.get("GA_CONFIG_DIRNAME")
    return name if isinstance(name, str) and name else "ga_config"


def normalize_workspace_root(path):
    if not isinstance(path, (str, os.PathLike)) or not str(path):
        return None
    root = Path(path).expanduser().resolve()
    cfg_name = config_dir_name()
    if root.name == cfg_name:
        root = root.parent
    return root


def workspace_config_dir(root=None):
    root = normalize_workspace_root(root) or workspace_root_dir()
    cfg = root / config_dir_name()
    return ensure_dir(cfg)


def app_data_dir():
    root = os.environ.get("GA_APP_DATA_DIR")
    if root:
        return ensure_dir(root)
    return app_root_dir()


def workspace_history_path():
    return app_data_dir() / "workspace_history.json"


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def temp_dir(*parts, root=None):
    base = Path(root) if root else data_dir()
    path = base.joinpath("temp", *parts)
    return ensure_dir(path)


def resource_path(*parts):
    return resource_dir().joinpath(*parts)


def mykey_candidate_paths(base=None):
    roots = []

    def add_root(value):
        if not value:
            return
        try:
            root = Path(value).expanduser().resolve()
        except Exception:
            return
        if root not in roots:
            roots.append(root)

    add_root(base or os.environ.get("GA_USER_DATA_DIR"))
    add_root(os.environ.get("GA_APP_DATA_DIR"))
    add_root(os.environ.get("GA_WORKSPACE_ROOT"))

    ga_base = os.environ.get("GA_BASE_DIR")
    if ga_base:
        add_root(ga_base)

    bundled = resource_dir()
    if bundled:
        add_root(bundled)

    backend = backend_dir()
    if backend:
        add_root(backend)

    seen = set()
    paths = []

    def add_path(path):
        try:
            ap = Path(path).expanduser().resolve()
        except Exception:
            return
        key = str(ap)
        if key not in seen:
            seen.add(key)
            paths.append(ap)

    for root in roots:
        if root.name == config_dir_name():
            candidates = [root, root.parent]
        else:
            candidates = [root / config_dir_name(), root]
        for cand_root in candidates:
            add_path(cand_root / "mykey.json")
            add_path(cand_root / "mykey.py")

    return paths


def resolve_mykey_path(base=None, prefer_existing=True):
    candidates = mykey_candidate_paths(base)
    if prefer_existing:
        for path in candidates:
            if _load_mykey_data(path):
                return path
    return candidates[0] if candidates else None


def _load_mykey_data(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        if path.suffix == ".py":
            import importlib.util
            import uuid

            mod_name = f"_mykey_probe_{uuid.uuid4().hex}"
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if not spec or not spec.loader:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            data = {k: v for k, v in vars(module).items() if not k.startswith("_")}
        else:
            import json

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        if isinstance(data, dict):
            return data or None
    except Exception:
        return None
    return None
