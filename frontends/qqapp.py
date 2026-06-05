import argparse, asyncio, json, os, sys, threading, time
from collections import deque

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)
from path_utils import workspace_root_dir, workspace_config_dir, resolve_mykey_path


def _ensure_runtime_paths():
    workspace_root = workspace_root_dir()
    config_root = workspace_config_dir(workspace_root)
    os.environ.setdefault("GA_WORKSPACE_ROOT", str(workspace_root))
    os.environ.setdefault("GA_USER_DATA_DIR", str(config_root))
    return str(workspace_root), str(config_root)


_ensure_runtime_paths()
from agentmain import GeneraticAgent
from chatapp_common import AgentChatMixin, ensure_single_instance, public_access, redirect_log, require_runtime, split_text

try:
    import botpy
    from botpy.message import C2CMessage, GroupMessage
except Exception:
    print("Please install qq-botpy to use QQ module: pip install qq-botpy")
    sys.exit(1)

agent = None
agent_error = None
agent_thread = None
PROCESSED_IDS, USER_TASKS = deque(maxlen=1000), {}
SEQ_LOCK, MSG_SEQ = threading.Lock(), 1


def _to_allowed_set(value):
    if value is None:
        return set()
    if isinstance(value, str):
        value = [value]
    return {str(x).strip() for x in value if str(x).strip()}


