import os, sys, threading, queue, time, json, re, random
import health_monitor
if sys.stdout is None: sys.stdout = open(os.devnull, "w")
elif hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(errors='replace')
if sys.stderr is None: sys.stderr = open(os.devnull, "w")
elif hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(errors='replace')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

_this_dir = os.path.dirname(os.path.abspath(__file__))
_resource_dir = os.environ.get("GA_BASE_DIR") or _this_dir
if _resource_dir.endswith(".zip") and os.path.isfile(_resource_dir):
    _resource_dir = os.path.dirname(os.path.dirname(_resource_dir))

from sidercall import SiderLLMSession, LLMSession, ToolClient, ClaudeSession, XaiSession
from agent_loop import agent_runner_loop, StepOutcome, BaseHandler
from ga import GenericAgentHandler, smart_format, get_global_memory, format_error

with open(os.path.join(_resource_dir, 'assets/tools_schema.json'), 'r', encoding='utf-8') as f:
    TS = f.read()
    TOOLS_SCHEMA = json.loads(TS if os.name == 'nt' else TS.replace('powershell', 'bash'))

def get_system_prompt():
    data_dir = _get_data_dir()
    mem_dir = os.path.join(data_dir, 'memory')
    if not os.path.exists(mem_dir): os.makedirs(mem_dir)
    mem_txt = os.path.join(mem_dir, 'global_mem.txt')
    if not os.path.exists(mem_txt):
        with open(mem_txt, 'w', encoding='utf-8') as f: f.write('')
    mem_insight = os.path.join(mem_dir, 'global_mem_insight.txt')
    if not os.path.exists(mem_insight):
        t = os.path.join(_resource_dir, 'assets/global_mem_insight_template.txt')
        open(mem_insight, 'w', encoding='utf-8').write(open(t, encoding='utf-8').read() if os.path.exists(t) else '')
    with open(os.path.join(_resource_dir, 'assets/sys_prompt.txt'), 'r', encoding='utf-8') as f: prompt = f.read()
    prompt += f"\nToday: {time.strftime('%Y-%m-%d %a')}\n"
    prompt += get_global_memory()
    return prompt

class LLMClientLogger:
    def __init__(self, real_client, log_file):
        self.real_client = real_client
        self.log_file = log_file
    def __getattr__(self, name):
        return getattr(self.real_client, name)
    def chat(self, messages, tools=None):
        start_t = time.time()
        msg_preview = str(messages[-1])[:500] if messages else ""
        log_entry = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'messages_preview': msg_preview,
            'tools_count': len(tools) if tools else 0
        }
        try:
            gen = self.real_client.chat(messages, tools)
            val = yield from gen
            log_entry['status'] = 'success'
            log_entry['response_time'] = round(time.time() - start_t, 2)
            log_entry['response_preview'] = str(getattr(val, 'content', ''))[:500]
            return val
        except Exception as e:
            log_entry['status'] = 'error'
            log_entry['error'] = str(e)
            log_entry['response_time'] = round(time.time() - start_t, 2)
            raise
        finally:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            except:
                pass

def _get_base_dir():
    try:
        from api_server import get_user_data_dir
        return get_user_data_dir()
    except:
        return os.environ.get("GA_USER_DATA_DIR") or os.getcwd()

def _get_data_dir():
    base = _get_base_dir()
    if not os.path.exists(base):
        os.makedirs(base, exist_ok=True)
    return base

