//! FFmpeg 命令构建 (移植自 src/core.py)。
//!
//! 纯函数: 输入参数 -> 完整 ffmpeg 命令行。与 Python 版逐分支对齐,
//! 测试矩阵亦对齐 (tests/test_core_full.py)。

/// 编码器显示名/标识 -> ffmpeg 编码器名 (presets.ENCODERS 的值域)。
pub fn resolve_encoder(encoder: &str) -> String {
    encoder.to_string()
}

/// 路径转义 (用于 subtitles 滤镜): 反斜杠转正斜杠、冒号与单引号转义。
pub fn escape_path_for_ffmpeg(path: &str) -> String {
    path.replace('\\', "/")
        .replace(':', "\\:")
        .replace('\'', "'\\''")
}

/// 根据流选择模式生成 -map 参数。
///
/// * `stream_type`: "a"=音频, "s"=字幕
/// * `track_option`: "all"/"none"/"custom"/数字字符串
pub fn stream_map_args(stream_type: &str, track_option: &str, custom_indices: &str) -> Vec<String> {
    let mut args: Vec<String> = Vec::new();
    match track_option {
        "none" => {
            args.push(if stream_type == "a" { "-an" } else { "-sn" }.to_string());
        }
        "all" => {
            args.push("-map".into());
            args.push(format!("0:{stream_type}?"));
        }
        "custom" if !custom_indices.trim().is_empty() => {
            for idx in custom_indices.split(',') {
                let idx = idx.trim();
                if !idx.is_empty() && idx.chars().all(|c| c.is_ascii_digit()) {
                    args.push("-map".into());
                    args.push(format!("0:{stream_type}:{idx}?"));
                }
            }
        }
        _ => {
            if !track_option.is_empty() && track_option.chars().all(|c| c.is_ascii_digit()) {
                args.push("-map".into());
                args.push(format!("0:{stream_type}:{track_option}?"));
            } else {
                args.push("-map".into());
                args.push(format!("0:{stream_type}?"));
            }
        }
    }
    args
}

/// 质量预设参数 (presets.QUALITY_PRESETS)。
pub struct QualityPreset {
    pub encoder: &'static str,
    pub crf: Option<u32>,
    pub cq: Option<u32>,
    pub speed_preset: &'static str,
    pub audio_encoder: &'static str,
    pub audio_bitrate: &'static str,
    pub extra_args: Option<&'static str>,
}

pub const QUALITY_PRESETS: &[(&str, QualityPreset)] = &[
    ("【均衡画质】x264 常用导出 (CRF18)", QualityPreset {
        encoder: "libx264", crf: Some(18), cq: None, speed_preset: "medium",
        audio_encoder: "copy", audio_bitrate: "192k", extra_args: None,
    }),
    ("【较小体积】x264 快速导出 (CRF22)", QualityPreset {
        encoder: "libx264", crf: Some(22), cq: None, speed_preset: "medium",
        audio_encoder: "copy", audio_bitrate: "192k", extra_args: None,
    }),
    ("【极致画质】x264 4K/高动态/AMV (CRF16)", QualityPreset {
        encoder: "libx264", crf: Some(16), cq: None, speed_preset: "slow",
        audio_encoder: "copy", audio_bitrate: "320k", extra_args: None,
    }),
    ("【均衡画质】x265/HEVC 高效压缩 (CRF20)", QualityPreset {
        encoder: "libx265", crf: Some(20), cq: None, speed_preset: "medium",
        audio_encoder: "copy", audio_bitrate: "192k", extra_args: None,
    }),
    ("【速度优先】NVIDIA 显卡加速", QualityPreset {
        encoder: "h264_nvenc", crf: None, cq: Some(23), speed_preset: "p4",
        audio_encoder: "copy", audio_bitrate: "192k",
        extra_args: Some("-rc vbr -b:v 0 -maxrate 20M"),
    }),
    ("【画质优先】NVIDIA 显卡加速 (HQ)", QualityPreset {
        encoder: "h264_nvenc", crf: None, cq: Some(19), speed_preset: "p7",
        audio_encoder: "copy", audio_bitrate: "192k",
        extra_args: Some("-rc vbr -b:v 0 -maxrate 20M"),
    }),
];

pub fn quality_preset(name: &str) -> Option<&'static QualityPreset> {
    QUALITY_PRESETS.iter().find(|(k, _)| *k == name).map(|(_, v)| v)
}

