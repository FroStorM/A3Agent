import importlib
import os
import sys

_registry = {}
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def register(event):
    def decorator(fn):
        _registry.setdefault(event, []).append(fn)
        return fn
    return decorator


def trigger(event, ctx: dict):
    for fn in _registry.get(event, []):
        try:
            ret = fn(ctx)
            if isinstance(ret, dict):
                ctx = ret
        except Exception as e:
            sys.stderr.write(f"[hooks] {event} callback error: {e}\n")
    return ctx


def unregister(event, fn):
    try:
        _registry[event] = [f for f in _registry[event] if f is not fn]
    except KeyError:
        pass


def clear(event=None):
    if event:
        _registry.pop(event, None)
    else:
        _registry.clear()


def has(event):
    return bool(_registry.get(event))


def load(name, reload=False):
    try:
        mod_name = f"plugins.{name}"
        if reload and mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])
        else:
            importlib.import_module(mod_name)
        return True
    except Exception as e:
        sys.stderr.write(f"[hooks] plugin '{name}' load failed: {e}\n")
        return False


def discover_and_load(plugin_dir=None, reload=False):
    if plugin_dir is None:
        plugin_dir = os.path.join(_PROJECT_ROOT, "plugins")
    if not os.path.isdir(plugin_dir):
        return
    parent = os.path.dirname(plugin_dir)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    for fn in sorted(os.listdir(plugin_dir)):
        if fn.startswith("_") or not fn.endswith(".py") or fn == "hooks.py":
            continue
        load(fn[:-3], reload=reload)
