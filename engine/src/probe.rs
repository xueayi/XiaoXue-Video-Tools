//! 媒体元数据探测 (移植自 src/media_probe.py)。
//!
//! 纯解析函数 [`parse_probe_output`] 可独立测试;
//! [`probe_media`] 负责调起 ffprobe 进程。

use std::collections::HashMap;
use std::path::Path;

use serde::Deserialize;

/// ffprobe 输出文件定位 (utils.get_ffprobe_path)。
pub fn ffprobe_path() -> String {
    crate::paths::find_tool("ffprobe")
}

#[derive(Debug, Default, Clone, serde::Serialize)]
pub struct StreamInfo {
    pub index: usize,
    pub stream_index: usize,
    pub codec_name: String,
    pub profile: String,
    pub language: String,
    pub title: String,
    pub width: u32,
    pub height: u32,
    pub fps: f64,
    pub bitrate_kbps: u64,
    pub sample_rate: u32,
    pub channels: u32,
    pub channel_layout: String,
    pub pix_fmt: String,
}

#[derive(Debug, Default, Clone, serde::Serialize)]
pub struct Chapter {
    pub id: i64,
    pub start_time: f64,
    pub end_time: f64,
    pub title: String,
}

#[derive(Debug, Default, Clone, serde::Serialize)]
pub struct MediaInfo {
    pub path: String,
    pub filename: String,
    pub format_name: String,
    pub format_long_name: String,
    pub duration_sec: f64,
    pub total_bitrate_kbps: u64,
    pub video_streams: Vec<StreamInfo>,
    pub audio_streams: Vec<StreamInfo>,
    pub subtitle_streams: Vec<StreamInfo>,
    pub chapters: Vec<Chapter>,
    pub errors: Vec<String>,
}

impl MediaInfo {
    pub fn new(path: &str) -> Self {
        let filename = Path::new(path)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        Self { path: path.into(), filename, ..Default::default() }
    }
}

// ----------------------------------------------------------------
// ffprobe JSON 反序列化 (字段全部宽松可选)
// ----------------------------------------------------------------

#[derive(Deserialize, Default)]
#[serde(default)]
struct RawFormat {
    format_name: String,
    format_long_name: String,
    duration: Option<String>,
    bit_rate: Option<String>,
}

#[derive(Deserialize, Default)]
#[serde(default)]
struct RawTags {
    language: String,
    title: String,
}

#[derive(Deserialize, Default)]
#[serde(default)]
struct RawStream {
    index: usize,
    codec_type: String,
    codec_name: String,
    profile: String,
    level: serde_json::Value,
    width: u32,
    height: u32,
    r_frame_rate: Option<String>,
    bit_rate: Option<String>,
    sample_rate: Option<String>,
    channels: u32,
    channel_layout: String,
    pix_fmt: String,
    tags: RawTags,
}

#[derive(Deserialize, Default)]
#[serde(default)]
struct RawChapter {
    id: i64,
    start_time: String,
    end_time: String,
    tags: RawTags,
}

#[derive(Deserialize, Default)]
#[serde(default)]
pub struct RawProbe {
    format: RawFormat,
    streams: Vec<RawStream>,
    chapters: Vec<RawChapter>,
}

fn parse_fps(s: &str) -> f64 {
    let mut parts = s.splitn(2, '/');
    let num: f64 = match parts.next().unwrap_or("").trim().parse() {
        Ok(v) => v,
        Err(_) => return 0.0,
    };
    let den: f64 = match parts.next().unwrap_or("1").trim().parse() {
        Ok(v) => v,
        Err(_) => return 0.0,
    };
    if den == 0.0 {
        return 0.0;
    }
    (num / den * 1000.0).round() / 1000.0
}

fn parse_u64(s: &str) -> u64 {
    s.trim().parse().unwrap_or(0)
}

