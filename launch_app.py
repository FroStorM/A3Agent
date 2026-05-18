import os
import json
import re
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

def run_child_python_if_requested():
    if os.environ.get("A3AGENT_CHILD_PYTHON") != "1":
        return
    import runpy

    args = list(sys.argv[1:])
    script = None
    rest = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-X" and i + 1 < len(args):
            i += 2
            continue
        if arg == "-u":
            i += 1
            continue
        if arg.startswith("-"):
            i += 1
            continue
        script = arg
        rest = args[i + 1:]
        break
    if not script:
        raise SystemExit("A3AGENT_CHILD_PYTHON requires a script path")
    sys.argv = [script] + rest
    runpy.run_path(script, run_name="__main__")
    raise SystemExit(0)


run_child_python_if_requested()

import objc
from uvicorn import run
from PIL import Image

try:
    from path_utils import app_data_dir, resource_dir, resource_path

    BASE_DIR = resource_dir()
except Exception:
    BASE_DIR = Path(__file__).resolve().parent

os.chdir(str(BASE_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

APP_NAME = "A3Agent"
LOG_FILE = Path(os.environ.get("GA_LOG_FILE") or "/tmp/A3Agent-launch.log")
WINDOW_REF = None
WEBVIEW_REF = None
FLOATING_REF = None
CONTROLLER_REF = None
WEBVIEW_DELEGATE_REF = None
PET_PROCESS_REF = None
LAST_PET_CONFIG = None


def log(message):
    try:
        print(message)
    except Exception:
        pass
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(str(message) + "\n")
    except Exception:
        pass


log("launcher: python entry loaded")

try:
    log("launcher: importing Cocoa")
    from Cocoa import (
        NSAlert,
        NSApplication,
        NSApplicationActivationPolicyRegular,
        NSBackingStoreBuffered,
        NSColor,
        NSFloatingWindowLevel,
        NSImage,
        NSImageView,
        NSMakeRect,
        NSMenu,
        NSMenuItem,
        NSScreen,
        NSWindow,
        NSWindowStyleMaskBorderless,
        NSWindowStyleMaskClosable,
        NSWindowStyleMaskMiniaturizable,
        NSWindowStyleMaskResizable,
        NSWindowStyleMaskTitled,
    )
    log("launcher: Cocoa imported")
    log("launcher: importing Foundation")
    from Foundation import NSObject, NSURL, NSURLRequest, NSSelectorFromString, NSTimer
    log("launcher: Foundation imported")
    log("launcher: importing WebKit")
    from WebKit import WKWebView, WKWebViewConfiguration
    log("launcher: WebKit imported")
except Exception as e:
    log(f"launcher: native WebKit import failed: {e}")
    raise RuntimeError(f"macOS WebKit runtime unavailable: {e}")


def find_free_port(lo=18501, hi=18599):
    for port in range(lo, hi + 1):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            sock.close()
            return port
        except OSError:
            continue
    return lo


PORT = find_free_port()
URL = f"http://127.0.0.1:{PORT}"

DESKTOP_PET_DEFAULT_CONFIG = {
    "enabled": True,
    "size": 104,
    "position": "right-bottom",
    "x": None,
    "y": None,
    "skin_name": "legacy-pet",
    "always_on_top": True,
    "show_shadow": False,
    "click_action": "toggle_main",
}


def desktop_pet_config_path():
    try:
        return app_data_dir() / "desktop_pet.json"
    except Exception:
        return Path(os.environ.get("GA_APP_DATA_DIR") or str(BASE_DIR)) / "desktop_pet.json"


def sanitize_desktop_pet_config(data):
    if not isinstance(data, dict):
        data = {}
    cfg = dict(DESKTOP_PET_DEFAULT_CONFIG)
    cfg.update({k: data.get(k) for k in cfg.keys() if k in data})
    cfg["enabled"] = bool(cfg.get("enabled"))
    cfg["always_on_top"] = bool(cfg.get("always_on_top"))
    cfg["show_shadow"] = bool(cfg.get("show_shadow"))
    try:
        cfg["size"] = int(cfg.get("size", DESKTOP_PET_DEFAULT_CONFIG["size"]))
    except Exception:
        cfg["size"] = DESKTOP_PET_DEFAULT_CONFIG["size"]
    cfg["size"] = max(48, min(220, cfg["size"]))
    if cfg.get("position") not in {"right-bottom", "right-top", "left-bottom", "left-top", "center", "custom"}:
        cfg["position"] = DESKTOP_PET_DEFAULT_CONFIG["position"]
    for key in ("x", "y"):
        value = cfg.get(key)
        if value is None or value == "":
            cfg[key] = None
        else:
            try:
                cfg[key] = float(value)
            except Exception:
                cfg[key] = None
    if cfg.get("click_action") not in {"toggle_main", "none"}:
        cfg["click_action"] = DESKTOP_PET_DEFAULT_CONFIG["click_action"]
    skin_name = cfg.get("skin_name") or DESKTOP_PET_DEFAULT_CONFIG["skin_name"]
    if skin_name != "legacy-pet":
        skin_dir = resource_path("frontends", "skins", str(skin_name))
        if not Path(skin_dir).is_dir():
            skin_name = DESKTOP_PET_DEFAULT_CONFIG["skin_name"]
    cfg["skin_name"] = skin_name
    return cfg


def load_desktop_pet_config():
    try:
        path = desktop_pet_config_path()
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return sanitize_desktop_pet_config(json.load(f))
    except Exception as e:
        log(f"desktop_pet: load config failed: {e}")
    return dict(DESKTOP_PET_DEFAULT_CONFIG)


def desktop_pet_skin_preview_path(name):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or ""))
    return Path(app_data_dir()) / f"desktop_pet_preview_{safe}.png"


