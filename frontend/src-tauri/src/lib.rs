use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::{process::CommandChild, ShellExt};

struct Backend(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // In dev, run uvicorn yourself with --reload
            if !cfg!(debug_assertions) {
                let data_dir = app.path().app_data_dir()?;
                std::fs::create_dir_all(&data_dir)?;

                let (mut rx, child) = app
                    .shell()
                    .sidecar("panel-backend")?
                    .args([
                        "--port", "8731",
                        "--data-dir", data_dir.to_str().unwrap(),
                        "--exit-on-stdin-close",
                    ])
                    .spawn()?;

                // drain output so the pipe never fills up
                tauri::async_runtime::spawn(async move {
                    while let Some(_event) = rx.recv().await {}
                });

                app.manage(Backend(Mutex::new(Some(child))));
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app.try_state::<Backend>() {
                    if let Some(child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}