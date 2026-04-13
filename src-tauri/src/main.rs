#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::File;
use std::io::Write;

fn main() {
    let log_path = std::env::temp_dir().join("a3agent_startup.log");
    let mut log_file = File::create(&log_path).unwrap();

    writeln!(log_file, "=== A3Agent starting ===").ok();
    writeln!(log_file, "Exe: {:?}", std::env::current_exe()).ok();
    writeln!(log_file, "Cwd: {:?}", std::env::current_dir()).ok();
    log_file.flush().ok();

    std::panic::set_hook(Box::new(move |info| {
        let msg = format!("[PANIC] {}", info);
        eprintln!("{}", msg);
        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(&log_path) {
            writeln!(f, "{}", msg).ok();
        }
    }));

    writeln!(log_file, "Calling a3_agent_lib::run()...").ok();
    log_file.flush().ok();
    a3_agent_lib::run();
    writeln!(log_file, "run() returned normally").ok();
}
