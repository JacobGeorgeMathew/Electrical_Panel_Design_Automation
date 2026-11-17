use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::{process::CommandChild, ShellExt};

struct Backend(Mutex<Option<CommandChild>>);
struct LaunchCredential(Option<String>);

fn launch_credential() -> Result<String, &'static str> {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).map_err(|_| "Local session initialization failed.")?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn trusted_window(label: &str, url: &tauri::Url, development: bool) -> bool {
    if label != "main" || !url.username().is_empty() || url.password().is_some() {
        return false;
    }
    let origin = url.origin().ascii_serialization();
    matches!(origin.as_str(), "http://tauri.localhost" | "https://tauri.localhost")
        || (url.scheme() == "tauri" && url.host_str() == Some("localhost") && url.port().is_none())
        || (development
            && matches!(origin.as_str(), "http://localhost:3000" | "http://127.0.0.1:3000"))
}

#[tauri::command]
fn local_session(
    window: tauri::WebviewWindow,
    credential: tauri::State<'_, LaunchCredential>,
) -> Result<Option<String>, &'static str> {
    let url = window.url().map_err(|_| "Local session is unavailable.")?;
    if !trusted_window(window.label(), &url, cfg!(debug_assertions)) {
        return Err("Local session is unavailable.");
    }
    Ok(credential.0.clone())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![local_session])
        .setup(|app| {
            // In dev, run uvicorn yourself with --reload
            if !cfg!(debug_assertions) {
                let data_dir = app.path().app_data_dir()?;
                std::fs::create_dir_all(&data_dir)?;
                let credential = launch_credential()?;

                let (mut rx, child) = app
                    .shell()
                    .sidecar("panel-backend")?
                    .env("PANEL_LOCAL_MODE", "desktop")
                    .env("PANEL_LOCAL_LAUNCH_SECRET", &credential)
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
                app.manage(LaunchCredential(Some(credential)));
            } else {
                // Explicit PANEL_LOCAL_MODE=development on the separately run backend.
                app.manage(LaunchCredential(None));
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn credentials_are_fresh_and_window_origin_is_exact() {
        let first = launch_credential().unwrap();
        assert_eq!(first.len(), 64);
        assert_ne!(first, launch_credential().unwrap());
        for origin in ["tauri://localhost/", "http://tauri.localhost/", "https://tauri.localhost/"] {
            assert!(trusted_window("main", &tauri::Url::parse(origin).unwrap(), false));
            assert!(!trusted_window("other", &tauri::Url::parse(origin).unwrap(), false));
        }
        for origin in ["https://evil.example/", "http://tauri.localhost.evil/", "http://localhost:3000/"] {
            assert!(!trusted_window("main", &tauri::Url::parse(origin).unwrap(), false));
        }
        assert!(trusted_window("main", &tauri::Url::parse("http://localhost:3000/").unwrap(), true));
    }
}
