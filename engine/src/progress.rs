//! FFmpeg 输出进度解析 (移植自 src/ui/ffmpeg_progress.py)。
//!
//! 无正则: 按 `key=value` 令牌提取, 宽松容错 (N/A、坏数字一律忽略)。
//! 与 Python 版语义一致: 仅 `time=` 行触发派生值更新。

use serde::Serialize;

#[derive(Debug, Default, Clone, Serialize)]
pub struct ProgressInfo {
    pub frame: u64,
    pub fps: f64,
    pub size_kb: u64,
    pub time_sec: f64,
    pub bitrate_kbps: f64,
    pub speed: f64,
    pub total_duration: f64,
    pub percent: f64,
    pub eta_sec: f64,
}

/// 从行中提取 `key=值` (容忍 = 后的空格与尾随逗号)。
fn extract<'a>(line: &'a str, key: &str) -> Option<&'a str> {
    let pat = format!("{key}=");
    let start = line.find(&pat)? + pat.len();
    let rest = line[start..].trim_start();
    let end = rest.find(char::is_whitespace).unwrap_or(rest.len());
    let value = rest[..end].trim_end_matches(',');
    if value.is_empty() {
        None
    } else {
        Some(value)
    }
}

/// 解析 `HH:MM:SS.cc` 为秒; 非 timestamps 返回 None。
fn parse_hms(s: &str) -> Option<f64> {
    let parts: Vec<&str> = s.trim().split(':').collect();
    if parts.len() != 3 {
        return None;
    }
    let h: f64 = parts[0].trim().parse().ok()?;
    let m: f64 = parts[1].trim().parse().ok()?;
    let sec: f64 = parts[2].trim().parse().ok()?;
    Some(h * 3600.0 + m * 60.0 + sec)
}

#[derive(Debug, Default)]
pub struct ProgressParser {
    info: ProgressInfo,
}

impl ProgressParser {
    pub fn new() -> Self {
        Self::default()
    }

    /// 从视频元数据预知总时长, 用于百分比与 ETA 计算。
    pub fn set_duration(&mut self, seconds: f64) {
        self.info.total_duration = seconds;
    }

    /// 喂入一行输出; 仅当 `time=` 更新时返回快照 (与 Python 版一致)。
    pub fn feed_line(&mut self, line: &str) -> Option<ProgressInfo> {
        if line.is_empty() {
            return None;
        }

        // 尝试从头部行解析 Duration
        if self.info.total_duration <= 0.0 {
            if let Some(pos) = line.find("Duration:") {
                let rest = line[pos + "Duration:".len()..].trim_start();
                let end = rest
                    .find(|c: char| c == ',' || c.is_whitespace())
                    .unwrap_or(rest.len());
                if let Some(sec) = parse_hms(&rest[..end]) {
                    self.info.total_duration = sec;
                }
            }
        }

        let mut updated = false;
        if let Some(v) = extract(line, "time") {
            if let Some(sec) = parse_hms(v) {
                self.info.time_sec = sec;
                updated = true;
            }
        }
        if let Some(v) = extract(line, "frame") {
            if let Ok(n) = v.parse() {
                self.info.frame = n;
            }
        }
        if let Some(v) = extract(line, "fps") {
            if let Ok(f) = v.parse() {
                self.info.fps = f;
            }
        }
        if let Some(v) = extract(line, "size") {
            self.info.size_kb = parse_u64_suffix(v, "kB");
        }
        if let Some(v) = extract(line, "bitrate") {
            self.info.bitrate_kbps = parse_f64_suffix(v, "kbits/s");
        }
        if let Some(v) = extract(line, "speed") {
            self.info.speed = parse_f64_suffix(v, "x");
        }

        if updated {
            self.calc_derived();
            Some(self.info.clone())
        } else {
            None
        }
    }

    fn calc_derived(&mut self) {
        let info = &mut self.info;
        if info.total_duration > 0.0 {
            info.percent = (info.time_sec / info.total_duration * 100.0).min(100.0);
        } else {
            info.percent = 0.0;
        }
        if info.speed > 0.0 && info.total_duration > 0.0 {
            let remaining = info.total_duration - info.time_sec;
            info.eta_sec = (remaining / info.speed).max(0.0);
        } else {
            info.eta_sec = -1.0;
        }
    }
}

fn parse_u64_suffix(v: &str, suffix: &str) -> u64 {
    v.strip_suffix(suffix)
        .and_then(|t| t.trim().parse().ok())
        .unwrap_or(0)
}

fn parse_f64_suffix(v: &str, suffix: &str) -> f64 {
    v.strip_suffix(suffix)
        .and_then(|t| t.trim().parse().ok())
        .unwrap_or(0.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn duration_header_parsed() {
        let mut p = ProgressParser::new();
        p.feed_line("Input #0, mp4:\n");
        p.feed_line("  Duration: 00:01:40.00, start: 0.000000\n");
        assert_eq!(p.info.total_duration, 100.0);
    }

    #[test]
    fn progress_line_full() {
        let mut p = ProgressParser::new();
        p.set_duration(200.0);
        let got = p.feed_line(
            "frame=  100 fps= 50 q=28.0 size=    1024kB \
             time=00:01:00.00 bitrate= 140.0kbits/s speed=2.00x\n",
        );
        let info = got.expect("time= 应触发信号");
        assert_eq!(info.frame, 100);
        assert_eq!(info.fps, 50.0);
        assert_eq!(info.size_kb, 1024);
        assert_eq!(info.time_sec, 60.0);
        assert_eq!(info.bitrate_kbps, 140.0);
        assert_eq!(info.speed, 2.0);
        assert!((info.percent - 30.0).abs() < 0.1);
        assert!((info.eta_sec - 70.0).abs() < 0.5);
    }

    #[test]
    fn values_without_time_stay_silent() {
        let mut p = ProgressParser::new();
        assert!(p.feed_line("frame=5 fps=24.0 size=10kB bitrate=1.2.3kbits/s speed=1.2.3x\n").is_none());
        assert_eq!(p.info.frame, 5);
        assert_eq!(p.info.fps, 24.0);
        assert_eq!(p.info.size_kb, 10);
        assert_eq!(p.info.bitrate_kbps, 0.0); // 坏数字被吞
        assert_eq!(p.info.speed, 0.0);
    }

    #[test]
    fn garbage_and_empty() {
        let mut p = ProgressParser::new();
        assert!(p.feed_line("").is_none());
        assert!(p.feed_line("hello world\n").is_none());
    }

    #[test]
    fn duration_from_header_fractions() {
        let mut p = ProgressParser::new();
        p.feed_line("  Duration: 00:01:40.00, start: 0\n");
        p.feed_line("frame=1 time=00:00:50.00 speed=1.00x\n");
        assert!((p.info.percent - 50.0).abs() < 0.1);
        assert!((p.info.eta_sec - 50.0).abs() < 0.1);
    }
}
