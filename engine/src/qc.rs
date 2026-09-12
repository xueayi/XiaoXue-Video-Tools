//! 素材质量检测 (移植自 src/qc.py)。
//!
//! 通过 ffprobe 收集媒体信息, 检查 PR 兼容性与用户阈值。

use std::path::Path;

use serde::Serialize;

use crate::paths::find_tool;

const PR_INCOMPATIBLE_CONTAINERS: &[&str] = &[".mkv", ".webm", ".ogv", ".ogg", ".flv"];
const PR_INCOMPATIBLE_CODECS: &[&str] = &["vp8", "vp9", "av1", "theora"];
const PR_INCOMPATIBLE_IMAGES: &[&str] = &[".webp", ".heic", ".avif"];
const COMMON_IMAGE_EXTENSIONS: &[&str] = &[
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".avif", ".webp",
];

#[derive(Debug, Default, Clone, Serialize)]
pub struct MediaInfo {
    pub path: String,
    pub filename: String,
    pub container: String,
    pub duration_sec: f64,
    pub video_codec: String,
    pub width: u32,
    pub height: u32,
    pub fps: f64,
    pub bitrate_kbps: u64,
    pub audio_codec: String,
    pub audio_bitrate_kbps: u64,
    pub is_valid: bool,
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

impl MediaInfo {
    pub fn new(path: &str) -> Self {
        let filename = Path::new(path)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        let container = Path::new(path)
            .extension()
            .map(|e| format!(".{}", e.to_string_lossy().to_ascii_lowercase()))
            .unwrap_or_default();
        Self {
            path: path.into(),
            filename,
            container,
            ..Default::default()
        }
    }
}

/// 通过文件头魔数检测图片真实格式 (qc.detect_image_format_by_header)。
pub fn detect_image_format_by_header(file_path: &Path) -> Option<String> {
    let bytes = std::fs::read(file_path).ok()?;
    if bytes.len() < 4 {
        return None;
    }
    if bytes.starts_with(b"\xff\xd8\xff") {
        return Some("jpeg".into());
    }
    if bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
        return Some("png".into());
    }
    if bytes.starts_with(b"GIF8") {
        return Some("gif".into());
    }
    if bytes.starts_with(b"BM") {
        return Some("bmp".into());
    }
    if bytes.starts_with(b"II*\x00") || bytes.starts_with(b"MM\x00*") {
        return Some("tiff".into());
    }
    if bytes.starts_with(b"RIFF") && bytes.len() >= 12 && &bytes[8..12] == b"WEBP" {
        return Some("webp".into());
    }
    if bytes.len() >= 12 && &bytes[4..8] == b"ftyp" {
        let brand = &bytes[8..12];
        if [b"heic".as_slice(), b"heix", b"hevc", b"hevx", b"mif1"].contains(&brand) {
            return Some("heic".into());
        }
        if [b"avif".as_slice(), b"avis"].contains(&brand) {
            return Some("avif".into());
        }
    }
    None
}

/// 检测格式 -> 预期扩展名 (qc.get_expected_extension)。
pub fn get_expected_extension(detected: &str) -> &'static str {
    match detected {
        "jpeg" => ".jpg",
        "png" => ".png",
        "gif" => ".gif",
        "bmp" => ".bmp",
        "tiff" => ".tiff",
        "webp" => ".webp",
        "heic" => ".heic",
        "avif" => ".avif",
        _ => "",
    }
}