/// 解析 ffprobe JSON (media_probe._parse_detailed_output)。
pub fn parse_probe_output(path: &str, data: &RawProbe) -> MediaInfo {
    let mut info = MediaInfo::new(path);

    info.format_name = data.format.format_name.clone();
    info.format_long_name = data.format.format_long_name.clone();
    info.duration_sec = data
        .format
        .duration
        .as_deref()
        .and_then(|d| d.parse().ok())
        .unwrap_or(0.0);
    info.total_bitrate_kbps =
        data.format.bit_rate.as_deref().map(parse_u64).unwrap_or(0) / 1000;

    let mut video_idx = 0usize;
    let mut audio_idx = 0usize;
    let mut sub_idx = 0usize;

    for s in &data.streams {
        let mut si = StreamInfo {
            index: 0,
            stream_index: s.index,
            codec_name: s.codec_name.clone(),
            profile: s.profile.clone(),
            language: s.tags.language.clone(),
            title: s.tags.title.clone(),
            width: s.width,
            height: s.height,
            fps: s.r_frame_rate.as_deref().map(parse_fps).unwrap_or(0.0),
            bitrate_kbps: s.bit_rate.as_deref().map(parse_u64).unwrap_or(0) / 1000,
            sample_rate: s.sample_rate.as_deref().map(parse_u64).unwrap_or(0) as u32,
            channels: s.channels,
            channel_layout: s.channel_layout.clone(),
            pix_fmt: s.pix_fmt.clone(),
        };
        match s.codec_type.as_str() {
            "video" => {
                si.index = video_idx;
                video_idx += 1;
                info.video_streams.push(si);
            }
            "audio" => {
                si.index = audio_idx;
                audio_idx += 1;
                info.audio_streams.push(si);
            }
            "subtitle" => {
                si.index = sub_idx;
                sub_idx += 1;
                info.subtitle_streams.push(si);
            }
            _ => {}
        }
    }

    for c in &data.chapters {
        info.chapters.push(Chapter {
            id: c.id,
            start_time: c.start_time.parse().unwrap_or(0.0),
            end_time: c.end_time.parse().unwrap_or(0.0),
            title: c.tags.title.clone(),
        });
    }
    info
}

/// 调用 ffprobe 探测文件 (media_probe.probe_detailed)。
pub fn probe_media(file_path: &str) -> MediaInfo {
    let mut info = MediaInfo::new(file_path);
    let ffprobe = ffprobe_path();
    let output = std::process::Command::new(&ffprobe)
        .args(["-v", "error", "-show_format", "-show_streams",
               "-show_chapters", "-print_format", "json", file_path])
        .output();
    match output {
        Err(e) => {
            info.errors.push(format!("探测失败: {e}"));
        }
        Ok(out) if !out.status.success() => {
            let stderr = String::from_utf8_lossy(&out.stderr);
            info.errors
                .push(format!("ffprobe 无法读取文件: {}", stderr.trim()));
        }
        Ok(out) => match serde_json::from_slice::<RawProbe>(&out.stdout) {
            Ok(raw) => info = parse_probe_output(file_path, &raw),
            Err(e) => info.errors.push(format!("探测失败: {e}")),
        },
    }
    info
}

// ----------------------------------------------------------------
// 展示辅助
// ----------------------------------------------------------------

pub fn format_file_size(size_bytes: u64) -> String {
    if size_bytes == 0 {
        return "未知".into();
    }
    if size_bytes < 1024 {
        return format!("{size_bytes} B");
    }
    if size_bytes < 1024 * 1024 {
        return format!("{:.1} KB", size_bytes as f64 / 1024.0);
    }
    if size_bytes < 1024 * 1024 * 1024 {
        return format!("{:.2} MB", size_bytes as f64 / (1024.0 * 1024.0));
    }
    format!("{:.2} GB", size_bytes as f64 / (1024.0 * 1024.0 * 1024.0))
}

