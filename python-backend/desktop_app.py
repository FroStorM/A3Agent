import sys
import os
import asyncio
import shutil
import threading
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QLabel, QSystemTrayIcon, QMenu, QAction, QLineEdit, QMessageBox)
from PyQt5.QtCore import Qt, QUrl, QSize, QPoint, pyqtSignal, QTimer, QRectF
from PyQt5.QtGui import QIcon, QPainter, QColor, QBrush, QCursor, QPen, QFont, QPixmap, QBitmap, QPainterPath, QRegion, QDesktopServices
import requests
import json
import urllib.request
import time
import socket
import traceback
from datetime import datetime
import uvicorn
from path_utils import app_root_dir, ensure_dir, resource_dir, temp_dir

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
STARTUP_LOG = "/tmp/a3agent-desktop.log"
APP_RESOURCE_DIR = str(resource_dir())
APP_ICON_PATH = os.path.join(APP_RESOURCE_DIR, "frontend", "app_icon_round.png")
APP_FALLBACK_ICON_PATH = os.path.join(APP_RESOURCE_DIR, "frontend", "logo-transparent.png")
APP_EFFECTIVE_ICON_PATH = APP_ICON_PATH if os.path.exists(APP_ICON_PATH) else APP_FALLBACK_ICON_PATH

def get_local_url(path=""):
    return f"http://{SERVER_HOST}:{SERVER_PORT}{path}"

