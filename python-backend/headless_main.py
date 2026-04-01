import threading, sys, time, os, atexit, socket, runpy

# 初始化配置文件 - 必须在导入其他模块之前完成
from config_manager import initialize_workspace_config
workspace_root = initialize_workspace_config()
# 环境变量已在initialize_workspace_config中设置

def find_free_port():
    sock = socket.socket()
    try:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]
    finally:
        sock.close()

def start_api_server(port):
    import uvicorn
    from api_server import app as fastapi_app
    uvicorn.run(
        fastapi_app,
        host="127.0.0.1",
        port=int(port),
        log_level="warning",
    )


def start_script(script_filename):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, script_filename)
    runpy.run_path(script_path, run_name="__main__")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('port', nargs='?', default='0')
    parser.add_argument('--tg', action='store_true', help='启动 Telegram Bot')
    parser.add_argument('--qq', action='store_true', help='启动 QQ Bot')
    parser.add_argument('--feishu', '--fs', dest='feishu', action='store_true', help='启动 Feishu Bot')
    parser.add_argument('--wecom', action='store_true', help='启动 WeCom Bot')
    parser.add_argument('--dingtalk', '--dt', dest='dingtalk', action='store_true', help='启动 DingTalk Bot')
    parser.add_argument('--no-sched', action='store_true', help='不启动计划任务调度器')
    parser.add_argument('--llm_no', type=int, default=0, help='LLM编号')
    args = parser.parse_args()
    
    port = str(find_free_port()) if args.port == '0' else args.port
    print(f'[Launch] Using port {port}')
    
    threading.Thread(target=start_api_server, args=(port,), daemon=True).start()

    if args.tg:
        threading.Thread(target=start_script, args=("tgapp.py",), daemon=True).start()
        print('[Launch] Telegram Bot started')
    else: print('[Launch] Telegram Bot not enabled (use --tg to start)')

    if args.qq:
        threading.Thread(target=start_script, args=("qqapp.py",), daemon=True).start()
        print('[Launch] QQ Bot started')
    else: print('[Launch] QQ Bot not enabled (use --qq to start)')

    if args.feishu:
        threading.Thread(target=start_script, args=("fsapp.py",), daemon=True).start()
        print('[Launch] Feishu Bot started')
    else: print('[Launch] Feishu Bot not enabled (use --feishu to start)')

    if args.wecom:
        threading.Thread(target=start_script, args=("wecomapp.py",), daemon=True).start()
        print('[Launch] WeCom Bot started')
    else: print('[Launch] WeCom Bot not enabled (use --wecom to start)')

    if args.dingtalk:
        threading.Thread(target=start_script, args=("dingtalkapp.py",), daemon=True).start()
        print('[Launch] DingTalk Bot started')
    else: print('[Launch] DingTalk Bot not enabled (use --dingtalk to start)')
    
    if not args.no_sched:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM); sock.bind(('127.0.0.1', 45762)); sock.listen(1)
            import agentmain
            agentmain.start_scheduled_scheduler(llm_no=args.llm_no)
            atexit.register(sock.close)
            print('[Launch] Task Scheduler started')
        except OSError:
            print('[Launch] Task Scheduler already running (port occupied)')
    else: print('[Launch] Task Scheduler disabled (--no-sched)')

    print(f'PORT:{port}', flush=True)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("[Launch] Exiting...")