def resolve_desktop_pet_image_path(cfg):
    skin_name = cfg.get("skin_name") or DESKTOP_PET_DEFAULT_CONFIG["skin_name"]
    if skin_name == "legacy-pet":
        path = resource_path("frontends", "pet.gif")
        return Path(path) if Path(path).exists() else None

    skin_dir = Path(resource_path("frontends", "skins", skin_name))
    skin_json = skin_dir / "skin.json"
    if not skin_json.exists():
        return None
    try:
        with skin_json.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        animations = meta.get("animations") or {}
        if not animations:
            return None
        anim = animations.get("idle") or next(iter(animations.values()))
        asset = skin_dir / str(anim.get("file") or "")
        if not asset.exists():
            return None
        if str(meta.get("format") or "").lower() == "gif" or asset.suffix.lower() == ".gif":
            return asset
        sprite = anim.get("sprite") or {}
        img = Image.open(asset).convert("RGBA")
        frame_width = int(sprite.get("frameWidth") or img.width)
        frame_height = int(sprite.get("frameHeight") or img.height)
        start_frame = int(sprite.get("startFrame") or 0)
        columns = max(1, int(sprite.get("columns") or 1))
        row = start_frame // columns
        col = start_frame % columns
        box = (
            col * frame_width,
            row * frame_height,
            col * frame_width + frame_width,
            row * frame_height + frame_height,
        )
        preview = desktop_pet_skin_preview_path(skin_name)
        preview.parent.mkdir(parents=True, exist_ok=True)
        img.crop(box).save(preview, format="PNG")
        return preview
    except Exception as e:
        log(f"desktop_pet: resolve skin failed: {e}")
        return None


def load_desktop_pet_image(cfg):
    path = resolve_desktop_pet_image_path(cfg)
    if path is None:
        return None, None
    image = NSImage.alloc().initWithContentsOfFile_(str(path))
    if image is None:
        return None, None
    return image, path


def pet_origin_for_config(cfg):
    screen_frame = NSScreen.mainScreen().visibleFrame()
    size = float(cfg.get("size") or DESKTOP_PET_DEFAULT_CONFIG["size"])
    margin = 28.0
    pos = cfg.get("position")
    if pos == "custom" and cfg.get("x") is not None and cfg.get("y") is not None:
        return float(cfg["x"]), float(cfg["y"])
    left = screen_frame.origin.x + margin
    right = screen_frame.origin.x + screen_frame.size.width - size - margin
    bottom = screen_frame.origin.y + margin
    top = screen_frame.origin.y + screen_frame.size.height - size - margin
    if pos == "right-top":
        return right, top
    if pos == "left-bottom":
        return left, bottom
    if pos == "left-top":
        return left, top
    if pos == "center":
        return (
            screen_frame.origin.x + (screen_frame.size.width - size) / 2.0,
            screen_frame.origin.y + (screen_frame.size.height - size) / 2.0,
        )
    return right, bottom


