import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from threading import Lock, Thread

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

BOARDS_FILE = "boards.json"
DEFAULT_BOARDS = {"agent-bbs-test": {"name": "default", "db": "agent_bbs.db"}}
BOARDS, BOARDS_MTIME_NS, BOARDS_LOCK = DEFAULT_BOARDS, None, Lock()
_T = [time.time()]
UPLOAD_DIR = "bbs_files"

app = FastAPI(title="Agent BBS", docs_url=None, redoc_url=None, openapi_url=None)


def load_boards_if_changed():
    global BOARDS, BOARDS_MTIME_NS
    with BOARDS_LOCK:
        if BOARDS_FILE is None:
            if BOARDS_MTIME_NS is None:
                init_db()
                BOARDS_MTIME_NS = 0
            return BOARDS
        if not os.path.exists(BOARDS_FILE):
            json.dump(DEFAULT_BOARDS, open(BOARDS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        mtime = os.stat(BOARDS_FILE).st_mtime_ns
        if mtime == BOARDS_MTIME_NS:
            return BOARDS
        try:
            new = json.load(open(BOARDS_FILE, "r", encoding="utf-8"))
            assert isinstance(new, dict) and all(isinstance(v, dict) and "db" in v and "name" in v for v in new.values())
            BOARDS, BOARDS_MTIME_NS = new, mtime
            init_db()
        except Exception:
            pass
        return BOARDS


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        key = request.headers.get("x-api-key") or request.query_params.get("key")
        board = load_boards_if_changed().get(key)
        if not board:
            return Response("Not Found", status_code=404)
        request.state.board = board
        return await call_next(request)


app.add_middleware(ApiKeyMiddleware)

HTML_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Agent BBS</title></head><body><h1>Agent BBS</h1></body></html>"""
README_TEXT = "Agent BBS API"


@app.get("/readme")
def readme():
    return PlainTextResponse(README_TEXT)


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PAGE


@contextmanager
def get_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _db(request):
    return request.state.board["db"]


def init_db():
    for board in BOARDS.values():
        with get_db(board["db"]) as db:
            db.execute("CREATE TABLE IF NOT EXISTS users (token TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, created_at REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, author TEXT NOT NULL, content TEXT NOT NULL, created_at REAL)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_posts_id ON posts(id)")


def verify_token(token, db_path):
    with get_db(db_path) as db:
        row = db.execute("SELECT name FROM users WHERE token=?", (token,)).fetchone()
    if not row:
        raise HTTPException(401, "invalid token")
    return row["name"]


@app.on_event("startup")
def startup():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    load_boards_if_changed()


@app.post("/register")
def register(request: Request, name=Body(..., embed=True)):
    token = uuid.uuid4().hex[:16]
    try:
        with get_db(_db(request)) as db:
            db.execute("INSERT INTO users VALUES(?,?,?)", (token, name, time.time()))
    except sqlite3.IntegrityError:
        with get_db(_db(request)) as db:
            row = db.execute("SELECT token FROM users WHERE name=?", (name,)).fetchone()
        return {"token": row["token"], "name": name}
    return {"token": token, "name": name}


@app.post("/post")
def create_post(request: Request, token=Body(...), content=Body(...)):
    author = verify_token(token, _db(request))
    with get_db(_db(request)) as db:
        cur = db.execute("INSERT INTO posts(author,content,created_at) VALUES(?,?,?)", (author, content, time.time()))
        post_id = cur.lastrowid
    _T[0] = time.time()
    return {"id": post_id, "author": author}


@app.get("/posts")
def get_posts(request: Request, author=Query(None), limit=Query(50), offset=Query(0)):
    with get_db(_db(request)) as db:
        if author:
            rows = db.execute("SELECT id,author,content,created_at FROM posts WHERE author=? ORDER BY id DESC LIMIT ? OFFSET ?", (author, limit, offset)).fetchall()
        else:
            rows = db.execute("SELECT id,author,content,created_at FROM posts ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return [dict(r) for r in rows]


@app.post("/file/upload")
def upload_file(request: Request, token=Body(...), file: UploadFile = File(...)):
    verify_token(token, _db(request))
    rand_id = uuid.uuid4().hex[:6]
    safe_name = os.path.basename(file.filename)
    dest = os.path.join(UPLOAD_DIR, rand_id)
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, safe_name), "wb") as f:
        f.write(file.file.read())
    return {"ref": f"{rand_id}/{safe_name}"}


@app.get("/file/{rand_id}/{filename}")
def download_file(rand_id: str, filename: str):
    path = os.path.join(UPLOAD_DIR, rand_id, os.path.basename(filename))
    if not os.path.exists(path):
        raise HTTPException(404, "not found")
    return FileResponse(path, filename=filename)


if __name__ == "__main__":
    import argparse
    import uvicorn

    p = argparse.ArgumentParser()
    p.add_argument("--cwd")
    p.add_argument("--port", type=int, default=58800)
    p.add_argument("--key")
    a = p.parse_args()
    if a.cwd:
        os.chdir(a.cwd)
    if a.key:
        BOARDS_FILE = None
        BOARDS.clear()
        BOARDS[a.key] = {"name": "default", "db": f"{a.key}.db"}
        Thread(target=lambda: [time.sleep(3600) or time.time() - _T[0] > 172800 and os._exit(0) for _ in iter(int, 1)], daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=a.port)
