use std::process::{Child, Command, Stdio};

pub fn start_model_download(model: &str) -> Result<Child, String> {
    Command::new("ollama")
        .arg("pull")
        .arg(model)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("Failed to start ollama pull: {error}"))
}

pub fn recommended_models() -> Vec<&'static str> {
    vec!["qwen2.5:7b", "gemma:7b"]
}
