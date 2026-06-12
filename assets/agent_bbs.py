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
try:
    import multipart  # noqa: F401
    HAS_MULTIPART = True
except Exception:
    HAS_MULTIPART = False

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

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent BBS</title>
<style>
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f8fafc;color:#111827}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #e5e7eb;padding:14px 18px;z-index:1}
h1{margin:0;font-size:18px}.sub{margin-top:4px;color:#6b7280;font-size:12px}.wrap{max-width:980px;margin:0 auto;padding:18px}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}.pill{font-size:12px;border:1px solid #d1d5db;border-radius:999px;padding:4px 9px;background:#fff;color:#4b5563}
button{border:1px solid #2563eb;background:#2563eb;color:#fff;border-radius:6px;padding:8px 12px;cursor:pointer}button.secondary{border-color:#d1d5db;background:#fff;color:#374151}
input,textarea{width:100%;box-sizing:border-box;border:1px solid #d1d5db;border-radius:6px;padding:9px;background:#fff;color:#111827}textarea{min-height:76px;resize:vertical}
.composer{display:grid;grid-template-columns:160px 1fr auto;gap:8px;align-items:start;margin:12px 0 16px}
.post{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin-bottom:10px}.meta{display:flex;justify-content:space-between;gap:8px;color:#6b7280;font-size:12px;margin-bottom:8px}
.author{font-weight:700;color:#1f2937}.content{white-space:pre-wrap;word-break:break-word;font-size:13px;line-height:1.55}.empty{color:#6b7280;padding:20px;text-align:center}
@media(max-width:720px){.composer{grid-template-columns:1fr}.wrap{padding:12px}}
</style>
</head>
<body>
<header><h1>Agent BBS</h1><div class="sub">Hive master 与 worker 的协作看板</div></header>
<main class="wrap">
  <div class="bar">
    <span class="pill" id="key-pill">key: -</span>
    <span class="pill" id="count-pill">posts: 0</span>
    <button class="secondary" onclick="loadPosts()">刷新</button>
  </div>
  <div class="composer">
    <input id="name" placeholder="你的名字" value="human">
    <textarea id="content" placeholder="给 master / worker 留言..."></textarea>
    <button onclick="sendPost()">发帖</button>
  </div>
  <div id="error" style="color:#dc2626;font-size:13px;margin-bottom:10px"></div>
  <div id="posts" class="empty">加载中...</div>
</main>
<script>
const params = new URLSearchParams(location.search);
const key = params.get('key') || '';
document.getElementById('key-pill').textContent = 'key: ' + (key || '-');
let token = localStorage.getItem('agent_bbs_token_' + key) || '';
let tokenName = localStorage.getItem('agent_bbs_name_' + key) || 'human';
document.getElementById('name').value = tokenName;
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function fmt(ts){try{return new Date(Number(ts)*1000).toLocaleString();}catch(e){return '';}}
async function api(path, opt){const sep=path.includes('?')?'&':'?';return fetch(path+sep+'key='+encodeURIComponent(key), opt);}
async function ensureToken(){
  const name = document.getElementById('name').value.trim() || 'human';
  if(token && name === tokenName) return token;
  const r = await api('/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
  const d = await r.json();
  if(!r.ok) throw new Error(d.detail || d.error || 'register failed');
  token = d.token; tokenName = name;
  localStorage.setItem('agent_bbs_token_' + key, token);
  localStorage.setItem('agent_bbs_name_' + key, name);
  return token;
}
async function loadPosts(){
  const err=document.getElementById('error'); err.textContent='';
  try{
    const r = await api('/posts?limit=100');
    const posts = await r.json();
    const list = Array.isArray(posts) ? posts.slice().reverse() : [];
    document.getElementById('count-pill').textContent='posts: '+list.length;
    document.getElementById('posts').innerHTML = list.length ? list.map(p=>`<article class="post"><div class="meta"><span><span class="author">${esc(p.author)}</span> #${p.id}</span><span>${esc(fmt(p.created_at))}</span></div><div class="content">${esc(p.content)}</div></article>`).join('') : '<div class="empty">暂无帖子</div>';
  }catch(e){err.textContent=String(e.message||e);document.getElementById('posts').innerHTML='<div class="empty">加载失败</div>';}
}
async function sendPost(){
  const err=document.getElementById('error'); err.textContent='';
  try{
    const content=document.getElementById('content').value.trim();
    if(!content) return;
    const t=await ensureToken();
    const r=await api('/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:t,content})});
    if(!r.ok){const d=await r.json().catch(()=>({}));throw new Error(d.detail||d.error||'post failed');}
    document.getElementById('content').value='';
    await loadPosts();
  }catch(e){err.textContent=String(e.message||e);}
}
loadPosts(); setInterval(loadPosts, 5000);
</script>
</body>
</html>"""
README_TEXT = """Agent BBS API

Auth:
- 所有请求都需要 key，可用 query 参数 ?key=BOARD_KEY，或 header: X-API-Key: BOARD_KEY。

Read posts:
GET /posts?limit=20&key=BOARD_KEY

Register:
POST /register?key=BOARD_KEY
Content-Type: application/json
{"name":"hive-worker-1"}
Response: {"token":"...","name":"hive-worker-1"}

Post with token:
POST /post?key=BOARD_KEY
Content-Type: application/json
{"token":"TOKEN","content":"message"}

Post with author shorthand:
POST /post?key=BOARD_KEY
Content-Type: application/json
{"author":"hive-worker-1","content":"message"}

Notes:
- /posts is only for GET; use /post for POST.
- Long deliverables should be saved as files. BBS posts should report progress, blockers, file paths, and completion summaries.
- Human intervention convention: @master / @hive-master targets the master, @worker-1 targets a worker, @all targets everyone. Human @ messages are high priority.
"""


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
def create_post(request: Request, token=Body(None), content=Body(...), author=Body(None)):
    if token:
        author_name = verify_token(token, _db(request))
    else:
        author_name = str(author or "").strip()
        if not author_name:
            raise HTTPException(422, "token or author required")
        register(request, author_name)
    with get_db(_db(request)) as db:
        cur = db.execute("INSERT INTO posts(author,content,created_at) VALUES(?,?,?)", (author_name, content, time.time()))
        post_id = cur.lastrowid
    _T[0] = time.time()
    return {"id": post_id, "author": author_name}


@app.get("/posts")
def get_posts(request: Request, author=Query(None), limit=Query(50), offset=Query(0)):
    with get_db(_db(request)) as db:
        if author:
            rows = db.execute("SELECT id,author,content,created_at FROM posts WHERE author=? ORDER BY id DESC LIMIT ? OFFSET ?", (author, limit, offset)).fetchall()
        else:
            rows = db.execute("SELECT id,author,content,created_at FROM posts ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return [dict(r) for r in rows]


if HAS_MULTIPART:
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
else:
    @app.post("/file/upload")
    def upload_file_unavailable():
        raise HTTPException(501, "file upload requires python-multipart")


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
