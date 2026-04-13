import os
import sys
import threading
import time
import subprocess
import webbrowser
from uvicorn import run

# 1. Start the API Server in a separate thread
def start_server():
    # We use os.system or subprocess to run the start script to ensure clean environment
    # Or import app and run uvicorn programmatically. 
    # Let's run programmatically to avoid complex process management
    try:
        from api_server import app
        run(app, host="0.0.0.0", port=8000, log_level="error")
    except Exception as e:
        print(f"Error starting server: {e}")

server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()

print("Waiting for server to start...")
time.sleep(2) # Wait a bit for server to be ready

URL = "http://localhost:8000"

# 2. Try to launch in "App Mode" (Independent Window)

# Option A: pywebview (Best native-like experience)
try:
    import webview
    print("Launching with pywebview...")
    webview.create_window('Cowork AI', URL, width=1200, height=800)
    webview.start()
    sys.exit(0)
except ImportError:
    print("pywebview not found. Falling back to Browser App Mode.")

# Option B: Chrome/Edge in App Mode
def find_browser_path():
    # Common macOS paths for Chrome/Edge
    paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

browser_path = find_browser_path()

if browser_path:
    print(f"Launching with {browser_path} in App Mode...")
    subprocess.Popen([browser_path, f"--app={URL}"])
    
    # Keep script running to keep server alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
else:
    # Option C: Default Browser (Tab)
    print("No compatible browser found for App Mode. Opening in default browser...")
    webbrowser.open(URL)
    
    # Keep script running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