/// 编码命令参数 (core.build_encode_command 的入参)。
pub struct EncodeOptions {
    pub input: String,
    pub output: String,
    pub preset_name: Option<String>,
    pub encoder: Option<String>,
    pub crf: Option<u32>,
    pub bitrate: Option<String>,
    pub speed_preset: Option<String>,
    pub resolution: Option<String>,
    pub fps: Option<u32>,
    pub audio_encoder: String,
    pub audio_bitrate: String,
    pub subtitle_path: Option<String>,
    pub extra_args: Option<String>,
    pub rc_mode: Option<String>,
    pub audio_tracks: String,
    pub audio_tracks_custom: String,
    pub subtitle_tracks: String,
    pub subtitle_tracks_custom: String,
}

impl Default for EncodeOptions {
    fn default() -> Self {
        Self {
            input: "input.mp4".into(),
            output: "output.mp4".into(),
            preset_name: None,
            encoder: None,
            crf: None,
            bitrate: None,
            speed_preset: None,
            resolution: None,
            fps: None,
            audio_encoder: "aac".into(),
            audio_bitrate: "192k".into(),
            subtitle_path: None,
            extra_args: None,
            rc_mode: None,
            audio_tracks: "0".into(),
            audio_tracks_custom: String::new(),
            subtitle_tracks: "none".into(),
            subtitle_tracks_custom: String::new(),
        }
    }
}

fn push_quality(cmd: &mut Vec<String>, encoder: &str, rc_mode: Option<&str>,
                crf: Option<u32>, bitrate: Option<&str>) {
    let is_nvenc = encoder.contains("nvenc");
    let is_qsv = encoder.contains("qsv");
    let is_amf = encoder.contains("amf");

    match rc_mode {
        Some("2pass") => {
            if let Some(b) = bitrate {
                cmd.push("-b:v".into());
                cmd.push(b.into());
                if is_nvenc {
                    cmd.push("-rc".into());
                    cmd.push("vbr_hq".into());
                    cmd.push("-2pass".into());
                    cmd.push("1".into());
                } else if is_amf {
                    cmd.push("-rc".into());
                    cmd.push("vbr_peak".into());
                    cmd.push("-2pass".into());
                    cmd.push("1".into());
                } else {
                    cmd.push("-maxrate".into());
                    cmd.push(b.into());
                    cmd.push("-bufsize".into());
                    cmd.push(b.into());
                }
            } else if let Some(q) = crf {
                push_cq(cmd, is_nvenc, is_qsv, q);
            }
        }
        Some("vbr") => {
            if let Some(b) = bitrate {
                cmd.push("-b:v".into());
                cmd.push(b.into());
                if is_nvenc {
                    cmd.push("-rc".into());
                    cmd.push("vbr".into());
                } else if is_amf {
                    cmd.push("-rc".into());
                    cmd.push("vbr_peak".into());
                }
                cmd.push("-maxrate".into());
                cmd.push(b.into());
                cmd.push("-bufsize".into());
                cmd.push(b.into());
            } else if let Some(q) = crf {
                push_cq(cmd, is_nvenc, is_qsv, q);
            }
        }
        Some("cbr") => {
            if let Some(b) = bitrate {
                cmd.push("-b:v".into());
                cmd.push(b.into());
                if is_nvenc || is_amf {
                    cmd.push("-rc".into());
                    cmd.push("cbr".into());
                }
                cmd.push("-minrate".into());
                cmd.push(b.into());
                cmd.push("-maxrate".into());
                cmd.push(b.into());
                cmd.push("-bufsize".into());
                cmd.push(b.into());
            } else if let Some(q) = crf {
                push_cq(cmd, is_nvenc, is_qsv, q);
            }
        }
        _ => {
            // 默认 CRF/CQ 恒定质量模式; 指定码率时优先码率
            if let Some(b) = bitrate {
                cmd.push("-b:v".into());
                cmd.push(b.into());
            } else if let Some(q) = crf {
                if is_nvenc {
                    cmd.push("-cq".into());
                    cmd.push(q.to_string());
                } else if is_qsv {
                    cmd.push("-global_quality".into());
                    cmd.push(q.to_string());
                } else if is_amf {
                    cmd.push("-qp_i".into());
                    cmd.push(q.to_string());
                    cmd.push("-qp_p".into());
                    cmd.push(q.to_string());
                } else {
                    cmd.push("-crf".into());
                    cmd.push(q.to_string());
                }
            }
        }
    }
}

