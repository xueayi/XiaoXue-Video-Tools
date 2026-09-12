//! ffmpeg/ffprobe 可执行文件定位 (移植自 src/utils.py)。
//!
//! 查找顺序: exe 同级 bin/ -> 上级 bin/ -> ./bin/ -> 系统 PATH -> 原名回退。

use std::path::PathBuf;

fn exe_name(tool: &str) -> String {
    if cfg!(windows) {
        format!("{tool}.exe")
    } else {
        tool.to_string()
    }
}

/// 在 PATH 中查找可执行文件 (utils.shutil.which 的简化版)。
fn which(tool: &str) -> Option<String> {
    let target = exe_name(tool);
    let path_var = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path_var) {
        let candidate = dir.join(&target);
        if candidate.is_file() {
            return Some(candidate.to_string_lossy().into_owned());
        }
    }
    None
}

/// 定位 ffmpeg/ffprobe (utils.get_ffmpeg_path / get_ffprobe_path)。
pub fn find_tool(tool: &str) -> String {
    let name = exe_name(tool);

    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("bin").join(&name));
            if let Some(parent) = dir.parent() {
                candidates.push(parent.join("bin").join(&name));
            }
        }
    }
    candidates.push(PathBuf::from("bin").join(&name));
    for c in candidates {
        if c.is_file() {
            return c.to_string_lossy().into_owned();
        }
    }
    which(tool).unwrap_or_else(|| tool.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fallback_returns_bare_name() {
        // 不存在的工具名 -> 原样返回, 由调用方命令执行时报错
        assert_eq!(
            find_tool("definitely-not-a-real-tool-xyz"),
            "definitely-not-a-real-tool-xyz"
        );
    }
}
