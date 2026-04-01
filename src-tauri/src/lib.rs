use std::fs;
use std::process::{Command, Stdio};
use std::io::{BufRead, BufReader, Write};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use std::path::{Path, PathBuf};
use tauri::{Emitter, Manager};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

/// 将 PathBuf 转为普通字符串，去掉 Windows \\?\ UNC 前缀
fn path_to_str(path: &Path) -> String {
    let s = path.to_string_lossy();
    // 去掉 Windows 扩展路径前缀 \\?\  避免与正斜杠路径拼接时出错
    if let Some(stripped) = s.strip_prefix(r"\\?\") {
        stripped.to_string()
    } else {
        s.to_string()
    }
}

/// 全局状态：存储 python-backend 子进程的 PID
struct BackendPid(Mutex<Option<u32>>);

fn log(msg: &str) {
    println!("[A3Agent] {}", msg);
    let path = std::env::temp_dir().join("a3agent_startup.log");
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(&path) {
        let _ = writeln!(f, "[A3Agent] {}", msg);
    }
}

fn python_log(line: &str) {
    let path = std::env::temp_dir().join("python_backend.log");
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(&path) {
        let _ = writeln!(f, "{}", line);
    }
}

fn emit_ui_state_from_log(app_handle: &tauri::AppHandle, line: &str) {
    let Some(rest) = line.strip_prefix("[Status] broadcast state=") else {
        return;
    };
    let state = rest
        .split_whitespace()
        .next()
        .unwrap_or("")
        .trim()
        .to_string();
    if state.is_empty() {
        return;
    }
    let payload = serde_json::json!({
        "state": state,
        "is_running": state == "running",
        "needs_human_input": state == "need-user",
        "agent_init_error": "",
        "source": "backend-log"
    });
    let _ = app_handle.emit("ga-status", payload);

    if let Some(window) = app_handle.get_webview_window("floating") {
        let js = format!(
            "document.documentElement.dataset.state = {:?};",
            state
        );
        let _ = window.eval(js.as_str());
    }
}

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[tauri::command]
fn toggle_main_window(app: tauri::AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "main window not found".to_string())?;

    let is_visible = window.is_visible().map_err(|e| e.to_string())?;
    if is_visible {
        window.hide().map_err(|e| e.to_string())?;
    } else {
        window.show().map_err(|e| e.to_string())?;
        window.set_focus().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn exit_app(app: tauri::AppHandle) {
    app.exit(0);
}

fn find_python_backend_dir(resource_dir: &Path) -> Option<PathBuf> {
    // 首先尝试查找开发环境的 python-backend 目录
    let from_resource_dir = resource_dir.join("python-backend");
    if from_resource_dir.join("headless_main.py").exists() {
        return Some(from_resource_dir);
    }

    if let Ok(exe) = std::env::current_exe() {
        let mut cur = exe.parent().map(|p| p.to_path_buf());
        while let Some(p) = cur {
            let candidate = p.join("python-backend");
            if candidate.join("headless_main.py").exists() {
                return Some(candidate);
            }
            cur = p.parent().map(|pp| pp.to_path_buf());
        }
    }

    // 如果找不到开发环境，返回 resource_dir 作为后备
    // 这样在使用 sidecar 时，可以从 resource_dir 查找
    Some(resource_dir.to_path_buf())
}

fn find_external_frontend_dir(python_backend_dir: &Path) -> Option<PathBuf> {
    let mut cur = Some(python_backend_dir.to_path_buf());
    for _ in 0..8 {
        if let Some(p) = cur.as_ref() {
            let candidate = p.join("frontend");
            if candidate.join("index.html").exists() {
                return Some(candidate);
            }
            cur = p.parent().map(|pp| pp.to_path_buf());
        } else {
            break;
        }
    }
    None
}

fn find_ga_config_src_dir(resource_dir: &Path, python_backend_dir: &Path) -> Option<PathBuf> {
    let direct_candidates = [
        resource_dir.join("ga_config"),
        python_backend_dir.join("ga_config"),
    ];
    for candidate in direct_candidates {
        if candidate.join("memory").exists() {
            return Some(candidate);
        }
    }

    if let Some(parent) = python_backend_dir.parent() {
        let candidate = parent.join("ga_config");
        if candidate.join("memory").exists() {
            return Some(candidate);
        }
    }

    if let Ok(exe) = std::env::current_exe() {
        let mut cur = exe.parent().map(|p| p.to_path_buf());
        for _ in 0..8 {
            if let Some(p) = cur.as_ref() {
                let candidate = p.join("ga_config");
                if candidate.join("memory").exists() {
                    return Some(candidate);
                }
                cur = p.parent().map(|pp| pp.to_path_buf());
            } else {
                break;
            }
        }
    }

    None
}

fn copy_missing_tree(src: &Path, dst: &Path) -> std::io::Result<()> {
    if !src.exists() || src == dst {
        return Ok(());
    }

    if src.is_file() {
        if !dst.exists() {
            if let Some(parent) = dst.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::copy(src, dst)?;
        }
        return Ok(());
    }

    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let path = entry.path();
        let target = dst.join(entry.file_name());
        if path.is_dir() {
            copy_missing_tree(&path, &target)?;
        } else if path.is_file() {
            let needs_copy = match target.metadata() {
                Ok(meta) => meta.len() == 0,
                Err(_) => true,
            };
            if needs_copy {
                if let Some(parent) = target.parent() {
                    fs::create_dir_all(parent)?;
                }
                fs::copy(&path, &target)?;
            }
        }
    }
    Ok(())
}