def wait_for_server(timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(URL + "/api/status", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


def start_server():
    try:
        log("server: importing api_server")
        from api_server import app

        log(f"server: starting on {URL}")
        run(app, host="127.0.0.1", port=PORT, log_level="error")
    except Exception as e:
        log(f"server: failed: {e}")


def alert(message):
    try:
        panel = NSAlert.alloc().init()
        panel.setMessageText_(f"{APP_NAME} 启动失败")
        panel.setInformativeText_(str(message))
        panel.runModal()
    except Exception:
        log(message)


def install_main_menu(app):
    try:
        main_menu = NSMenu.alloc().init()

        app_item = NSMenuItem.alloc().init()
        main_menu.addItem_(app_item)
        app_menu = NSMenu.alloc().initWithTitle_(APP_NAME)
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Quit {APP_NAME}", NSSelectorFromString("terminate:"), "q"
        )
        app_menu.addItem_(quit_item)
        app_item.setSubmenu_(app_menu)

        edit_item = NSMenuItem.alloc().init()
        main_menu.addItem_(edit_item)
        edit_menu = NSMenu.alloc().initWithTitle_("Edit")
        for title, selector, key in (
            ("Undo", "undo:", "z"),
            ("Redo", "redo:", "Z"),
            ("Cut", "cut:", "x"),
            ("Copy", "copy:", "c"),
            ("Paste", "paste:", "v"),
            ("Select All", "selectAll:", "a"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, NSSelectorFromString(selector), key
            )
            edit_menu.addItem_(item)
        edit_item.setSubmenu_(edit_menu)
        app.setMainMenu_(main_menu)
        log("launcher: standard app/edit menu installed")
    except Exception as e:
        log(f"launcher: install menu failed: {e}")


class WebViewDelegate(NSObject):
    def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
        self, webview, configuration, navigation_action, window_features
    ):
        try:
            request = navigation_action.request()
            if request is not None:
                webview.loadRequest_(request)
        except Exception as e:
            log(f"launcher: blocked extra webview: {e}")
        return None


class AppController(NSObject):
    def toggleMainWindow_(self, sender):
        try:
            if WINDOW_REF is None:
                return
            if WINDOW_REF.isVisible():
                WINDOW_REF.orderOut_(None)
            else:
                WINDOW_REF.makeKeyAndOrderFront_(None)
                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception as e:
            log(f"floating: toggle failed: {e}")

    def pollStatus_(self, timer):
        try:
            if getattr(self, "button", None) is None:
                return
            with urllib.request.urlopen(URL + "/api/status", timeout=0.8) as resp:
                data = __import__("json").loads(resp.read().decode("utf-8", errors="replace"))
            if data.get("agent_init_error"):
                title = "A3\n错误"
                color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.20, 0.20, 0.88)
            elif data.get("needs_human_input"):
                title = "A3\n待确认"
                color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.20, 0.20, 0.88)
            elif data.get("is_running"):
                title = "A3\n运行"
                color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.96, 0.62, 0.16, 0.88)
            else:
                title = "A3"
                color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.16, 0.45, 0.96, 0.82)
            if hasattr(self.button, "setTitle_"):
                self.button.setTitle_(title)
        except Exception:
            try:
                if hasattr(self.button, "setTitle_"):
                    self.button.setTitle_("A3\n离线")
            except Exception:
                pass

    def pollDesktopPetConfig_(self, timer):
        try:
            apply_desktop_pet_config(self, load_desktop_pet_config())
        except Exception as e:
            log(f"desktop_pet: apply config failed: {e}")


class PetImageView(NSImageView):
    def initWithFrame_controller_(self, frame, controller):
        self = objc.super(PetImageView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.controller = controller
        self._dragged = False
        self.setEditable_(False)
        return self

    def mouseDown_(self, event):
        self._dragged = False

    def mouseDragged_(self, event):
        try:
            window = self.window()
            frame = window.frame()
            frame.origin.x += event.deltaX()
            frame.origin.y -= event.deltaY()
            window.setFrameOrigin_(frame.origin)
            self._dragged = True
        except Exception as e:
            log(f"desktop_pet: drag failed: {e}")

    def mouseUp_(self, event):
        if self._dragged:
            return
        try:
            cfg = getattr(self.controller, "desktop_pet_config", DESKTOP_PET_DEFAULT_CONFIG)
            if cfg.get("click_action") == "toggle_main":
                self.controller.toggleMainWindow_(self)
        except Exception as e:
            log(f"desktop_pet: click failed: {e}")


def create_window(app):
    rect = NSMakeRect(120.0, 80.0, 1280.0, 860.0)
    style = (
        NSWindowStyleMaskTitled
        | NSWindowStyleMaskClosable
        | NSWindowStyleMaskMiniaturizable
        | NSWindowStyleMaskResizable
    )
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, style, NSBackingStoreBuffered, False
    )
    window.setTitle_(APP_NAME)

    config = WKWebViewConfiguration.alloc().init()
    webview = WKWebView.alloc().initWithFrame_configuration_(rect, config)
    global WEBVIEW_DELEGATE_REF
    WEBVIEW_DELEGATE_REF = WebViewDelegate.alloc().init()
    webview.setUIDelegate_(WEBVIEW_DELEGATE_REF)
    request = NSURLRequest.requestWithURL_(NSURL.URLWithString_(URL))
    webview.loadRequest_(request)

    window.setContentView_(webview)
    window.center()
    window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    return window, webview


