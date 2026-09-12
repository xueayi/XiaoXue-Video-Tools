//! 小雪工具箱 Tauri 壳层: 将 engine 的能力以 command 形式暴露给前端。

mod tasks;

use std::path::Path;
use xiaoxue_engine as engine;

#[tauri::command]
fn app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

#[tauri::command]
fn quality_preset_names() -> Vec<&'static str> {
    engine::ffmpeg::quality_preset_names()
}

#[tauri::command]
fn preview_encode_command(
    opts: engine::ffmpeg::EncodeOptions,
) -> Vec<String> {
    engine::ffmpeg::build_encode_command(&opts)
}

#[tauri::command]
fn probe_media(path: String) -> engine::probe::MediaInfo {
    engine::probe::probe_media(&path)
}

// ---- 任务执行 (命令定义在 tasks 模块) ----

#[tauri::command]
fn build_replace_audio_cmd(video: String, audio: String, output: String,
                           audio_encoder: String, audio_bitrate: String) -> Vec<String> {
    engine::ffmpeg::build_replace_audio_command(
        &video, &audio, &output, &audio_encoder, &audio_bitrate)
}

#[tauri::command]
fn build_extract_audio_cmd(input: String, output: String,
                           audio_encoder: String, audio_bitrate: String) -> Vec<String> {
    engine::ffmpeg::build_extract_audio_command(&input, &output, &audio_encoder, &audio_bitrate)
}

#[tauri::command]
fn build_extract_video_cmd(input: String, output: String) -> Vec<String> {
    engine::ffmpeg::build_extract_video_command(&input, &output)
}

#[tauri::command]
fn plan_remux_cmd(inputs: Vec<String>, output_dir: String, extension: String,
                  overwrite: bool, audio_tracks: String, audio_custom: String,
                  subtitle_tracks: String, subtitle_custom: String,
                  ) -> engine::ffmpeg::RemuxPlan {
    engine::ffmpeg::plan_remux_commands(
        &inputs, &output_dir, &extension, overwrite,
        &audio_tracks, &audio_custom, &subtitle_tracks, &subtitle_custom)
}

// ---- 批量工具 (非长任务, 直接执行返回结果) ----

#[derive(serde::Serialize)]
struct BatchOutcome {
    ok: u32,
    fail: u32,
    errors: Vec<String>,
}

#[tauri::command]
fn create_folders_cmd(txt_path: String, output_dir: String,
                      auto_number: bool) -> BatchOutcome {
    let (ok, fail, errors) = engine::folder::batch_create_folders(
        Path::new(&txt_path), Path::new(&output_dir), auto_number);
    BatchOutcome { ok, fail, errors }
}

#[tauri::command]
fn batch_rename_cmd(input_dir: String, config: engine::batch::RenameConfig) -> BatchOutcome {
    let (ok, fail, errors) = engine::batch::batch_rename(Path::new(&input_dir), &config);
    BatchOutcome { ok, fail, errors }
}

// ---- 通知 ----

#[tauri::command]
fn send_feishu_cmd(webhook_url: String, title: String, content: String,
                   color: String, footer: String) -> Result<(), String> {
    engine::notify::send_feishu(&webhook_url, &title, &content, &color, &footer)
}

#[tauri::command]
fn send_webhook_cmd(url: String, headers: Vec<(String, String)>,
                    body: serde_json::Value) -> Result<(), String> {
    engine::notify::send_webhook(&url, &headers, &body)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(tasks::TaskState::default())
        .invoke_handler(tauri::generate_handler![
            tasks::start_task,
            tasks::stop_task,
            app_version,
            quality_preset_names,
            preview_encode_command,
            probe_media,
            build_replace_audio_cmd,
            build_extract_audio_cmd,
            build_extract_video_cmd,
            plan_remux_cmd,
            create_folders_cmd,
            batch_rename_cmd,
            send_feishu_cmd,
            send_webhook_cmd,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