fn push_cq(cmd: &mut Vec<String>, is_nvenc: bool, is_qsv: bool, q: u32) {
    if is_nvenc {
        cmd.push("-cq".into());
        cmd.push(q.to_string());
    } else if is_qsv {
        cmd.push("-global_quality".into());
        cmd.push(q.to_string());
    } else {
        cmd.push("-crf".into());
        cmd.push(q.to_string());
    }
}

/// 构建视频编码 FFmpeg 命令 (core.build_encode_command 的忠实移植)。
pub fn build_encode_command(opts: &EncodeOptions) -> Vec<String> {
    let mut cmd: Vec<String> = vec![
        "ffmpeg".into(),
        "-y".into(),
        "-i".into(),
        opts.input.clone(),
        "-map".into(),
        "0:v:0".into(),
    ];

    cmd.extend(stream_map_args("a", &opts.audio_tracks, &opts.audio_tracks_custom));
    cmd.extend(stream_map_args("s", &opts.subtitle_tracks, &opts.subtitle_tracks_custom));

    // 预设参数 (自定义值优先)
    let mut encoder = opts.encoder.clone();
    let mut crf = opts.crf;
    let mut speed_preset = opts.speed_preset.clone();
    let mut audio_bitrate = opts.audio_bitrate.clone();
    let mut extra_args = opts.extra_args.clone();

    if let Some(name) = &opts.preset_name {
        if let Some(preset) = quality_preset(name) {
            encoder = encoder.or_else(|| Some(preset.encoder.to_string()));
            if let Some(cq) = preset.cq {
                crf = Some(cq);
            } else {
                crf = crf.or(preset.crf);
            }
            speed_preset = speed_preset.or_else(|| Some(preset.speed_preset.to_string()));
            audio_bitrate = if audio_bitrate.is_empty() {
                preset.audio_bitrate.to_string()
            } else {
                audio_bitrate
            };
            if let Some(pe) = preset.extra_args {
                extra_args = Some(match extra_args.take() {
                    Some(u) => format!("{pe} {u}"),
                    None => pe.to_string(),
                });
            }
        }
    }

    // 视频滤镜链: 字幕烧录 + 缩放
    let mut vf: Vec<String> = Vec::new();
    if let Some(sub) = &opts.subtitle_path {
        vf.push(format!("subtitles='{}'", escape_path_for_ffmpeg(sub)));
    }
    if let Some(res) = &opts.resolution {
        if res.contains('x') {
            let parts: Vec<&str> = res.split('x').collect();
            if parts.len() == 2 {
                vf.push(format!("scale={}:{}", parts[0], parts[1]));
            }
        }
    }
    if !vf.is_empty() {
        cmd.push("-vf".into());
        cmd.push(vf.join(","));
    }

    let actual_encoder = encoder.unwrap_or_else(|| "libx264".into());
    cmd.push("-c:v".into());
    cmd.push(actual_encoder.clone());

    if actual_encoder != "copy" {
        push_quality(&mut cmd, &actual_encoder, opts.rc_mode.as_deref(), crf,
                     opts.bitrate.as_deref());
        if let Some(sp) = &speed_preset {
            cmd.push("-preset".into());
            cmd.push(sp.clone());
        }
    }

    if let Some(fps) = opts.fps {
        if fps > 0 {
            cmd.push("-r".into());
            cmd.push(fps.to_string());
        }
    }

    if opts.audio_tracks != "none" && !cmd.iter().any(|a| a == "-an") {
        cmd.push("-c:a".into());
        cmd.push(opts.audio_encoder.clone());
        if opts.audio_encoder != "copy" {
            cmd.push("-b:a".into());
            cmd.push(audio_bitrate.clone());
        }
    }

    if opts.subtitle_tracks != "none" && !cmd.iter().any(|a| a == "-sn") {
        cmd.push("-c:s".into());
        cmd.push("copy".into());
    }

    if let Some(extra) = &extra_args {
        cmd.extend(extra.split(' ').filter(|s| !s.is_empty()).map(str::to_string));
    }

    cmd.push(opts.output.clone());
    cmd
}