def create_desktop_pet(controller):
    try:
        cfg = load_desktop_pet_config()
        size = float(cfg["size"])
        x, y = pet_origin_for_config(cfg)
        rect = NSMakeRect(x, y, size, size)
        panel = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False
        )
        panel.setLevel_(NSFloatingWindowLevel if cfg.get("always_on_top") else 0)
        panel.setOpaque_(False)
        panel.setHasShadow_(bool(cfg.get("show_shadow")))
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setMovableByWindowBackground_(False)
        panel.setCollectionBehavior_(1 << 7)  # NSWindowCollectionBehaviorCanJoinAllSpaces

        pet = PetImageView.alloc().initWithFrame_controller_(NSMakeRect(0.0, 0.0, size, size), controller)
        pet.setWantsLayer_(True)
        pet.layer().setBackgroundColor_(NSColor.clearColor().CGColor())
        pet.setImageScaling_(2)  # NSImageScaleProportionallyUpOrDown
        if hasattr(pet, "setAnimates_"):
            pet.setAnimates_(True)

        image, pet_path = load_desktop_pet_image(cfg)
        if image is None or pet_path is None:
            raise RuntimeError("failed to load desktop pet image")
        pet.setImage_(image)

        panel.setContentView_(pet)
        controller.desktop_pet_config = cfg
        if cfg.get("enabled"):
            panel.orderFrontRegardless()
        else:
            panel.orderOut_(None)
        controller.button = pet
        log(f"desktop_pet: native cocoa pet loaded {pet_path}")
        return panel
    except Exception as e:
        log(f"desktop_pet: native pet failed: {e}")
        return None


def apply_desktop_pet_config(controller, cfg):
    global LAST_PET_CONFIG
    cfg = sanitize_desktop_pet_config(cfg)
    if cfg == LAST_PET_CONFIG:
        return
    LAST_PET_CONFIG = dict(cfg)
    controller.desktop_pet_config = cfg
    if FLOATING_REF is None:
        return
    size = float(cfg["size"])
    x, y = pet_origin_for_config(cfg)
    FLOATING_REF.setLevel_(NSFloatingWindowLevel if cfg.get("always_on_top") else 0)
    FLOATING_REF.setHasShadow_(bool(cfg.get("show_shadow")))
    FLOATING_REF.setOpaque_(False)
    FLOATING_REF.setBackgroundColor_(NSColor.clearColor())
    FLOATING_REF.setFrame_display_(NSMakeRect(x, y, size, size), True)
    if getattr(controller, "button", None) is not None:
        controller.button.setFrame_(NSMakeRect(0.0, 0.0, size, size))
        image, pet_path = load_desktop_pet_image(cfg)
        if image is not None:
            controller.button.setImage_(image)
        controller.button.setNeedsDisplay_(True)
    if cfg.get("enabled"):
        FLOATING_REF.orderFrontRegardless()
    else:
        FLOATING_REF.orderOut_(None)
    log(f"desktop_pet: config applied {cfg}")


def main():
    global WINDOW_REF, WEBVIEW_REF, FLOATING_REF, CONTROLLER_REF
    log("launcher: creating native app")
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    install_main_menu(app)

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    log("launcher: waiting for server")
    if not wait_for_server():
        msg = "本地服务没有启动成功，请查看日志：/tmp/A3Agent-launch.log"
        log(msg)
        alert(msg)
        sys.exit(1)

    log("launcher: creating WebKit window")
    window, webview = create_window(app)
    CONTROLLER_REF = AppController.alloc().init()
    FLOATING_REF = create_desktop_pet(CONTROLLER_REF)
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0, CONTROLLER_REF, "pollDesktopPetConfig:", None, True
    )
    # Keep strong references alive for the Cocoa event loop.
    WINDOW_REF = window
    WEBVIEW_REF = webview
    log(f"launcher: window loaded {URL}")
    app.run()


if __name__ == "__main__":
    main()
