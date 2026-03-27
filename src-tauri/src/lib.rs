use std::fs;
use std::process::{Command, Stdio};
use std::io::{BufRead, BufReader};
use std::thread;
use std::time::Duration;
use std::path::{Path, PathBuf};
use tauri::{Emitter, Manager};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

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

fn find_python_backend_dir(resource_dir: &Path) -> Option<PathBuf> {
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

    None
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

fn detect_workspace_root(resource_dir: &Path, python_backend_dir: &Path, app_data_dir: &Path) -> PathBuf {
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

    Err(last_err.unwrap_or_else(|| std::io::Error::other("failed to spawn python process")))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
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
                .build();
            }
            
            let resource_dir = app.path().resource_dir().expect("failed to get resource dir");
            let python_backend_dir =
                find_python_backend_dir(&resource_dir).expect("failed to find python-backend directory");

            let app_data_dir = app.path().app_data_dir().expect("failed to get app data dir");
            if !app_data_dir.exists() {
                std::fs::create_dir_all(&app_data_dir).expect("failed to create app data dir");
            }
            let ga_config_src_dir = find_ga_config_src_dir(&resource_dir, &python_backend_dir);
            let workspace_root = detect_workspace_root(&resource_dir, &python_backend_dir, &app_data_dir);
            if !workspace_root.exists() {
                std::fs::create_dir_all(&workspace_root).expect("failed to create workspace root");
            }
            let user_data_dir = workspace_root.join("ga_config");
            if !user_data_dir.exists() {
                std::fs::create_dir_all(&user_data_dir).expect("failed to create default config dir");
            }
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

            let sidecar = if cfg!(debug_assertions) {
                None
            } else {
                Some(
                    app_handle
                        .shell()
                        .sidecar("python-backend")
                        .or_else(|_| app_handle.shell().sidecar("bin/python-backend")),
                )
            };

            match sidecar {
                Some(Ok(sidecar_command)) => {
                    let sidecar_command = sidecar_command
                        .args(["0"])
                        .env("GA_APP_NAME", "A3Agent")
                        .env("GA_BASE_DIR", python_backend_dir.to_string_lossy().to_string())
                        .env("GA_FRONTEND_DIR", frontend_dir.to_string_lossy().to_string())
                        .env(
                            "GA_CONFIG_SRC_DIR",
                            ga_config_src_dir
                                .as_ref()
                                .map(|p| p.to_string_lossy().to_string())
                                .unwrap_or_else(|| resource_dir.join("ga_config").to_string_lossy().to_string()),
                        )
                        .env("GA_WORKSPACE_ROOT", ws_dir.to_string_lossy().to_string())
                        .env("GA_CONFIG_DIRNAME", "ga_config")
                        .env("GA_USER_DATA_DIR", ud_dir.to_string_lossy().to_string())
                        .env("GA_APP_DATA_DIR", ad_dir.to_string_lossy().to_string());

                    let (mut rx, _child) = sidecar_command
                        .spawn()
                        .expect("Failed to spawn sidecar process");

                    tauri::async_runtime::spawn(async move {
                        let mut last_port: Option<String> = None;
                        while let Some(event) = rx.recv().await {
                            match event {
                                CommandEvent::Stdout(bytes) => {
                                    let chunk = String::from_utf8_lossy(&bytes);
                                    for line in chunk.lines() {
                                        println!("Backend: {}", line);
                                        emit_ui_state_from_log(&app_handle, line);
                                        if line.starts_with("PORT:") {
                                            let port = line.replace("PORT:", "").trim().to_string();
                                            if last_port.as_deref() == Some(&port) {
                                                continue;
                                            }
                                            last_port = Some(port.clone());
                                            if let Some(window) = app_handle.get_webview_window("main") {
                                                let url = format!("http://127.0.0.1:{}/", port);
                                                println!("Navigating to {}", url);
                                                if let Ok(url) = tauri::Url::parse(&url) {
                                                    let _ = window.navigate(url);
                                                }
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
                _ => {
                    let mut child = spawn_python_backend(
                        &headless_main,
                        &python_backend_dir,
                        Some(frontend_dir),
                        ga_config_src_dir.as_deref(),
                        Some(ws_dir),
                        Some(ud_dir),
                        Some(ad_dir),
                    )
                    .expect("Failed to spawn python process");

                    let stdout = child.stdout.take().expect("Failed to open stdout");
                    let stderr = child.stderr.take().expect("Failed to open stderr");

                    thread::spawn(move || {
                        let reader = BufReader::new(stdout);
                        for line in reader.lines() {
                            if let Ok(line) = line {
                                println!("Python: {}", line);
                                emit_ui_state_from_log(&app_handle, &line);
                                if line.starts_with("PORT:") {
                                    let port = line.replace("PORT:", "").trim().to_string();
                                    if let Some(window) = app_handle.get_webview_window("main") {
                                        let url = format!("http://127.0.0.1:{}/", port);
                                        println!("Navigating to {}", url);
                                        if let Ok(url) = tauri::Url::parse(&url) {
                                            for _ in 0..5 {
                                                let _ = window.navigate(url.clone());
                                                thread::sleep(Duration::from_millis(500));
                                            }
                                        }
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

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet, toggle_main_window])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