/// 构建封装转换命令 (core.build_remux_command)。
pub fn build_remux_command(input: &str, output: &str,
                           audio_tracks: &str, audio_custom: &str,
                           subtitle_tracks: &str, subtitle_custom: &str) -> Vec<String> {
    let mut cmd: Vec<String> = vec![
        "ffmpeg".into(), "-y".into(), "-i".into(), input.into(),
        "-map".into(), "0:v".into(),
    ];
    cmd.extend(stream_map_args("a", audio_tracks, audio_custom));
    cmd.extend(stream_map_args("s", subtitle_tracks, subtitle_custom));
    cmd.push("-c".into());
    cmd.push("copy".into());
    cmd.push(output.into());
    cmd
}

/// 构建替换音频命令 (core.build_replace_audio_command)。
pub fn build_replace_audio_command(video: &str, audio: &str, output: &str,
                                   audio_encoder: &str, audio_bitrate: &str) -> Vec<String> {
    let mut cmd: Vec<String> = vec![
        "ffmpeg".into(), "-y".into(),
        "-i".into(), video.into(),
        "-i".into(), audio.into(),
        "-map".into(), "0:v:0".into(),
        "-map".into(), "1:a:0".into(),
        "-c:v".into(), "copy".into(),
        "-c:a".into(), audio_encoder.into(),
    ];
    if audio_encoder != "copy" {
        cmd.push("-b:a".into());
        cmd.push(audio_bitrate.into());
    }
    cmd.push(output.into());
    cmd
}

#[cfg(test)]
mod tests {
    use super::*;

    fn opts() -> EncodeOptions {
        EncodeOptions::default()
    }

    #[test]
    fn stream_map_none() {
        assert_eq!(stream_map_args("a", "none", ""), vec!["-an"]);
        assert_eq!(stream_map_args("s", "none", ""), vec!["-sn"]);
    }

    #[test]
    fn stream_map_all() {
        assert_eq!(stream_map_args("a", "all", ""), vec!["-map", "0:a?"]);
    }

    #[test]
    fn stream_map_custom() {
        assert_eq!(
            stream_map_args("a", "custom", "0, 2, x"),
            vec!["-map", "0:a:0?", "-map", "0:a:2?"]
        );
        assert_eq!(stream_map_args("a", "custom", ""), vec!["-map", "0:a?"]);
    }

    #[test]
    fn stream_map_digit_and_fallback() {
        assert_eq!(stream_map_args("a", "1", ""), vec!["-map", "0:a:1?"]);
        assert_eq!(stream_map_args("a", "whatever", ""), vec!["-map", "0:a?"]);
    }

    #[test]
    fn escape_path() {
        assert_eq!(
            escape_path_for_ffmpeg("C:\\my subs\\a's.ass"),
            "C\\:/my subs/a'\\''s.ass"
        );
    }

    #[test]
    fn encode_basic() {
        let cmd = build_encode_command(&opts());
        assert_eq!(cmd.last().unwrap(), "output.mp4");
        assert!(cmd.contains(&"-c:v".to_string()) && cmd.contains(&"libx264".to_string()));
        assert!(!cmd.contains(&"-crf".to_string()));
    }

    #[test]
    fn encode_preset_full() {
        let mut o = opts();
        o.preset_name = Some("【均衡画质】x264 常用导出 (CRF18)".into());
        o.subtitle_path = Some("C:\\subs\\a.ass".into());
        o.resolution = Some("1280x720".into());
        o.fps = Some(30);
        let cmd = build_encode_command(&o);
        assert!(cmd.contains(&"-crf".to_string()) && cmd.contains(&"18".to_string()));
        let joined = cmd.join(" ");
        assert!(joined.contains("subtitles=") && joined.contains("1280"));
        assert!(cmd.contains(&"-r".to_string()) && cmd.contains(&"30".to_string()));
    }

    #[test]
    fn encode_preset_nvenc_extra_args() {
        let mut o = opts();
        o.preset_name = Some("【速度优先】NVIDIA 显卡加速".into());
        o.extra_args = Some("-tune film".into());
        let cmd = build_encode_command(&o);
        assert!(cmd.contains(&"h264_nvenc".to_string()));
        assert!(cmd.contains(&"-rc".to_string()) && cmd.contains(&"vbr".to_string()));
        assert!(cmd.contains(&"-tune".to_string()));
    }

