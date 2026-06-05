"""Per-thread LLM token usage via llmcore monkey-patches."""
from __future__ import annotations
import glob
import os
import re
import threading
import time
from dataclasses import dataclass, field


@dataclass
class TokenStats:
    requests: int = 0
    input: int = 0
    output: int = 0
    cache_create: int = 0
    cache_read: int = 0
    last_input: int = 0
    last_output: int = 0
    started_at: float = field(default_factory=time.time)

    def total_input_side(self) -> int:
        return self.input + self.cache_create + self.cache_read

    def total_tokens(self) -> int:
        return self.input + self.output + self.cache_create + self.cache_read

    def cache_hit_rate(self) -> float:
        side = self.total_input_side()
        return (self.cache_read / side * 100.0) if side else 0.0

    def elapsed_seconds(self) -> float:
        return max(0.0, time.time() - self.started_at)


def context_window_chars(backend) -> int:
    try:
        return int(getattr(backend, 'context_win', 0)) * 3
    except (TypeError, ValueError):
        return 0


def current_input_chars(backend) -> int:
    try:
        import json as _json
        history = getattr(backend, 'history', None) or []
        return sum(len(_json.dumps(m, ensure_ascii=False)) for m in history)
    except Exception:
        return 0


_trackers: dict[str, TokenStats] = {}
_lock = threading.Lock()
_OUT_RE = re.compile(r'\[Output\]\s+tokens=(\d+)')
_CACHE_RE_NEW = re.compile(r'\[Cache\]\s+input=(\d+)\s+creation=(\d+)\s+read=(\d+)')
_CACHE_RE_OLD = re.compile(r'\[Cache\]\s+input=(\d+)\s+cached=(\d+)')
_INSTALLED = False
_SUBAGENT_GLOB = os.path.join("temp", "*", "stdout.log")


def scan_subagent_logs(since: float = 0.0, root: str | None = None) -> TokenStats:
    out = TokenStats()
    if since > 0:
        out.started_at = since
    pattern = os.path.join(root, _SUBAGENT_GLOB) if root else _SUBAGENT_GLOB
    for p in glob.glob(pattern):
        try:
            if since and os.path.getmtime(p) < since:
                continue
            with open(p, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("[Output]"):
                        m = _OUT_RE.match(line)
                        if m:
                            out.output += int(m.group(1))
                            out.requests += 1
                    elif line.startswith("[Cache]"):
                        m = _CACHE_RE_NEW.match(line)
                        if m:
                            i, c, r = int(m.group(1)), int(m.group(2)), int(m.group(3))
                            out.input += i
                            out.cache_create += c
                            out.cache_read += r
                            continue
                        m = _CACHE_RE_OLD.match(line)
                        if m:
                            i, r = int(m.group(1)), int(m.group(2))
                            out.input += max(0, i - r)
                            out.cache_read += r
        except OSError:
            continue
    return out


def get(thread_name: str) -> TokenStats:
    with _lock:
        if thread_name not in _trackers:
            _trackers[thread_name] = TokenStats()
        return _trackers[thread_name]


def reset(thread_name: str) -> None:
    with _lock:
        _trackers.pop(thread_name, None)


def all_trackers() -> dict[str, TokenStats]:
    with _lock:
        return dict(_trackers)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    import llmcore
    orig_record, orig_print = llmcore._record_usage, print

    def record_patched(usage, api_mode):
        try:
            if usage:
                t = get(threading.current_thread().name)
                t.requests += 1
                if api_mode == 'messages':
                    inp = int(usage.get('input_tokens', 0) or 0)
                    cc = int(usage.get('cache_creation_input_tokens', 0) or 0)
                    cr = int(usage.get('cache_read_input_tokens', 0) or 0)
                    t.input += inp
                    t.cache_create += cc
                    t.cache_read += cr
                    out = int(usage.get('output_tokens', 0) or 0)
                    if out > 1:
                        t.output += out
                        t.last_output = out
                    t.last_input = inp + cc + cr
                elif api_mode == 'chat_completions':
                    cached = int((usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0) or 0)
                    inp = int(usage.get('prompt_tokens', 0) or 0) - cached
                    t.input += inp
                    t.cache_read += cached
                    t.last_input = inp + cached
                elif api_mode == 'responses':
                    cached = int((usage.get('input_tokens_details') or {}).get('cached_tokens', 0) or 0)
                    inp = int(usage.get('input_tokens', 0) or 0) - cached
                    t.input += inp
                    t.cache_read += cached
                    t.last_input = inp + cached
        except Exception:
            pass
        return orig_record(usage, api_mode)

    llmcore._record_usage = record_patched

    def print_patched(*args, **kwargs):
        try:
            if args and isinstance(args[0], str):
                m = _OUT_RE.match(args[0])
                if m:
                    t = get(threading.current_thread().name)
                    n = int(m.group(1))
                    t.output += n
                    t.last_output = n
        except Exception:
            pass
        return orig_print(*args, **kwargs)

    llmcore.print = print_patched
    _INSTALLED = True
