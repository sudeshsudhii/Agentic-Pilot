use serde::Serialize;
use std::process::Command;

#[derive(Debug, Serialize)]
pub struct OllamaStatus {
    installed: bool,
    running: bool,
    models: Vec<String>,
}

pub fn check_ollama_installed() -> bool {
    Command::new("ollama")
        .arg("--version")
        .output()
        .map(|output| output.status.success())
        .unwrap_or(false)
}

pub async fn check_ollama_running() -> bool {
    reqwest::get("http://localhost:11434/api/tags")
        .await
        .map(|response| response.status().is_success())
        .unwrap_or(false)
}

pub async fn list_available_models() -> Vec<String> {
    let response = match reqwest::get("http://localhost:11434/api/tags").await {
        Ok(response) => response,
        Err(_) => return Vec::new(),
    };
    let body: serde_json::Value = match response.json().await {
        Ok(body) => body,
        Err(_) => return Vec::new(),
    };
    body.get("models")
        .and_then(|models| models.as_array())
        .map(|models| {
            models
                .iter()
                .filter_map(|model| model.get("name").and_then(|name| name.as_str()).map(str::to_string))
                .collect()
        })
        .unwrap_or_default()
}

#[tauri::command]
pub async fn get_ollama_status() -> OllamaStatus {
    let installed = check_ollama_installed();
    let running = check_ollama_running().await;
    let models = if running { list_available_models().await } else { Vec::new() };
    OllamaStatus {
        installed,
        running,
        models,
    }
}