    #[test]
    fn encode_rc_matrix() {
        let mut o = opts();
        o.bitrate = Some("8M".into());
        o.rc_mode = Some("2pass".into());
        assert!(build_encode_command(&o).contains(&"-maxrate".to_string()));

        let mut o = opts();
        o.encoder = Some("h264_nvenc".into());
        o.bitrate = Some("8M".into());
        o.rc_mode = Some("2pass".into());
        assert!(build_encode_command(&o).contains(&"vbr_hq".to_string()));

        let mut o = opts();
        o.encoder = Some("h264_amf".into());
        o.bitrate = Some("8M".into());
        o.rc_mode = Some("2pass".into());
        assert!(build_encode_command(&o).contains(&"vbr_peak".to_string()));

        let mut o = opts();
        o.encoder = Some("h264_nvenc".into());
        o.crf = Some(20);
        o.rc_mode = Some("2pass".into());
        assert!(build_encode_command(&o).contains(&"-cq".to_string()));

        let mut o = opts();
        o.encoder = Some("h264_qsv".into());
        o.crf = Some(20);
        o.rc_mode = Some("2pass".into());
        assert!(build_encode_command(&o).contains(&"-global_quality".to_string()));

        let mut o = opts();
        o.encoder = Some("h264_nvenc".into());
        o.bitrate = Some("8M".into());
        o.rc_mode = Some("vbr".into());
        assert!(build_encode_command(&o).contains(&"-rc".to_string()));

        let mut o = opts();
        o.encoder = Some("h264_amf".into());
        o.bitrate = Some("8M".into());
        o.rc_mode = Some("vbr".into());
        assert!(build_encode_command(&o).contains(&"vbr_peak".to_string()));

        let mut o = opts();
        o.encoder = Some("h264_nvenc".into());
        o.bitrate = Some("8M".into());
        o.rc_mode = Some("cbr".into());
        assert!(build_encode_command(&o).contains(&"-minrate".to_string()));

        let mut o = opts();
        o.encoder = Some("h264_amf".into());
        o.crf = Some(20);
        let cmd = build_encode_command(&o);
        assert!(cmd.contains(&"-qp_i".to_string()));
    }

    #[test]
    fn encode_full_matrix_smoke() {
        for rc in [None, Some("2pass"), Some("vbr"), Some("cbr")] {
            for enc in ["libx264", "h264_nvenc", "h264_qsv", "h264_amf"] {
                for q in [Some(20u32), None] {
                    let bitrate = q.map(|_| "8M".to_string());
                    let mut o = opts();
                    o.encoder = Some(enc.into());
                    o.rc_mode = rc.map(str::to_string);
                    o.crf = q;
                    o.bitrate = bitrate;
                    let cmd = build_encode_command(&o);
                    assert_eq!(cmd.last().unwrap(), "output.mp4");
                }
            }
        }
    }

    #[test]
    fn encode_audio_subtitle_switches() {
        let mut o = opts();
        o.audio_tracks = "none".into();
        o.subtitle_tracks = "none".into();
        let cmd = build_encode_command(&o);
        assert!(cmd.contains(&"-an".to_string()) && cmd.contains(&"-sn".to_string()));
        assert!(!cmd.contains(&"-c:a".to_string()));

        let mut o = opts();
        o.audio_tracks = "all".into();
        o.subtitle_tracks = "all".into();
        o.audio_encoder = "copy".into();
        let cmd = build_encode_command(&o);
        assert!(cmd.contains(&"-c:s".to_string()));
        assert!(!cmd.contains(&"-b:a".to_string()));
    }

    #[test]
    fn replace_audio_command() {
        let cmd = build_replace_audio_command("v.mp4", "a.m4a", "o.mp4", "aac", "192k");
        let joined = cmd.join(" ");
        assert!(joined.contains("1:a:0") && joined.contains("copy"));
        let cmd2 = build_replace_audio_command("v.mp4", "a.m4a", "o.mp4", "copy", "192k");
        assert!(!cmd2.contains(&"-b:a".to_string()));
    }

    #[test]
    fn remux_command() {
        let cmd = build_remux_command("i.mkv", "o.mp4", "none", "", "all", "");
        let joined = cmd.join(" ");
        assert!(joined.contains("-c copy") && joined.contains("-an"));
    }

    #[test]
    fn resolution_passthrough() {
        let mut o = opts();
        o.resolution = Some("axb".into());
        let cmd = build_encode_command(&o);
        assert!(cmd.join(" ").contains("scale=a:b"));
    }
}