/// 解析 ffprobe JSON 为 MediaInfo (qc._parse_ffprobe_output)。
pub fn parse_probe_output(path: &str, data: &serde_json::Value) -> MediaInfo {
    let mut info = MediaInfo::new(path);
    let fmt = &data["format"];
    info.duration_sec = fmt["duration"].as_str().and_then(|d| d.parse().ok()).unwrap_or(0.0);
    info.bitrate_kbps = fmt["bit_rate"].as_str().and_then(|b| b.parse().ok()).unwrap_or(0) / 1000;

    for stream in data["streams"].as_array().map(|a| a.as_slice()).unwrap_or(&[]) {
        match stream["codec_type"].as_str() {
            Some("video") => {
                info.video_codec = stream["codec_name"].as_str().unwrap_or("unknown").into();
                info.width = stream["width"].as_u64().unwrap_or(0) as u32;
                info.height = stream["height"].as_u64().unwrap_or(0) as u32;
                if let Some(fps_str) = stream["r_frame_rate"].as_str() {
                    let parts: Vec<&str> = fps_str.split('/').collect();
                    if parts.len() == 2 {
                        match (parts[0].trim().parse::<f64>(), parts[1].trim().parse::<f64>()) {
                            (Ok(num), Ok(den)) if den != 0.0 => {
                                info.fps = (num / den * 100.0).round() / 100.0;
                            }
                            _ => info.fps = 0.0,
                        }
                    } else {
                        info.fps = 0.0;
                    }
                }
            }
            Some("audio") => {
                info.audio_codec = stream["codec_name"].as_str().unwrap_or("unknown").into();
                info.audio_bitrate_kbps =
                    stream["bit_rate"].as_str().and_then(|b| b.parse().ok()).unwrap_or(0) / 1000;
            }
            _ => {}
        }
    }
    info
}

/// 调用 ffprobe 探测 (qc.probe_media)。
pub fn probe_media(file_path: &Path) -> MediaInfo {
    let mut info = MediaInfo::new(file_path.to_string_lossy().as_ref());
    let output = std::process::Command::new(find_tool("ffprobe"))
        .args(["-v", "error", "-show_format", "-show_streams",
               "-print_format", "json"])
        .arg(file_path)
        .output();
    match output {
        Err(e) => {
            info.is_valid = false;
            info.errors.push(format!("探测失败: {e}"));
        }
        Ok(out) if !out.status.success() => {
            info.is_valid = false;
            info.errors.push(format!(
                "无法读取文件: {}",
                String::from_utf8_lossy(&out.stderr).trim()
            ));
        }
        Ok(out) => match serde_json::from_slice::<serde_json::Value>(&out.stdout) {
            Ok(data) => info = parse_probe_output(info.path.as_str(), &data),
            Err(e) => {
                info.is_valid = false;
                info.errors.push(format!("探测失败: {e}"));
            }
        },
    }
    info
}

/// 兼容性检查参数 (qc.check_compatibility 的选项集合)。
#[derive(Debug, Default, Clone)]
pub struct CompatibilityRules {
    pub max_bitrate_kbps: u64,
    pub max_resolution: String,
    pub min_bitrate_kbps: u64,
    pub min_resolution: String,
    pub check_pr_video: bool,
    pub check_pr_image: bool,
    pub custom_containers: Vec<String>,
    pub custom_codecs: Vec<String>,
    pub custom_images: Vec<String>,
}