fn is_project_root(path: &Path) -> bool {
    path.join("src-tauri").join("tauri.conf.json").exists()
        && path.join("python-backend").join("headless_main.py").exists()
}

fn detect_workspace_root(resource_dir: &Path, python_backend_dir: &Path) -> PathBuf {
    // 在release构建中，优先使用exe所在目录
    if !cfg!(debug_assertions) {
        if let Ok(exe) = std::env::current_exe() {
            if let Some(parent) = exe.parent() {
                return parent.to_path_buf();
            }
        }
    }

    // 在开发模式下，查找项目根目录
    if let Ok(exe) = std::env::current_exe() {
        for ancestor in exe.ancestors() {
            if is_project_root(ancestor) {
                return ancestor.to_path_buf();
            }
        }
    }

    if let Ok(cwd) = std::env::current_dir() {
        for ancestor in cwd.ancestors() {
            if is_project_root(ancestor) {
                return ancestor.to_path_buf();
            }
        }
    }

    for ancestor in resource_dir.ancestors() {
        if is_project_root(ancestor) {
            return ancestor.to_path_buf();
        }
    }

    if let Some(parent) = python_backend_dir.parent() {
        if is_project_root(parent) {
            return parent.to_path_buf();
        }
    }

    app_data_dir.to_path_buf()
}

fn kill_process_by_pid(pid: u32) {
    log(&format!("Killing python-backend process (pid={})", pid));
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/F", "/T"])
            .spawn();
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .spawn();
    }
}