def _load_config():
    path = resolve_mykey_path(os.environ.get("GA_WORKSPACE_ROOT"), prefer_existing=True)
    if not path or not os.path.exists(path):
        return {}, str(path or "")
    try:
        if str(path).endswith(".py"):
            import importlib.util
            import uuid
            mod_name = f"_qq_mykey_{uuid.uuid4().hex}"
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if not spec or not spec.loader:
                return {}, str(path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            data = {k: v for k, v in vars(module).items() if not k.startswith("_")}
        else:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        return data if isinstance(data, dict) else {}, str(path)
    except Exception as e:
        print(f"[QQ] load mykey failed {path}: {e}")
        return {}, str(path)


def _qq_config():
    cfg, path = _load_config()
    app_id = str(cfg.get("qq_app_id", "") or "").strip()
    secret = str(cfg.get("qq_app_secret", "") or "").strip()
    allowed = _to_allowed_set(cfg.get("qq_allowed_users", []))
    return app_id, secret, allowed, path


APP_ID, APP_SECRET, ALLOWED, CONFIG_PATH = _qq_config()


def _mask_secret(value):
    value = str(value or "")
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def get_agent():
    global agent, agent_error, agent_thread
    if agent is not None:
        return agent
    if agent_error:
        raise RuntimeError(agent_error)
    try:
        agent = GeneraticAgent()
        agent.verbose = False
        agent_thread = threading.Thread(target=agent.run, daemon=True)
        agent_thread.start()
        return agent
    except Exception as e:
        agent_error = str(e)
        raise


def check_config(init_agent=False):
    app_id, secret, allowed, path = _qq_config()
    result = {
        "config_path": path,
        "app_id": app_id,
        "app_secret": _mask_secret(secret),
        "app_secret_present": bool(secret),
        "public_access": not allowed or "*" in allowed,
        "allowed_users": sorted(allowed),
        "ready": bool(app_id and secret),
    }
    if init_agent:
        try:
            ga = get_agent()
            result["agent_ready"] = True
            result["llm_count"] = len(ga.list_llms()) if hasattr(ga, "list_llms") else 0
            result["current_llm"] = ga.get_llm_name() if getattr(ga, "llmclient", None) else ""
        except Exception as e:
            result["agent_ready"] = False
            result["agent_error"] = str(e)
    return result


def _next_msg_seq():
    global MSG_SEQ
    with SEQ_LOCK:
        MSG_SEQ += 1
        return MSG_SEQ


def _build_intents():
    try:
        return botpy.Intents(public_messages=True, direct_message=True)
    except Exception:
        intents = botpy.Intents.none() if hasattr(botpy.Intents, "none") else botpy.Intents()
        for attr in ("public_messages", "public_guild_messages", "direct_message", "direct_messages", "c2c_message", "c2c_messages", "group_at_message", "group_at_messages"):
            if hasattr(intents, attr):
                try:
                    setattr(intents, attr, True)
                except Exception:
                    pass
        return intents


def _make_bot_class(app):
    class QQBot(botpy.Client):
        def __init__(self):
            super().__init__(intents=_build_intents(), ext_handlers=False)

        async def on_ready(self):
            print(f"[QQ] bot ready: {getattr(getattr(self, 'robot', None), 'name', 'QQBot')}")

        async def on_c2c_message_create(self, message: C2CMessage):
            await app.on_message(message, is_group=False)

        async def on_group_at_message_create(self, message: GroupMessage):
            await app.on_message(message, is_group=True)

        async def on_direct_message_create(self, message):
            await app.on_message(message, is_group=False)

    return QQBot


class QQApp(AgentChatMixin):
    label, source, split_limit = "QQ", "qq", 1500

    def __init__(self):
        super().__init__(get_agent(), USER_TASKS)
        self.client = None

    async def send_text(self, chat_id, content, *, msg_id=None, is_group=False):
        if not self.client:
            return
        api = self.client.api.post_group_message if is_group else self.client.api.post_c2c_message
        key = "group_openid" if is_group else "openid"
        for part in split_text(content, self.split_limit):
            await api(**{key: chat_id, "msg_type": 0, "content": part, "msg_id": msg_id, "msg_seq": _next_msg_seq()})

    async def on_message(self, data, is_group=False):
        try:
            msg_id = getattr(data, "id", None)
            if msg_id in PROCESSED_IDS:
                return
            PROCESSED_IDS.append(msg_id)
            content = (getattr(data, "content", "") or "").strip()
            if not content:
                return
            author = getattr(data, "author", None)
            user_id = str(getattr(author, "member_openid" if is_group else "user_openid", "") or getattr(author, "id", "") or "unknown")
            chat_id = str(getattr(data, "group_openid", "") or user_id) if is_group else user_id
            if not public_access(ALLOWED) and user_id not in ALLOWED:
                print(f"[QQ] unauthorized user: {user_id}")
                return
            print(f"[QQ] message from {user_id} ({'group' if is_group else 'c2c'}): {content}")
            if content.startswith("/"):
                return await self.handle_command(chat_id, content, msg_id=msg_id, is_group=is_group)
            asyncio.create_task(self.run_agent(chat_id, content, msg_id=msg_id, is_group=is_group))
        except Exception:
            import traceback
            print("[QQ] handle_message error")
            traceback.print_exc()

    async def start(self):
        self.client = _make_bot_class(self)()
        while True:
            try:
                print(f"[QQ] bot starting... {time.strftime('%m-%d %H:%M')}")
                await self.client.start(appid=APP_ID, secret=APP_SECRET)
            except Exception as e:
                print(f"[QQ] bot error: {e}")
            print("[QQ] reconnect in 5s...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A3Agent QQ frontend")
    parser.add_argument("--check", action="store_true", help="只检查 QQ 配置，不启动长连接")
    parser.add_argument("--check-agent", action="store_true", help="检查配置并初始化 Agent/LLM")
    args = parser.parse_args()
    if args.check or args.check_agent:
        print(json.dumps(check_config(init_agent=args.check_agent), ensure_ascii=False, indent=2), flush=True)
        sys.exit(0)

    APP_ID, APP_SECRET, ALLOWED, CONFIG_PATH = _qq_config()
    agent = get_agent()
    _LOCK_SOCK = ensure_single_instance(19528, "QQ")
    require_runtime(agent, "QQ", qq_app_id=APP_ID, qq_app_secret=APP_SECRET)
    redirect_log(__file__, "qqapp.log", "QQ", ALLOWED)
    asyncio.run(QQApp().start())
