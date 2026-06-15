use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::State;

pub struct PythonProcess(pub Mutex<Option<Child>>);

impl Drop for PythonProcess {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.0.lock() {
            if let Some(child) = guard.as_mut() {
                stop_python_server(child);
            }
        }
    }
}

pub fn start_python_server(port: u16) -> Result<Child, String> {
    let python = python_command();
    Command::new(python)
        .arg("backend/main.py")
        .env("PILOT_SERVER_PORT", port.to_string())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("Failed to start Python backend: {error}"))
}

pub fn stop_python_server(child: &mut Child) {
    if child.try_wait().ok().flatten().is_some() {
        return;
    }
    let _ = child.kill();
    let deadline = Instant::now() + Duration::from_secs(5);
    while Instant::now() < deadline {
        if child.try_wait().ok().flatten().is_some() {
            return;
        }
        thread::sleep(Duration::from_millis(100));
    }
    let _ = child.kill();
}

#[tauri::command]
pub async fn check_backend_health(_state: State<'_, PythonProcess>) -> Result<bool, String> {
    let response = reqwest::get("http://127.0.0.1:8765/health")
        .await
        .map_err(|error| error.to_string())?;
    Ok(response.status().is_success())
}

async fn wait_for_backend() -> Result<(), String> {
    let started = Instant::now();
    while started.elapsed() < Duration::from_secs(30) {
        if let Ok(response) = reqwest::get("http://127.0.0.1:8765/health").await {
            if response.status().is_success() {
                return Ok(());
            }
        }
        tokio_sleep(Duration::from_millis(500)).await;
    }
    Err("Python backend did not become healthy within 30 seconds".to_string())
}

pub async fn start_and_wait(state: &PythonProcess, port: u16) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|_| "Python process lock poisoned".to_string())?;
    if guard.is_none() {
        *guard = Some(start_python_server(port)?);
    }
    drop(guard);
    wait_for_backend().await
}

async fn tokio_sleep(duration: Duration) {
    std::thread::sleep(duration);
}

fn python_command() -> &'static str {
    if cfg!(target_os = "windows") {
        "py"
    } else {
        "python3"
    }
}