/// 兼容性/阈值检查结果追加到 info (qc.check_compatibility)。
pub fn check_compatibility(info: &mut MediaInfo, rules: &CompatibilityRules) {
    let max_bitrate_kbps = rules.max_bitrate_kbps;
    let max_resolution = rules.max_resolution.as_str();
    let min_bitrate_kbps = rules.min_bitrate_kbps;
    let min_resolution = rules.min_resolution.as_str();
    let check_pr_video = rules.check_pr_video;
    let check_pr_image = rules.check_pr_image;
    let custom_containers = &rules.custom_containers;
    let custom_codecs = &rules.custom_codecs;
    let custom_images = &rules.custom_images;
    // 1. 阈值
    if max_bitrate_kbps > 0 && info.bitrate_kbps > max_bitrate_kbps {
        info.warnings.push(format!(
            "码率 {}kbps 超过最大阈值 {max_bitrate_kbps}kbps", info.bitrate_kbps
        ));
    }
    if min_bitrate_kbps > 0 && info.bitrate_kbps < min_bitrate_kbps {
        info.warnings.push(format!(
            "码率 {}kbps 低于最小阈值 {min_bitrate_kbps}kbps", info.bitrate_kbps
        ));
    }
    for (spec, is_max) in [(max_resolution, true), (min_resolution, false)] {
        if spec.is_empty() {
            continue;
        }
        let parts: Vec<&str> = spec.split('x').collect();
        if parts.len() != 2 {
            continue;
        }
        if let (Ok(max_w), Ok(max_h)) =
            (parts[0].trim().parse::<u32>(), parts[1].trim().parse::<u32>())
        {
            if is_max && (info.width > max_w || info.height > max_h) {
                info.warnings.push(format!(
                    "分辨率 {}x{} 超过最大阈值 {spec}", info.width, info.height
                ));
            }
            if !is_max && (info.width < max_w || info.height < max_h) {
                info.warnings.push(format!(
                    "分辨率 {}x{} 低于最小阈值 {spec}", info.width, info.height
                ));
            }
        }
    }

    // 2. PR 兼容性
    if check_pr_video {
        let containers: Vec<String> = if custom_containers.is_empty() {
            PR_INCOMPATIBLE_CONTAINERS.iter().map(|s| s.to_string()).collect()
        } else {
            custom_containers.to_vec()
        };
        let codecs: Vec<String> = if custom_codecs.is_empty() {
            PR_INCOMPATIBLE_CODECS.iter().map(|s| s.to_string()).collect()
        } else {
            custom_codecs.to_vec()
        };
        if containers.contains(&info.container) {
            info.warnings
                .push(format!("[兼容性] 容器 {} 可能导致兼容性问题", info.container));
        }
        if codecs.contains(&info.video_codec.to_lowercase()) {
            info.warnings
                .push(format!("[兼容性] 编码 {} 可能导致兼容性问题", info.video_codec));
        }
        if info.container == ".mkv" {
            info.warnings
                .push("[兼容性] MKV 封装对某些软件不友好，建议转封装为 MP4/MOV".into());
        }
    }

    if check_pr_image {
        let images: Vec<String> = if custom_images.is_empty() {
            PR_INCOMPATIBLE_IMAGES.iter().map(|s| s.to_string()).collect()
        } else {
            custom_images.to_vec()
        };
        if images.contains(&info.container) {
            info.errors
                .push(format!("[兼容性] 图片格式 {} 可能不被支持", info.container));
        }
        if COMMON_IMAGE_EXTENSIONS.contains(&info.container.as_str()) {
            if let Some(detected) = detect_image_format_by_header(Path::new(&info.path)) {
                let expected = get_expected_extension(detected.as_str());
                let equivalent =
                    |ext: &str| -> Vec<String> { vec![ext.to_ascii_lowercase()] };
                let actual_set = equivalent(&info.container.to_lowercase());
                let _expected_set = equivalent(expected);
                // .jpg/.jpeg 与 .tiff/.tif 视为等价扩展名
                let is_equivalent_pair = |a: &str, b: &str| -> bool {
                    (a == ".jpg" && b == ".jpeg")
                        || (a == ".jpeg" && b == ".jpg")
                        || (a == ".tiff" && b == ".tif")
                        || (a == ".tif" && b == ".tiff")
                };
                let mismatch = !actual_set.contains(&expected.to_string())
                    && !actual_set
                        .iter()
                        .any(|a| is_equivalent_pair(a, expected));
                if mismatch {
                    info.warnings.push(format!(
                        "[格式不匹配] 文件实际格式为 {}({expected})，但扩展名为 {}",
                        detected.to_uppercase(),
                        info.container
                    ));
                }
            }
        }
    }
}

