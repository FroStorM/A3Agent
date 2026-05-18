# Frontend/Backend Split

This project now uses the GA_APP frontend as a fixed static UI and the current
GenericAgent Python files as the backend core.

## Runtime

Start the decoupled app from the project root:

```bash
python3 launch_app.py
```

Or run only the API/static web server:

```bash
python3 api_server.py
```

The server listens on `http://localhost:8000`. Static frontend files are served
from `frontend/`; API endpoints are under `/api/*`.

## Maintenance Boundary

- Keep `frontend/` stable unless the API contract changes intentionally.
- Backend developers can replace root-level `*.py` files such as `ga.py`,
  `agentmain.py`, `agent_loop.py`, `llmcore.py`, and related backend modules.
- SOP files are read directly from `memory/`, so replacing `memory/*_sop.md`
  files takes effect without changing the frontend.
- User LLM configuration is stored under the app workspace `ga_config` via the
  `/api/config/mykey` and `/api/llm_configs/*` endpoints.

## Frontend API Contract

The fixed frontend calls these backend endpoints:

- `GET /api/status`
- `GET /api/stream`
- `POST /api/chat`
- `POST /api/control`
- `GET /api/llm_configs`
- `POST /api/llm_configs/test`
- `POST /api/llm_configs/upsert`
- `POST /api/llm_configs/delete`
- `GET /api/todo`
- `POST /api/todo`
- `GET /api/sop/list`
- `GET /api/sop/read?name=...`
- `POST /api/sop/write`
- `GET /api/schedule/list`
- `GET /api/schedule/read?bucket=...&name=...`
- `POST /api/schedule/write`
- `POST /api/schedule/delete`

