import threading
from contextlib import contextmanager


_LOCAL = threading.local()


def set_runtime_context(username=None, workspace_root=None, user_data_dir=None):
    if username is not None:
        _LOCAL.username = username
    if workspace_root is not None:
        _LOCAL.workspace_root = workspace_root
    if user_data_dir is not None:
        _LOCAL.user_data_dir = user_data_dir


def clear_runtime_context():
    for name in ("username", "workspace_root", "user_data_dir"):
        if hasattr(_LOCAL, name):
            delattr(_LOCAL, name)


def get_runtime_value(name, default=None):
    return getattr(_LOCAL, name, default)


@contextmanager
def scoped_runtime_context(username=None, workspace_root=None, user_data_dir=None):
    prev = {
        "username": get_runtime_value("username"),
        "workspace_root": get_runtime_value("workspace_root"),
        "user_data_dir": get_runtime_value("user_data_dir"),
    }
    try:
        set_runtime_context(username=username, workspace_root=workspace_root, user_data_dir=user_data_dir)
        yield
    finally:
        clear_runtime_context()
        set_runtime_context(
            username=prev["username"],
            workspace_root=prev["workspace_root"],
            user_data_dir=prev["user_data_dir"],
        )