/// 扫描目录 (qc.scan_directory)。
#[allow(clippy::too_many_arguments)]
pub fn scan_directory(
    directory: &Path,
    extensions: &[String],
    max_bitrate_kbps: u64,
    max_resolution: &str,
    min_bitrate_kbps: u64,
    min_resolution: &str,
    check_pr_video: bool,
    check_pr_image: bool,
) -> Vec<MediaInfo> {
    let default_exts = [
        ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".ts",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".avif", ".webp",
    ];
    let exts: Vec<String> = if extensions.is_empty() {
        default_exts.iter().map(|s| s.to_string()).collect()
    } else {
        extensions
            .iter()
            .map(|e| {
                let l = e.to_ascii_lowercase();
                if l.starts_with('.') { l } else { format!(".{l}") }
            })
            .collect()
    };
    let mut all = exts.clone();
    all.extend(PR_INCOMPATIBLE_IMAGES.iter().map(|s| s.to_string()));
    all.extend(COMMON_IMAGE_EXTENSIONS.iter().map(|s| s.to_string()));

    let mut results: Vec<MediaInfo> = Vec::new();
    walk(directory, &mut |p| {
        let ext = p
            .extension()
            .map(|e| format!(".{}", e.to_string_lossy().to_ascii_lowercase()))
            .unwrap_or_default();
        if !all.contains(&ext) {
            return;
        }
        let mut info = probe_media(p);
        check_compatibility(
            &mut info,
            &CompatibilityRules {
                max_bitrate_kbps,
                max_resolution: max_resolution.into(),
                min_bitrate_kbps,
                min_resolution: min_resolution.into(),
                check_pr_video,
                check_pr_image,
                ..Default::default()
            },
        );
        results.push(info);
    });
    results
}

fn walk(dir: &Path, f: &mut impl FnMut(&Path)) {
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.is_dir() {
                walk(&p, f);
            } else {
                f(&p);
            }
        }
    }
}