class GeneraticAgent:
    def __init__(self, is_vision=False):
        # 确保目录和监控启动
        base = _get_base_dir()
        temp_dir = os.path.join(base, "temp")
        if not os.path.exists(temp_dir): os.makedirs(temp_dir)
        health_monitor.start_monitor(temp_dir)
        import importlib
        import llmcore
        importlib.reload(llmcore)
        from llmcore import mykeys
        print(f"Loaded keys count: {len(mykeys)}")
        llm_sessions = []
        for k, cfg in mykeys.items():
            if not isinstance(cfg, dict): continue
            # Check type explicitly from new json structure
            tp = cfg.get("type", "")
            try:
                if tp == "claude" or "claude" in k:
                    s = ClaudeSession(api_key=cfg['apikey'], api_base=cfg['apibase'], model=cfg['model'])
                    s.config_id = k
                    llm_sessions += [s]
                elif tp == "sider" or 'sider' in k:
                    import sidercall
                    importlib.reload(sidercall)
                    for x in ["gemini-3.0-flash", "claude-haiku-4.5", "kimi-k2"]:
                        s = sidercall.SiderLLMSession(cfg, default_model=x)
                        s.config_id = k
                        llm_sessions += [s]
                elif tp == "xai" or 'xai' in k:
                    s = XaiSession(cfg, mykeys.get('proxy', ''))
                    s.config_id = k
                    llm_sessions += [s]
                elif tp == "oai" or 'oai' in k or 'model' in k:
                    s = LLMSession(api_key=cfg['apikey'], api_base=cfg['apibase'], model=cfg['model'], proxy=cfg.get('proxy'))
                    s.config_id = k
                    llm_sessions += [s]
            except Exception as e:
                print(f"[WARN] Failed to load config {k}: {e}")
        if len(llm_sessions) > 0: 
            self.llmclient = ToolClient(llm_sessions, auto_save_tokens=True)
            self.llmclient = LLMClientLogger(self.llmclient, os.path.join(temp_dir, 'model_calls.log'))
        else: self.llmclient = None
        self.lock = threading.Lock()
        self.history = []               
        self.task_queue = queue.Queue() 
        self.is_running, self.stop_sig = False, False
        self.llm_no = 0
        self.inc_out = False
        self.handler = None
        self.verbose = True
        self.max_history_items = int(os.environ.get("GA_MAX_HISTORY_ITEMS") or 80)
        self.max_history_chars = int(os.environ.get("GA_MAX_HISTORY_CHARS") or 240000)

    def reload_config(self):
        """重新加载模型配置"""
        import llmcore
        import importlib
        importlib.reload(llmcore)
        from llmcore import mykeys
        
        llm_sessions = []
        for k, cfg in mykeys.items():
            if not isinstance(cfg, dict): continue
            tp = cfg.get("type", "")
            try:
                if tp == "claude" or "claude" in k:
                    s = llmcore.ClaudeSession(api_key=cfg['apikey'], api_base=cfg['apibase'], model=cfg['model'])
                    s.config_id = k
                    llm_sessions += [s]
                elif tp == "sider" or 'sider' in k:
                    import sidercall
                    importlib.reload(sidercall)
                    for x in ["gemini-3.0-flash", "claude-haiku-4.5", "kimi-k2"]:
                        s = sidercall.SiderLLMSession(cfg, default_model=x)
                        s.config_id = k
                        llm_sessions += [s]
                elif tp == "xai" or 'xai' in k:
                    s = llmcore.XaiSession(cfg, mykeys.get('proxy', ''))
                    s.config_id = k
                    llm_sessions += [s]
                elif tp == "oai" or 'oai' in k or 'model' in k:
                    s = llmcore.LLMSession(api_key=cfg['apikey'], api_base=cfg['apibase'], model=cfg['model'], proxy=cfg.get('proxy'))
                    s.config_id = k
                    llm_sessions += [s]
            except Exception as e:
                print(f"[WARN] Failed to load config {k}: {e}")
                
        if len(llm_sessions) > 0:
            base = _get_base_dir()
            temp_dir = os.path.join(base, "temp")
            self.llmclient = llmcore.ToolClient(llm_sessions, auto_save_tokens=True)
            self.llmclient = LLMClientLogger(self.llmclient, os.path.join(temp_dir, 'model_calls.log'))
        else:
            self.llmclient = None

    def next_llm(self, n=-1):
        self.llm_no = ((self.llm_no + 1) if n < 0 else n) % len(self.llmclient.backends)
        self.llmclient.last_tools = ''
    def list_llms(self): return [(i, f"{type(b).__name__}/{b.default_model}", i == self.llm_no, getattr(b, "config_id", None)) for i, b in enumerate(self.llmclient.backends)]
    def get_llm_name(self):
        b = self.llmclient.backends[self.llm_no]
        return f"{type(b).__name__}/{b.default_model}"

    def abort(self):
        print('Abort current task...')
        if not self.is_running: return
        self.stop_sig = True
        try:
            backend = getattr(getattr(self, "llmclient", None), "backend", None)
            if backend is not None and hasattr(backend, "cancel"):
                backend.cancel()
        except Exception:
            pass
        if self.handler is not None: 
            self.handler.code_stop_signal.append(1)
            
    def clear_history(self):
        self.history = []
        if self.handler:
            self.handler.history_info = []
            self.handler.key_info = ""
        # Clear backend memory
        if self.llmclient and hasattr(self.llmclient, 'backends'):
            for b in self.llmclient.backends:
                if hasattr(b, 'raw_msgs'):
                    b.raw_msgs = []
                if hasattr(b, 'messages'):
                    b.messages = []
                if hasattr(b, 'reset'):
                    try: b.reset()
                    except: pass

    def _trim_history(self, history):
        try:
            if not isinstance(history, list):
                return history
            max_items = max(4, int(self.max_history_items))
            max_chars = max(2000, int(self.max_history_chars))
            if len(history) > max_items:
                history = history[-max_items:]
            total = 0
            kept = []
            for item in reversed(history):
                s = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                total += len(s)
                if total > max_chars and len(kept) >= 2:
                    break
                kept.append(item)
            return list(reversed(kept))
        except Exception:
            return history
                
    def put_task(self, query, source="user"):
        display_queue = queue.Queue()
        self.task_queue.put({"query": query, "source": source, "output": display_queue})
        return display_queue

    def run(self):
        while True:
            task = self.task_queue.get()
            self.is_running = True
            raw_query, source, display_queue = task["query"], task["source"], task["output"]
            rquery = smart_format(raw_query.replace('\n', ' '), max_str_len=200)
            self.history.append(f"[USER]: {rquery}")
            self.history = self._trim_history(self.history)
            
            sys_prompt = get_system_prompt()
            handler = GenericAgentHandler(None, self.history, os.path.join(_get_data_dir(), 'temp'))
            if self.handler and self.handler.key_info: 
                handler.key_info = self.handler.key_info
                if '清除工作记忆' not in handler.key_info:
                    handler.key_info += '\n[SYSTEM] 如果是新任务，请先更新或清除工作记忆\n'
            self.handler = handler
            self.llmclient.backend = self.llmclient.backends[self.llm_no]
            gen = agent_runner_loop(self.llmclient, sys_prompt, raw_query, 
                                handler, TOOLS_SCHEMA, max_turns=40, verbose=self.verbose)
            try:
                full_resp = ""
                full_parts = []
                pending = ""
                flush_chars = 200
                for chunk in gen:
                    if self.stop_sig:
                        try:
                            gen.close()
                        except Exception:
                            pass
                        break
                    if chunk:
                        full_parts.append(chunk)
                        pending += chunk
                    if len(pending) >= flush_chars:
                        out = pending if self.inc_out else ''.join(full_parts)
                        display_queue.put({'next': out, 'source': source})
                        pending = ""
                if pending:
                    out = pending if self.inc_out else ''.join(full_parts)
                    display_queue.put({'next': out, 'source': source})
                full_resp = ''.join(full_parts)
                if '</summary>' in full_resp: full_resp = full_resp.replace('</summary>', '</summary>\n\n')
                if '</file_content>' in full_resp: full_resp = re.sub(r'<file_content>\s*(.*?)\s*</file_content>', r'\n````\n<file_content>\n\1\n</file_content>\n````', full_resp, flags=re.DOTALL)                
                display_queue.put({'done': full_resp, 'source': source})
                self.history = self._trim_history(handler.history_info)
            except Exception as e:
                print(f"Backend Error: {format_error(e)}")
                display_queue.put({'done': full_resp + f'\n```\n{format_error(e)}\n```', 'source': source})
            finally:
                self.is_running = self.stop_sig = False
                self.task_queue.task_done()
                if self.handler is not None: self.handler.code_stop_signal.append(1)

    