def log_line(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(STARTUP_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def configure_qt_runtime(base_dir, writable_root=None):
    py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    qt5_dir = os.path.join(base_dir, "lib", py_ver, "PyQt5", "Qt5")
    if not os.path.isdir(qt5_dir):
        qt5_dir = os.path.join(base_dir, "PyQt5", "Qt5")
    qt_plugins_dir = os.path.join(qt5_dir, "plugins")
    qt_platforms_dir = os.path.join(qt_plugins_dir, "platforms")
    qt_qml_dir = os.path.join(qt5_dir, "qml")
    qt_lib_dir = os.path.join(qt5_dir, "lib")
    qtwebengine_process = os.path.join(
        qt_lib_dir,
        "QtWebEngineCore.framework", "Helpers", "QtWebEngineProcess.app",
        "Contents", "MacOS", "QtWebEngineProcess"
    )
    qtwebengine_resources = os.path.join(qt5_dir, "resources")
    qtwebengine_locales = os.path.join(qt5_dir, "translations", "qtwebengine_locales")

    def _prepend_env(name, value):
        if not value or not os.path.exists(value):
            return
        cur = os.environ.get(name)
        if cur:
            if value in cur.split(":"):
                return
            os.environ[name] = value + ":" + cur
        else:
            os.environ[name] = value

    if os.path.isdir(qt_plugins_dir):
        os.environ["QT_PLUGIN_PATH"] = qt_plugins_dir
    if os.path.isdir(qt_platforms_dir):
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = qt_platforms_dir
    if os.path.isdir(qt_qml_dir):
        os.environ["QML2_IMPORT_PATH"] = qt_qml_dir
    if os.path.isfile(qtwebengine_process):
        os.environ["QTWEBENGINEPROCESS_PATH"] = qtwebengine_process
    if os.path.isdir(qtwebengine_resources):
        os.environ["QTWEBENGINE_RESOURCES_PATH"] = qtwebengine_resources
    if os.path.isdir(qtwebengine_locales):
        os.environ["QTWEBENGINE_LOCALES_PATH"] = qtwebengine_locales
    if os.path.isdir(qt_lib_dir):
        _prepend_env("DYLD_FRAMEWORK_PATH", qt_lib_dir)
        _prepend_env("DYLD_LIBRARY_PATH", qt_lib_dir)
    if writable_root:
        qt_root = ensure_dir(os.path.join(writable_root, "qtwebengine"))
        qt_cache = ensure_dir(os.path.join(qt_root, "cache"))
        qt_profile = ensure_dir(os.path.join(qt_root, "profile"))
        os.environ["GA_QTWEBENGINE_ROOT"] = str(qt_root)
        os.environ["XDG_CACHE_HOME"] = str(qt_cache)
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
        user_data_flag = f"--user-data-dir={qt_profile}"
        if user_data_flag not in flags.split():
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (f"{flags} {user_data_flag}").strip()
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

def pick_server_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((SERVER_HOST, 0))
        return s.getsockname()[1]

UVICORN_SERVER = None
SERVER_SOCKET = None

def reserve_server_socket(port=0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((SERVER_HOST, int(port)))
    sock.listen(2048)
    return sock

def start_server():
    global SERVER_SOCKET
    try:
        log_line("start_server thread begin")
        from api_server import app
        log_line("api_server imported")
        if SERVER_SOCKET is None:
            raise RuntimeError("server socket not reserved")
        server_socket = SERVER_SOCKET
        config = uvicorn.Config(app, host=SERVER_HOST, port=SERVER_PORT, log_level="error", loop="asyncio", http="h11", ws="none", lifespan="off")
        server = uvicorn.Server(config)
        global UVICORN_SERVER
        UVICORN_SERVER = server
        asyncio.run(server.serve(sockets=[server_socket]))
        log_line("uvicorn.Server.run returned")
    except BaseException as e:
        log_line(f"Error starting server: {e}")
        log_line(traceback.format_exc())
    finally:
        try:
            if SERVER_SOCKET is not None:
                SERVER_SOCKET.close()
                SERVER_SOCKET = None
        except Exception:
            pass

def stop_server():
    try:
        global UVICORN_SERVER
        if UVICORN_SERVER is not None:
            UVICORN_SERVER.should_exit = True
    except Exception:
        pass

def on_app_quit():
    try:
        import api_server
        agent = getattr(getattr(api_server, "state", None), "agent", None)
        if agent is not None:
            try:
                agent.abort()
            except Exception:
                pass
    except Exception:
        pass
    stop_server()

def wait_for_server(timeout=10):
    start = time.time()
    last_err = None
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(get_local_url("/api/status"), timeout=1) as response:
                if response.getcode() == 200:
                    return True
        except Exception as e:
            last_err = repr(e)
            time.sleep(0.5)
    if last_err:
        log_line(f"wait_for_server last error: {last_err}")
    return False

# 2. Floating Logo Window
class FloatingLogo(QWidget):
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(70, 70) # Keep the floating button perfectly round
        self.setGeometry(100, 100, 70, 70) # Slightly larger for better visual
        
        # Load logo image
        self.logo_pixmap = QPixmap(APP_FALLBACK_ICON_PATH)
        if self.logo_pixmap.isNull():
            # Fallback if not found
            self.logo_pixmap = None

        # Enable dragging
        self.old_pos = None
        self.is_hovered = False
        self.status = "idle" # idle, running
        self.status_text = "Idle"
        
        # Timer to check status
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_status)
        self.timer.start(2000) # Check every 2 seconds
        
        # Tooltip
        self.setToolTip("A3Agent - Idle")

    def resizeEvent(self, event):
        # Force the window itself to be circular so it doesn't look like a square tile.
        try:
            self.setMask(QRegion(self.rect(), QRegion.Ellipse))
        except Exception:
            pass
        super().resizeEvent(event)

    def check_status(self):
        try:
            # Simple poll to get status
            # In a real app, maybe use a shared state object or queue if in same process
            # But HTTP request is robust enough
            import urllib.request
            with urllib.request.urlopen(get_local_url("/api/status"), timeout=1) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode())
                    is_running = data.get("is_running", False)
                    new_status = "running" if is_running else "idle"
                    if self.status != new_status:
                        self.status = new_status
                        self.status_text = "Running..." if is_running else "Idle"
                        self.setToolTip(f"A3Agent - {self.status_text}")
                        self.update() # Trigger repaint
        except Exception:
            pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Dynamic Colors
        if self.status == "running":
            bg_color = QColor("#10B981") # Emerald-500 (Green)
            border_color = QColor("#059669")
            glow_color = QColor(16, 185, 129, 100)
        else:
            bg_color = QColor("#6366F1") # Indigo-500 (Blue/Purple)
            border_color = QColor("#4F46E5")
            glow_color = QColor(99, 102, 241, 100)
            
        if self.is_hovered:
            bg_color = bg_color.lighter(110)
        
        # Draw Glow (Outer Ring)
        if self.status == "running":
            painter.setBrush(QBrush(glow_color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(2, 2, 66, 66)
            
        # Draw Main Circle
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 2))
        painter.drawEllipse(5, 5, 60, 60)
        
        # Draw Logo Image
        if self.logo_pixmap:
            path = QPainterPath()
            path.addEllipse(5, 5, 60, 60)
            painter.setClipPath(path)
            painter.drawPixmap(5, 5, 60, 60, self.logo_pixmap)
            painter.setClipping(False) # Reset clipping
        else:
            # Fallback: Draw "A3" Logo
            painter.setPen(QColor("white"))
            font = painter.font()
            font.setBold(True)
            font.setFamily("Arial")
            font.setPointSize(18)
            painter.setFont(font)
            painter.drawText(QRectF(5, 5, 60, 60), Qt.AlignCenter, "A3")
        
        # Draw Small Status Dot indicator if running
        if self.status == "running":
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(50, 10, 8, 8)

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()
            self.click_start = time.time()
            # Ensure we accept the event
            event.accept()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPos() - self.old_pos
            # Use globalPos directly for move calculation might be safer
            self.move(self.pos() + delta)
            self.old_pos = event.globalPos()
            event.accept()

    def mouseReleaseEvent(self, event):
        self.old_pos = None
        if time.time() - self.click_start < 0.2: # Short click
            self.clicked.emit()
        event.accept()

# 3. Main Window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._is_quitting = False
        self.setWindowTitle("A3Agent")
        self.resize(1200, 800)
        
        self.browser = None
        try:
            log_line("webengine import begin")
            from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile
            qt_root = os.environ.get("GA_QTWEBENGINE_ROOT")
            if qt_root:
                profile = QWebEngineProfile.defaultProfile()
                cache_path = str(ensure_dir(os.path.join(qt_root, "cache")))
                storage_path = str(ensure_dir(os.path.join(qt_root, "profile")))
                profile.setCachePath(cache_path)
                profile.setPersistentStoragePath(storage_path)
            class LoggingWebEnginePage(QWebEnginePage):
                def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
                    try:
                        log_line(f"JSConsole[{int(level)}] {sourceID}:{int(lineNumber)} {message}")
                    except Exception:
                        pass
            browser = QWebEngineView()
            browser.setPage(LoggingWebEnginePage(browser))
            browser.settings().setAttribute(browser.settings().WebAttribute.JavascriptEnabled, True)
            browser.settings().setAttribute(browser.settings().WebAttribute.LocalStorageEnabled, True)
            browser.settings().setAttribute(browser.settings().WebAttribute.PluginsEnabled, True)
            url = get_local_url("/")
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}v={int(time.time())}"
            browser.setUrl(QUrl(url))
            def _probe_theme(_ok):
                page = browser.page()
                if not page:
                    return
                js_state = "(function(){try{const html=document.documentElement;const body=document.body;const tw=window.tailwind;let cfgDarkMode=null;let twKeys=[];try{if(tw) twKeys=Object.keys(tw);}catch(_e){};try{if(tw&&tw.config&&typeof tw.config==='object') cfgDarkMode=tw.config.darkMode ?? null;}catch(_e){};let cssScan={mediaDark:0,classDark:0,hasBgRule:null};try{for(let i=0;i<document.styleSheets.length;i++){const s=document.styleSheets[i];let rules=null;try{rules=s.cssRules;}catch(_e){continue;}if(!rules)continue;for(let j=0;j<rules.length;j++){const r=rules[j];const t=(r.cssText||'');if(t.indexOf('prefers-color-scheme: dark')!==-1) cssScan.mediaDark++;if(t.indexOf('.dark .dark\\\\:')!==-1) cssScan.classDark++;if(cssScan.hasBgRule===null && t.indexOf('dark\\\\:bg-gray-900')!==-1) cssScan.hasBgRule=true;}}if(cssScan.hasBgRule===null) cssScan.hasBgRule=false;}catch(_e){};let sampleBtn=null;let sampleBtnBg=null;try{sampleBtn=document.querySelector('aside button.w-full')||document.querySelector('button');if(sampleBtn) sampleBtnBg=getComputedStyle(sampleBtn).backgroundColor;}catch(_e){};const payload={mode:localStorage.getItem('ga_theme'),dark:html.classList.contains('dark'),htmlBg:getComputedStyle(html).backgroundColor,bodyBg:body?getComputedStyle(body).backgroundColor:null,sampleBtnBg,tailwind:{type:typeof tw,keys:twKeys.slice(0,20),configDarkMode:cfgDarkMode},cssScan};return JSON.stringify(payload);}catch(e){return JSON.stringify({err:String(e)});}})();"
                def _after_before(res1):
                    log_line(f"ThemeProbe(before) {res1}")
                    page.runJavaScript("(function(){try{const b=document.getElementById('themeToggle'); if(b) b.click(); return true;}catch(e){return String(e);}})();", lambda _r: None)
                    QTimer.singleShot(300, lambda: page.runJavaScript(js_state, lambda res2: log_line(f"ThemeProbe(after) {res2}")))
                page.runJavaScript(js_state, _after_before)
            if os.environ.get("GA_THEME_PROBE") == "1":
                browser.loadFinished.connect(_probe_theme)
            self.browser = browser
            self.setCentralWidget(browser)
            log_line("webengine import ok")
        except Exception as e:
            log_line(f"webengine import fail: {e}")
            log_line(traceback.format_exc())
            w = QWidget()
            layout = QVBoxLayout(w)
            layout.setContentsMargins(24, 24, 24, 24)
            layout.setSpacing(12)
            title = QLabel("A3Agent 已启动")
            font = title.font()
            font.setPointSize(font.pointSize() + 4)
            font.setBold(True)
            title.setFont(font)
            tip = QLabel("当前环境缺少内置浏览器组件，将使用系统浏览器打开界面。")
            tip.setWordWrap(True)
            url = get_local_url("/")
            url_input = QLineEdit(url)
            url_input.setReadOnly(True)
            url_input.setMinimumHeight(28)
            btn = QPushButton("打开界面")
            btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
            copy_btn = QPushButton("复制链接")
            def _copy_url():
                QApplication.clipboard().setText(url)
                QMessageBox.information(self, "已复制", "链接已复制到剪贴板")
            copy_btn.clicked.connect(_copy_url)
            layout.addWidget(title)
            layout.addWidget(tip)
            layout.addWidget(url_input)
            layout.addWidget(btn)
            layout.addWidget(copy_btn)
            layout.addStretch(1)
            self.setCentralWidget(w)
            QTimer.singleShot(0, lambda: QDesktopServices.openUrl(QUrl(url)))
        
        # Floating Logo
        self.floating_logo = FloatingLogo()
        self.floating_logo.clicked.connect(self.restore_window)
        
        # Set Window Icon
        self.setWindowIcon(QIcon(APP_EFFECTIVE_ICON_PATH))

        # System Tray (Optional, standard for desktop apps)
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(APP_EFFECTIVE_ICON_PATH))
        
        # Menu
        tray_menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.restore_window)
        reload_action = QAction("Reload", self)
        reload_action.triggered.connect(self.reload_ui)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.graceful_quit)
        tray_menu.addAction(show_action)
        tray_menu.addAction(reload_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def graceful_quit(self):
        if self._is_quitting:
            return
        self._is_quitting = True
        try:
            import api_server
            agent = getattr(getattr(api_server, "state", None), "agent", None)
            if agent is not None:
                try:
                    agent.abort()
                except Exception:
                    pass
        except Exception:
            pass
        stop_server()
        try:
            if getattr(self, "tray_icon", None):
                self.tray_icon.hide()
        except Exception:
            pass
        try:
            if getattr(self, "floating_logo", None):
                self.floating_logo.hide()
        except Exception:
            pass
        QTimer.singleShot(50, lambda: QApplication.instance().quit())

    def reload_ui(self):
        if self.browser:
            self.browser.reload()
        else:
            QDesktopServices.openUrl(QUrl(get_local_url("/")))

    def changeEvent(self, event):
        # Override minimize event
        if event.type() == event.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                # Minimize logic: Hide main window, Show floating logo
                # We use QTimer to ensure the event is processed before we hide
                QTimer.singleShot(0, self.to_floating_mode)
        super().changeEvent(event)

    def closeEvent(self, event):
        if self._is_quitting:
            event.accept()
            return
        event.accept()
        self.graceful_quit()

    def to_floating_mode(self):
        self.hide()
        # Position floating logo near current window or last pos
        if not self.floating_logo.isVisible():
            # Default to top right or keep last pos
            screen_geo = QApplication.primaryScreen().geometry()
            self.floating_logo.move(screen_geo.width() - 100, 100)
            self.floating_logo.show()
            self.floating_logo.activateWindow() # Ensure it's active

    def restore_window(self):
        self.floating_logo.hide()
        self.showNormal()
        self.activateWindow()
        self.raise_() # Bring to front
        if self.browser:
            self.browser.setFocus()

if __name__ == "__main__":
    try:
        open(STARTUP_LOG, "w", encoding="utf-8").write("")
    except Exception:
        pass
    sys.excepthook = lambda et, ev, tb: log_line("".join(traceback.format_exception(et, ev, tb)))
    base_dir = str(resource_dir())
    log_line(f"Boot base_dir={base_dir}")

    # Determine if running in a frozen bundle
    is_frozen = getattr(sys, 'frozen', False) or "A3Agent.app" in base_dir

    if is_frozen:
        # User Data Directory (Persistent)
        if os.environ.get("AI_AGENT") == "TRAE" or os.environ.get("TRAE_SANDBOX_CLI_PATH"):
            user_data_dir = "/tmp/A3Agent"
        else:
            user_data_dir = str(app_root_dir("A3Agent"))
        ensure_dir(user_data_dir)
        
        log_line(f"Running in frozen mode. Redirecting to user data dir: {user_data_dir}")

        # 1. Memory (Mutable, Persistent) - Copy only if not exists
        user_memory = os.path.join(user_data_dir, "memory")
        bundle_memory = os.path.join(base_dir, "memory")
        if not os.path.exists(user_memory):
            if os.path.exists(bundle_memory):
                log_line(f"Initializing memory from {bundle_memory}")
                shutil.copytree(bundle_memory, user_memory)
            else:
                os.makedirs(user_memory)

        # 2. Assets (Read-only, Updated with App)
        user_assets = os.path.join(user_data_dir, "assets")
        bundle_assets = os.path.join(base_dir, "assets")
        if not os.path.exists(user_assets) and os.path.exists(bundle_assets):
            log_line(f"Copying assets from {bundle_assets}")
            try:
                shutil.copytree(bundle_assets, user_assets)
            except Exception as e:
                log_line(f"Assets copy failed: {e}")

        # 3. Temp (Mutable)
        user_temp = str(temp_dir(root=user_data_dir))

        # 4. Scheduler task dirs (Mutable)
        for sub in ("sche_tasks/pending", "sche_tasks/running", "sche_tasks/done"):
            os.makedirs(os.path.join(user_data_dir, sub), exist_ok=True)

        # 5. Redirect CWD
        os.chdir(user_data_dir)
        os.environ["GA_USER_DATA_DIR"] = user_data_dir
        sys.path.insert(0, user_data_dir)
        sys.path.insert(1, base_dir)
        
        # 6. Redirect stdout/stderr to log file in user dir for persistence
        log_file = os.path.join(user_data_dir, "app.log")
        try:
            sys.stdout = open(log_file, "a", buffering=1, encoding="utf-8")
            sys.stderr = open(log_file, "a", buffering=1, encoding="utf-8")
            print(f"[{datetime.now()}] App started in {user_data_dir}")
        except Exception as e:
            try:
                fallback_log = "/tmp/a3agent-app.log"
                sys.stdout = open(fallback_log, "a", buffering=1, encoding="utf-8")
                sys.stderr = open(fallback_log, "a", buffering=1, encoding="utf-8")
                print(f"[{datetime.now()}] App started in {user_data_dir} (log redirected due to: {e})")
            except Exception:
                pass

    else:
        # Dev mode: run in place
        os.chdir(base_dir)
        os.environ["GA_USER_DATA_DIR"] = base_dir

    configure_qt_runtime(base_dir, user_data_dir if getattr(sys, 'frozen', False) else base_dir)
    os.environ["GA_BASE_DIR"] = base_dir
    os.environ["GA_FRONTEND_DIR"] = os.path.join(base_dir, "frontend")
    SERVER_SOCKET = reserve_server_socket()
    SERVER_PORT = SERVER_SOCKET.getsockname()[1]
    log_line(f"Reserved local server port: {SERVER_PORT}")

    # Fix for macOS font issues and input method
    os.environ['QT_MAC_WANTS_LAYER'] = '1'
    os.environ['QT_SCALE_FACTOR'] = '1'
    
    # Start Server
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Wait for server to be ready
    log_line("Waiting for server to start...")
    if not wait_for_server():
        log_line("Server failed to start in time. Exiting.")
        sys.exit(1)
    
    try:
        from PyQt5 import QtCore
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts, True)
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        log_line("webengine preimport ok")
    except Exception as e:
        log_line(f"webengine preimport fail: {e}")
        log_line(traceback.format_exc())

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) # Keep running when main window hidden
    app.setWindowIcon(QIcon(APP_EFFECTIVE_ICON_PATH))
    try:
        app.aboutToQuit.connect(on_app_quit)
    except Exception:
        pass
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())