/// 生成 QC 报告 (qc.generate_report), 返回报告内容并写出。
pub fn generate_report(results: &[MediaInfo], output_path: &Path) -> String {
    let sep = "=".repeat(60);
    let mut lines: Vec<String> = vec![
        sep.clone(),
        "小雪工具箱 - 素材质量检测报告 (QC Report)".into(),
        sep.clone(),
        String::new(),
    ];
    let total = results.len();
    let errors_count = results.iter().filter(|r| !r.errors.is_empty()).count();
    let warnings_count = results.iter().filter(|r| !r.warnings.is_empty()).count();

    lines.push(format!("总计扫描: {total} 个文件"));
    lines.push(format!("  通过: {ok}", ok = total - errors_count));
    lines.push(format!("  警告: {warnings_count}"));
    lines.push(format!("  错误: {errors_count}"));
    lines.push(String::new());
    lines.push("-".repeat(60));

    for info in results {
        let icon = if !info.errors.is_empty() {
            "✗"
        } else if !info.warnings.is_empty() {
            "⚠"
        } else {
            "✓"
        };
        lines.push(String::new());
        lines.push(format!("[{icon}] {}", info.filename));
        lines.push(format!("    路径: {}", info.path));
        if info.is_valid {
            lines.push(format!(
                "    容器: {} | 编码: {} | 分辨率: {}x{}",
                info.container, info.video_codec, info.width, info.height
            ));
            lines.push(format!(
                "    帧率: {} FPS | 码率: {} kbps | 时长: {:.1}s",
                info.fps, info.bitrate_kbps, info.duration_sec
            ));
        }
        for err in &info.errors {
            lines.push(format!("    [错误] {err}"));
        }
        for warn in &info.warnings {
            lines.push(format!("    [警告] {warn}"));
        }
    }

    lines.push(String::new());
    lines.push(sep.clone());
    lines.push("报告生成完毕".into());

    let content = lines.join("\n");
    if let Some(parent) = output_path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let _ = std::fs::write(output_path, &content);
    content
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn header_detection_all_formats() {
        let dir = tempfile::tempdir().unwrap();
        let cases: &[(&str, &[u8], &str)] = &[
            ("a.jpg", b"\xff\xd8\xff\xe0", "jpeg"),
            ("a.png", b"\x89PNG\r\n\x1a\n", "png"),
            ("a.gif", b"GIF89a", "gif"),
            ("a.bmp", b"BM", "bmp"),
            ("a.tif", b"II*\x00", "tiff"),
            ("b.tif", b"MM\x00*", "tiff"),
            ("a.webp", b"RIFF\x00\x00\x00\x00WEBP", "webp"),
            ("a.heic", b"\x00\x00\x00\x18ftypheic", "heic"),
            ("a.avif", b"\x00\x00\x00\x18ftypavif", "avif"),
            ("a.txt", b"just plain text!", "x"),
        ];
        for (name, magic, expected) in cases {
            let p = dir.path().join(name);
            let mut bytes = magic.to_vec();
            bytes.extend_from_slice(&[0u8; 8]);
            std::fs::write(&p, bytes).unwrap();
            let got = detect_image_format_by_header(&p);
            if *expected == "x" {
                assert_eq!(got, None, "{name}");
            } else {
                assert_eq!(got.as_deref(), Some(*expected), "{name}");
            }
        }
    }

    #[test]
    fn header_detection_short_and_missing() {
        let dir = tempfile::tempdir().unwrap();
        let short = dir.path().join("s.bin");
        std::fs::write(&short, b"\x01\x02").unwrap();
        assert_eq!(detect_image_format_by_header(&short), None);
        assert_eq!(
            detect_image_format_by_header(&dir.path().join("none")),
            None
        );
    }

    #[test]
    fn expected_extension() {
        assert_eq!(get_expected_extension("jpeg"), ".jpg");
        assert_eq!(get_expected_extension("heic"), ".heic");
        assert_eq!(get_expected_extension("unknown"), "");
    }

    #[test]
    fn parse_and_bad_fps() {
        let data = serde_json::json!({
            "format": {"duration": "10.5", "bit_rate": "5000000"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264",
                 "width": 1920, "height": 1080, "r_frame_rate": "a/b"},
                {"codec_type": "audio", "codec_name": "aac", "bit_rate": "192000"}
            ]
        });
        let info = parse_probe_output("x.mp4", &data);
        assert_eq!(info.video_codec, "h264");
        assert_eq!(info.fps, 0.0);
        assert_eq!(info.audio_bitrate_kbps, 192);
        assert_eq!(info.bitrate_kbps, 5000);
    }

    #[test]
    fn compatibility_thresholds_and_pr() {
        let mut info = MediaInfo::new("C:/v.mkv");
        info.video_codec = "vp9".into();
        info.width = 3840;
        info.height = 2160;
        info.bitrate_kbps = 9000;
        check_compatibility(&mut info, &CompatibilityRules {
            max_bitrate_kbps: 8000,
            max_resolution: "1920x1080".into(),
            check_pr_video: true,
            ..Default::default()
        });
        assert!(info.warnings.iter().any(|w| w.contains("超过最大阈值")));
        assert!(info.warnings.iter().any(|w| w.contains("MKV")));
        assert!(info.warnings.iter().any(|w| w.contains("编码")));
    }

    #[test]
    fn compatibility_min_thresholds() {
        let mut info = MediaInfo::new("C:/v.mp4");
        info.width = 640;
        info.height = 480;
        info.bitrate_kbps = 100;
        check_compatibility(&mut info, &CompatibilityRules {
            min_bitrate_kbps: 500,
            min_resolution: "1920x1080".into(),
            ..Default::default()
        });
        assert!(info.warnings.iter().any(|w| w.contains("低于最小阈值")));
        assert!(info.warnings.iter().any(|w| w.contains("低于最小阈值")));
    }

    #[test]
    fn scan_and_report() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("a.mp4"), b"x").unwrap();
        std::fs::write(dir.path().join("b.png"), b"x").unwrap();

        // probe 走真实 ffprobe 会失败 (假文件), 报告应包含错误条目
        let results = scan_directory(dir.path(), &[], 0, "", 0, "", true, true);
        assert_eq!(results.len(), 2);
        assert!(results.iter().all(|r| !r.is_valid));

        let out = dir.path().join("qc.txt");
        let content = generate_report(&results, &out);
        assert!(out.exists());
        assert!(content.contains("✗"));
    }
}