def start_scheduled_scheduler(llm_no=0):
    from datetime import datetime
    agent = GeneraticAgent()
    agent.llm_no = llm_no
    agent.verbose = False
    threading.Thread(target=agent.run, daemon=True).start()

    def drain(dq, tag):
        while True:
            item = dq.get()
            if 'done' in item:
                break
        open(os.path.join(_get_data_dir(), 'temp/scheduler.log'), 'a', encoding='utf-8').write(
            f'[{datetime.now():%m-%d %H:%M}] {tag}\n{item["done"]}\n\n'
        )

    def loop():
        while True:
            time.sleep(55 + random.random() * 10)
            now = datetime.now()
            pending_dir = os.path.join(_get_data_dir(), 'sche_tasks/pending')
            if not os.path.isdir(pending_dir):
                continue
            for f in os.listdir(pending_dir):
                m = re.match(r'(\d{4}-\d{2}-\d{2})_(\d{4})_', f)
                if m and now >= datetime.strptime(f'{m[1]} {m[2]}', '%Y-%m-%d %H%M'):
                    task_path = os.path.join(pending_dir, f)
                    raw = open(task_path, encoding='utf-8').read()
                    dq = agent.put_task(
                        f'按scheduled_task_sop执行任务文件 {task_path}（立刻移到running）\n内容：\n{raw}',
                        source='scheduler',
                    )
                    threading.Thread(target=drain, args=(dq, f), daemon=True).start()
                    break

    threading.Thread(target=loop, daemon=True).start()
    return agent


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--scheduled', action='store_true', help='计划任务轮询模式')
    parser.add_argument('--task', metavar='IODIR', help='一次性任务模式(文件IO)')
    parser.add_argument('--llm_no', type=int, default=0, help='LLM编号')
    args = parser.parse_args()

    if args.scheduled:
        start_scheduled_scheduler(llm_no=args.llm_no)
        while True:
            time.sleep(3600)
    else:
        agent = GeneraticAgent()
        agent.llm_no = args.llm_no
        agent.verbose = False
        threading.Thread(target=agent.run, daemon=True).start()

    if args.task:
        d = os.path.join(_get_data_dir(), f'temp/{args.task}'); rp = os.path.join(d, 'reply.txt'); nround = ''
        with open(os.path.join(d, 'input.txt'), encoding='utf-8') as f: raw = f.read()
        while True:
            dq = agent.put_task(raw, source='task')
            while True:
                item = dq.get(timeout=120)
                if 'done' in item: break
                if 'next' in item and random.random() < 0.05:  # 1/20的概率写一次中间结果
                    with open(os.path.join(d, f'output{nround}.txt'), 'w', encoding='utf-8') as f: f.write(item.get('next', ''))
            with open(os.path.join(d, f'output{nround}.txt'), 'w', encoding='utf-8') as f: f.write(item['done'] + '\n[ROUND END]\n')
            for _ in range(150):  # 等reply.txt，5分钟超时
                time.sleep(2)
                if os.path.exists(rp):
                    with open(rp, encoding='utf-8') as f: raw = f.read()
                    os.remove(rp); break
            else: break
            nround = int(nround) + 1 if nround.isdigit() else 1
    else:
        agent.inc_out = True
        while True:
            q = input('> ').strip()
            if not q: continue
            try:
                dq = agent.put_task(q, source='user')
                while True:
                    item = dq.get()
                    if 'next' in item: print(item['next'], end='', flush=True)
                    if 'done' in item: print(); break
            except KeyboardInterrupt:
                agent.abort()
                print('\n[Interrupted]')
