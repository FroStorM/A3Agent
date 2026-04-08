import time
import threading
import json
import os
from datetime import datetime

try:
    import psutil
except Exception:
    psutil = None

class HealthMonitor:
    def __init__(self, log_dir):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, 'system_health.log')
        self.running = False
        
    def start(self):
        if self.running: return
        self.running = True
        threading.Thread(target=self._monitor_loop, daemon=True).start()
        
    def stop(self):
        self.running = False
        
    def get_gpu_usage(self):
        # Dummy GPU check for macos, or try to get metal stats if possible. 
        # For simplicity, returning empty dict if not available
        return {}

    def get_network_latency(self):
        try:
            start = time.time()
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return round((time.time() - start) * 1000, 2)
        except:
            return -1

    def _monitor_loop(self):
        while self.running:
            try:
                if psutil is None:
                    time.sleep(60)
                    continue
                stats = {
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'cpu_percent': psutil.cpu_percent(interval=1),
                    'memory_percent': psutil.virtual_memory().percent,
                    'memory_used_mb': psutil.virtual_memory().used / (1024*1024),
                    'network_latency_ms': self.get_network_latency()
                }
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(stats) + '\n')
            except Exception as e:
                pass
            time.sleep(60) # Log every minute

monitor = None
def start_monitor(log_dir):
    global monitor
    if psutil is None:
        return
    if monitor is None:
        monitor = HealthMonitor(log_dir)
        monitor.start()