pub fn format_duration(seconds: f64) -> String {
    if seconds <= 0.0 {
        return "00:00:00".into();
    }
    let hours = (seconds / 3600.0).floor() as u32;
    let minutes = ((seconds % 3600.0) / 60.0).floor() as u32;
    let secs = seconds % 60.0;
    format!("{hours:02}:{minutes:02}:{secs:05.2}")
}

/// 语言代码展示 (常用映射; 未知代码原样展示)。
pub fn language_display(lang: &str) -> String {
    if lang.is_empty() {
        return String::new();
    }
    let mut names: HashMap<&str, &str> = HashMap::new();
    names.insert("chi", "Chinese");
    names.insert("zho", "Chinese");
    names.insert("jpn", "Japanese");
    names.insert("eng", "English");
    names.insert("kor", "Korean");
    names.insert("und", "Undetermined");
    match names.get(lang) {
        Some(n) => format!("[{lang}] {n}"),
        None => format!("[{lang}]"),
    }
}

/// 格式化可读报告 (media_probe.format_media_report, 精简版)。
pub fn format_media_report(info: &MediaInfo) -> String {
    let sep = "=".repeat(60);
    let mut lines: Vec<String> = vec![
        sep.clone(),
        format!("文件: {}", info.filename),
        format!("路径: {}", info.path),
        format!("大小: {}", format_file_size(0)), // 文件大小由调用方按需补
        format!("时长: {}", format_duration(info.duration_sec)),
    ];
    if !info.format_name.is_empty() {
        if info.format_long_name.is_empty() {
            lines.push(format!("容器: {}", info.format_name));
        } else {
            lines.push(format!(
                "容器: {} ({})",
                info.format_name, info.format_long_name
            ));
        }
    }
    if info.total_bitrate_kbps > 0 {
        lines.push(format!("总码率: {} kbps", info.total_bitrate_kbps));
    }
    lines.push(sep.clone());

    if !info.errors.is_empty() {
        for err in &info.errors {
            lines.push(format!("  [错误] {err}"));
        }
        return lines.join("\n");
    }

    for vs in &info.video_streams {
        lines.push(String::new());
        lines.push(format!("  ── 视频流 #{} {}", vs.index, "─".repeat(40)));
        let mut codec = vs.codec_name.clone();
        if !vs.profile.is_empty() {
            codec += &format!(" ({})", vs.profile);
        }
        lines.push(format!("  编码器:      {codec}"));
        if vs.width > 0 && vs.height > 0 {
            lines.push(format!("  分辨率:      {}x{}", vs.width, vs.height));
        }
        if vs.fps > 0.0 {
            lines.push(format!("  帧率:        {} fps", vs.fps));
        }
        if vs.bitrate_kbps > 0 {
            lines.push(format!("  码率:        {} kbps", vs.bitrate_kbps));
        }
    }

    for aus in &info.audio_streams {
        lines.push(String::new());
        let lang = language_display(&aus.language);
        let mut extra = String::new();
        if !lang.is_empty() {
            extra += &format!(" {lang}");
        }
        if !aus.title.is_empty() {
            extra += &format!(" {}", aus.title);
        }
        lines.push(format!("  ── 音频流 #{} ──{extra}", aus.index));
        lines.push(format!("  编码器:      {}", aus.codec_name));
        if aus.sample_rate > 0 {
            lines.push(format!("  采样率:      {} Hz", aus.sample_rate));
        }
        if aus.channels > 0 {
            lines.push(format!("  声道:        {}", aus.channels));
        }
    }

    lines.push("─".repeat(60));
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = r#"{
        "format": {"format_name": "mov,mp4", "format_long_name": "QuickTime/MPEG-4",
                    "duration": "61.5", "bit_rate": "2000000"},
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264",
             "profile": "High", "level": 41, "width": 1920, "height": 1080,
             "pix_fmt": "yuv420p", "r_frame_rate": "30000/1001",
             "bit_rate": "1800000", "tags": {"language": "und"}},
            {"index": 1, "codec_type": "audio", "codec_name": "aac",
             "sample_rate": "48000", "channels": 2, "channel_layout": "stereo",
             "bit_rate": "192000", "tags": {"language": "jpn", "title": "主音轨"}},
            {"index": 2, "codec_type": "subtitle", "codec_name": "ass",
             "tags": {"language": "chi"}}
        ],
        "chapters": [{"id": 0, "start_time": "0", "end_time": "30",
                      "tags": {"title": "开头"}}]
    }"#;

    fn sample_info() -> MediaInfo {
        let raw: RawProbe = serde_json::from_str(SAMPLE).unwrap();
        parse_probe_output("C:/a.mp4", &raw)
    }

    #[test]
    fn parse_full_sample() {
        let info = sample_info();
        assert_eq!(info.format_name, "mov,mp4");
        assert_eq!(info.duration_sec, 61.5);
        assert_eq!(info.total_bitrate_kbps, 2000);
        let vs = &info.video_streams[0];
        assert_eq!((vs.width, vs.height), (1920, 1080));
        assert!((vs.fps - 29.97).abs() < 0.01);
        assert_eq!(vs.profile, "High");
        let au = &info.audio_streams[0];
        assert_eq!(au.sample_rate, 48000);
        assert_eq!(au.title, "主音轨");
        assert_eq!(info.subtitle_streams.len(), 1);
        assert_eq!(info.chapters[0].title, "开头");
        assert!(info.errors.is_empty());
    }

    #[test]
    fn parse_bad_values_tolerated() {
        let raw: RawProbe = serde_json::from_str(
            r#"{"streams": [
                {"codec_type": "video", "codec_name": "h264",
                 "r_frame_rate": "0/0", "bit_rate": "abc", "level": 41},
                {"codec_type": "audio", "codec_name": "aac", "bit_rate": null}
            ]}"#,
        )
        .unwrap();
        let info = parse_probe_output("C:/x.mp4", &raw);
        assert_eq!(info.video_streams[0].fps, 0.0);
        assert_eq!(info.video_streams[0].bitrate_kbps, 0);
        assert_eq!(info.audio_streams[0].bitrate_kbps, 0);
    }

    #[test]
    fn probe_missing_file_reports_error() {
        let info = probe_media("Z:/definitely-not-exists.mp4");
        assert!(!info.errors.is_empty());
    }

    #[test]
    fn size_formatting() {
        assert_eq!(format_file_size(0), "未知");
        assert_eq!(format_file_size(512), "512 B");
        assert_eq!(format_file_size(2048), "2.0 KB");
        assert_eq!(format_file_size(5 * 1024 * 1024), "5.00 MB");
        assert_eq!(format_file_size(3 * 1024 * 1024 * 1024), "3.00 GB");
    }

    #[test]
    fn duration_formatting() {
        assert_eq!(format_duration(0.0), "00:00:00");
        assert_eq!(format_duration(-5.0), "00:00:00");
        assert_eq!(format_duration(3661.5), "01:01:01.50");
    }

    #[test]
    fn language_display_cases() {
        assert_eq!(language_display(""), "");
        assert!(language_display("jpn").starts_with("[jpn]"));
        assert_eq!(language_display("xyz"), "[xyz]");
    }

    #[test]
    fn report_contains_streams() {
        let info = sample_info();
        let report = format_media_report(&info);
        assert!(report.contains("视频流 #0"));
        assert!(report.contains("High"));
        assert!(report.contains("音频流 #0"));
        assert!(report.contains("主音轨"));
    }

    #[test]
    fn report_with_errors_short_circuits() {
        let mut info = MediaInfo::new("C:/a.mp4");
        info.errors.push("boom".into());
        let report = format_media_report(&info);
        assert!(report.contains("[错误] boom"));
    }
}
