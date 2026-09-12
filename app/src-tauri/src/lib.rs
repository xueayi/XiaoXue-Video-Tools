//! 小雪工具箱 Tauri 壳层: 将 engine 的能力以 command 形式暴露给前端。

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            app_version,
            quality_preset_names,
            preview_encode_command,
            probe_media,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
