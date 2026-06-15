mod ollama;
mod python;
mod setup;

use python::PythonProcess;
use std::process::Child;
use std::sync::Mutex;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let process = PythonProcess(Mutex::new(None::<Child>));
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(process)
        .setup(|app| {
            let state = app.state::<PythonProcess>();
            tauri::async_runtime::block_on(async move {
                python::start_and_wait(&state, 8765).await
            })
            .map_err(|error| {
                Box::<dyn std::error::Error>::from(std::io::Error::new(
                    std::io::ErrorKind::Other,
                    error,
                ))
            })?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            python::check_backend_health,
            ollama::get_ollama_status
        ])
        .build(tauri::generate_context!())
        .expect("error while running tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                let state = app_handle.state::<PythonProcess>();
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(child) = guard.as_mut() {
                        python::stop_python_server(child);
                    }
                    *guard = None;
                }
            }
        });
}

fn main() {
    run();
}