fn spawn_python_backend(
    headless_main: &Path,
    python_backend_dir: &Path,
    frontend_dir: Option<&Path>,
    config_src_dir: Option<&Path>,
    workspace_root: Option<&Path>,
    user_data_dir: Option<&Path>,
    app_data_dir: Option<&Path>,
) -> std::io::Result<std::process::Child> {
    let candidates: Vec<&str> = if cfg!(target_os = "windows") {
        vec!["python", "py"]
    } else {
        vec!["python3.11", "python3.10", "python3.9", "python3.8", "python3", "python"]
    };

    let mut last_err: Option<std::io::Error> = None;
    for cmd in candidates {
        let mut command = Command::new(cmd);
        command
            .arg("-u")
            .arg(headless_main)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .env("GA_APP_NAME", "A3Agent")
            .env("GA_BASE_DIR", python_backend_dir);
        if let Some(dir) = frontend_dir {
            command.env("GA_FRONTEND_DIR", dir);
        }
        if let Some(dir) = config_src_dir {
            command.env("GA_CONFIG_SRC_DIR", dir);
        }
        if let Some(dir) = workspace_root {
            command.env("GA_WORKSPACE_ROOT", dir);
        }
        command.env("GA_CONFIG_DIRNAME", "ga_config");
        if let Some(dir) = user_data_dir {
            command.env("GA_USER_DATA_DIR", dir);
        }
        if let Some(dir) = app_data_dir {
            command.env("GA_APP_DATA_DIR", dir);
        }
        let res = command.spawn();
        match res {
            Ok(child) => return Ok(child),
            Err(e) => last_err = Some(e),
        }
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let portable_backend = exe_dir.join("python-backend.exe");
            if portable_backend.exists() {
                log(&format!("Trying portable python-backend.exe at {:?}", portable_backend));
                let mut cmd = Command::new(&portable_backend);
                if let Some(dir) = frontend_dir {
                    cmd.env("GA_FRONTEND_DIR", dir);
                }
                if let Some(dir) = workspace_root {
                    cmd.env("GA_WORKSPACE_ROOT", dir);
                }
                cmd.env("GA_CONFIG_DIRNAME", "ga_config");
                if let Some(dir) = user_data_dir {
                    cmd.env("GA_USER_DATA_DIR", dir);
                }
                if let Some(dir) = app_data_dir {
                    cmd.env("GA_APP_DATA_DIR", dir);
                }
                match cmd.env("GA_BASE_DIR", exe_dir).spawn() {
                    Ok(child) => return Ok(child),
                    Err(e) => {
                        log(&format!("Portable python-backend.exe failed: {}", e));
                        last_err = Some(e);
                    }
                }
            }
        }
    }

    Err(last_err.unwrap_or_else(|| std::io::Error::other("failed to spawn python process")))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(BackendPid(Mutex::new(None)))
        .setup(|app| {
            log("setup() started");
            let app_handle = app.handle().clone();

            let tray_icon = {
                let handle = app.handle().clone();

                let show_hide =
                    tauri::menu::MenuItem::with_id(&handle, "show_hide", "显示/隐藏", true, None::<&str>)?;
                let quit = tauri::menu::MenuItem::with_id(&handle, "quit", "退出", true, None::<&str>)?;
                let menu = tauri::menu::Menu::with_items(&handle, &[&show_hide, &quit])?;

                let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/32x32.png"))
                    .map_err(|e| e.to_string())?;

                tauri::tray::TrayIconBuilder::new()
                    .menu(&menu)
                    .icon(icon)
                    .tooltip("A3Agent")
                    .on_menu_event(move |app, event| {
                        if event.id().as_ref() == "quit" {
                            app.exit(0);
                            return;
                        }
                        if event.id().as_ref() == "show_hide" {
                            let _ = toggle_main_window(app.clone());
                        }
                    })
                    .build(&handle)?
            };
            std::mem::forget(tray_icon);
            log("tray icon created");

            {
                let _ = tauri::WebviewWindowBuilder::new(
                    app,
                    "floating",
                    tauri::WebviewUrl::App("floating.html".into()),
                )
                .title("A3Agent")
                .transparent(true)
                .decorations(false)
                .always_on_top(true)
                .skip_taskbar(true)
                .resizable(false)
                .position(20.0, 120.0)
                .inner_size(72.0, 72.0)
                .visible_on_all_workspaces(true)
                .shadow(false)
                .build();
                log("floating window created");
            }

            let resource_dir = match app.path().resource_dir() {
                Ok(dir) => dir,
                Err(e) => {
                    log(&format!("ERROR: failed to get resource dir: {}", e));
                    eprintln!("ERROR: failed to get resource dir: {}", e);
                    return Err(e.into());
                }
            };
            log(&format!("resource_dir: {:?}", resource_dir));

            let python_backend_dir = match find_python_backend_dir(&resource_dir) {
                Some(dir) => dir,
                None => {
                    let msg = format!("ERROR: Cannot find python-backend directory. Searched in:\n  - {:?}/python-backend\n  - Parent directories of exe", resource_dir);
                    log(&msg);
                    eprintln!("{}", msg);
                    return Err(msg.into());
                }
            };
            log(&format!("python_backend_dir: {:?}", python_backend_dir));

            let app_data_dir = match app.path().app_data_dir() {
                Ok(dir) => dir,
                Err(e) => {
                    log(&format!("ERROR: failed to get app data dir: {}", e));
                    return Err(e.into());
                }
            };
            log(&format!("app_data_dir: {:?}", app_data_dir));
            if !app_data_dir.exists() {
                if let Err(e) = std::fs::create_dir_all(&app_data_dir) {
                    log(&format!("ERROR: failed to create app data dir: {}", e));
                    return Err(e.into());
                }
            }
            let workspace_root = detect_workspace_root(&resource_dir, &python_backend_dir);
            log(&format!("workspace_root: {:?}", workspace_root));
            if !workspace_root.exists() {
                if let Err(e) = std::fs::create_dir_all(&workspace_root) {
                    log(&format!("WARN: failed to create workspace root: {}", e));
                }
            }
            let user_data_dir = workspace_root.join("ga_config");
            if !user_data_dir.exists() {
                if let Err(e) = std::fs::create_dir_all(&user_data_dir) {
                    log(&format!("WARN: failed to create config dir: {}", e));
                }
            }
            log("dirs setup done");
            let headless_main = python_backend_dir.join("headless_main.py");
            let resource_frontend_dir = {
                let candidate = resource_dir.join("frontend");
                if candidate.join("index.html").exists() {
                    Some(candidate)
                } else {
                    None
                }
            };
            let external_frontend_dir = resource_frontend_dir.or_else(|| find_external_frontend_dir(&python_backend_dir));

            let ud_dir = user_data_dir.as_path();
            let ad_dir = app_data_dir.as_path();
            let ws_dir = workspace_root.as_path();
            let frontend_dir = external_frontend_dir
                .as_deref()
                .unwrap_or_else(|| resource_dir.as_path());
            if let Some(src) = ga_config_src_dir.as_deref() {
                let targets = [
                    ws_dir.to_path_buf(),
                    ws_dir.join("ga_config"),
                    ud_dir.to_path_buf(),
                ];
                for target in targets {
                    let _ = copy_missing_tree(src, &target);
                }
            }

            let sidecar = app_handle
                .shell()
                .sidecar("python-backend")
                .or_else(|_| app_handle.shell().sidecar("binaries/python-backend"));

            match sidecar {
                Ok(sidecar_command) => {
                    log("Using bundled Python backend (sidecar)");
                    let sidecar_command = sidecar_command
                        .args(["0"])
                        .env("GA_APP_NAME", "A3Agent")
                        .env("GA_BASE_DIR", path_to_str(&python_backend_dir))
                        .env("GA_FRONTEND_DIR", path_to_str(frontend_dir))
                        .env("GA_WORKSPACE_ROOT", path_to_str(ws_dir))
                        .env("GA_CONFIG_DIRNAME", "ga_config")
                        .env("GA_USER_DATA_DIR", path_to_str(ud_dir))
                        .env("GA_APP_DATA_DIR", path_to_str(ad_dir));

                    let (mut rx, child) = match sidecar_command.spawn() {
                        Ok(result) => result,
                        Err(e) => {
                            let msg = format!("ERROR: Failed to spawn sidecar process: {}", e);
                            log(&msg);
                            eprintln!("{}", msg);
                            return Err(msg.into());
                        }
                    };

                    // 将 child 的 PID 存入全局状态，退出时通过 RunEvent::Exit kill
                    if let Ok(mut guard) = app_handle.state::<BackendPid>().0.lock() {
                        *guard = Some(child.pid());
                    }

                    tauri::async_runtime::spawn(async move {
                        let mut last_port: Option<String> = None;
                        while let Some(event) = rx.recv().await {
                            match event {
                                CommandEvent::Stdout(bytes) => {
                                    let chunk = String::from_utf8_lossy(&bytes);
                                    for line in chunk.lines() {
                                        println!("Backend: {}", line);
                                        python_log(line);
                                        emit_ui_state_from_log(&app_handle, line);
                                        if line.starts_with("PORT:") {
                                            let port = line.replace("PORT:", "").trim().to_string();
                                            if last_port.as_deref() == Some(&port) {
                                                continue;
                                            }
                                            last_port = Some(port.clone());
                                            println!("Backend API available at: http://127.0.0.1:{}/", port);
                                            // Emit backend port via Tauri event system
                                            let port_num: u16 = port.parse().unwrap_or(0);
                                            let _ = app_handle.emit("backend-port", port_num);
                                            // Also inject directly in case window is already ready
                                            if let Some(window) = app_handle.get_webview_window("main") {
                                                let js = format!("window.__BACKEND_PORT__ = {}; window.dispatchEvent(new CustomEvent('backendReady', {{detail: {}}}));", port, port);
                                                let _ = window.eval(&js);
                                                thread::sleep(Duration::from_millis(500));
                                                let _ = window.show();
                                                let _ = window.set_focus();
                                            }
                                        }
                                    }
                                }
                                CommandEvent::Stderr(bytes) => {
                                    let chunk = String::from_utf8_lossy(&bytes);
                                    for line in chunk.lines() {
                                        eprintln!("Backend (stderr): {}", line);
                                    }
                                }
                                _ => {}
                            }
                        }
                    });
                }
                Err(e) => {
                    log(&format!("Sidecar not available ({}), falling back to system Python", e));
                    log("Attempting to spawn Python backend directly...");
                    let mut child = match spawn_python_backend(
                        &headless_main,
                        &python_backend_dir,
                        Some(frontend_dir),
                        ga_config_src_dir.as_deref(),
                        Some(ws_dir),
                        Some(ud_dir),
                        Some(ad_dir),
                    ) {
                        Ok(child) => child,
                        Err(e) => {
                            let msg = format!(
                                "ERROR: Failed to spawn Python process: {}\n\n\
                                请确保:\n\
                                1. 系统已安装 Python 3.8 或更高版本\n\
                                2. Python 已添加到系统 PATH 环境变量\n\
                                3. 已安装所需的 Python 依赖包\n\n\
                                可以在命令行运行 'python --version' 检查 Python 是否正确安装",
                                e
                            );
                            log(&msg);
                            eprintln!("{}", msg);
                            return Err(msg.into());
                        }
                    };

                    // 保存子进程 PID，退出时通过 RunEvent::Exit kill
                    if let Ok(mut guard) = app_handle.state::<BackendPid>().0.lock() {
                        *guard = Some(child.id());
                    }

                    let stdout = child.stdout.take().expect("Failed to open stdout");
                    let stderr = child.stderr.take().expect("Failed to open stderr");

                    thread::spawn(move || {
                        let reader = BufReader::new(stdout);
                        for line in reader.lines() {
                            if let Ok(line) = line {
                                println!("Python: {}", line);
                                python_log(&line);
                                emit_ui_state_from_log(&app_handle, &line);
                                if line.starts_with("PORT:") {
                                    let port = line.replace("PORT:", "").trim().to_string();
                                    println!("Backend API available at: http://127.0.0.1:{}/", port);
                                    if let Some(window) = app_handle.get_webview_window("main") {
                                        let js = format!("window.__BACKEND_PORT__ = {}; window.dispatchEvent(new CustomEvent('backendReady', {{detail: {}}}));", port, port);
                                        let _ = window.eval(&js);
                                        thread::sleep(Duration::from_millis(300));
                                        let _ = window.show();
                                        let _ = window.set_focus();
                                    }
                                }
                            }
                        }
                    });

                    thread::spawn(move || {
                        let reader = BufReader::new(stderr);
                        for line in reader.lines() {
                            if let Ok(line) = line {
                                eprintln!("Python (stderr): {}", line);
                            }
                        }
                    });
                }
            }
            
            // Start Idle Monitor Thread
            let app_handle_idle = app.handle().clone();
            thread::spawn(move || {
                loop {
                    thread::sleep(Duration::from_secs(5)); // Check every 5 seconds
                    
                    if let Some(window) = app_handle_idle.get_webview_window("main") {
                        let js_script = r#"
                            (function() {
                                if (!window.__last_trigger_time) {
                                    window.__last_trigger_time = 0;
                                }
                                let now = Date.now() / 1000;
                                if (now - window.__last_trigger_time < 120) return;
                                
                                let el = document.getElementById('last-reply-time');
                                let last_reply = el ? parseInt(el.textContent) : 0;
                                if (!last_reply) return;
                                
                                if (now - last_reply > 1800) {
                                    const textarea = document.querySelector('textarea[data-testid="stChatInputTextArea"]');
                                    if (textarea) {
                                        const nativeTextAreaValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                                        nativeTextAreaValueSetter.call(textarea, "[AUTO]🤖 用户已经离开超过30分钟，作为自主智能体，请阅读自动化sop，执行自动任务。");
                                        textarea.dispatchEvent(new Event('input', { bubbles: true }));
                                        textarea.dispatchEvent(new Event('change', { bubbles: true }));
                                        setTimeout(() => {
                                            const btn = document.querySelector('[data-testid="stChatInputSubmitButton"]');
                                            if (btn) {
                                                btn.click();
                                            }
                                        }, 200);
                                    }
                                    window.__last_trigger_time = now;
                                }
                            })();
                        "#;
                        let _ = window.eval(js_script);
                    }
                }
            });

            log("setup() completed successfully");
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet, toggle_main_window, exit_app])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Ok(guard) = app_handle.state::<BackendPid>().0.lock() {
                    if let Some(pid) = *guard {
                        kill_process_by_pid(pid);
                    }
                }
            }
        });
}
