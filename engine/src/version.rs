//! 版本解析与比较 (移植自 src/updater.py)。
//!
//! `2.1.0` -> (2, 1, 0, 3, 0); 正式版 > rc > beta > alpha。

/// 解析版本号; 无法解析返回 [`None`]。
pub fn parse_version(version: &str) -> Option<(u32, u32, u32, u32, u32)> {
    let mut v = version.trim();
    if v.starts_with('v') || v.starts_with('V') {
        v = &v[1..];
    }
    let (core, pre) = match v.split_once('-') {
        Some((c, p)) => (c, Some(p)),
        None => (v, None),
    };
    let core: Vec<u32> = core
        .split('.')
        .map(|p| p.parse::<u32>().ok())
        .collect::<Option<Vec<_>>>()?;
    if core.len() != 3 {
        return None;
    }
    let (rank, num) = match pre {
        None => (3, 0),
        Some(p) => split_pre(p),
    };
    Some((core[0], core[1], core[2], rank, num))
}

/// 解析预发布标识: alpha=0 < beta=1 < rc=2, 后缀序号默认 0。
fn split_pre(p: &str) -> (u32, u32) {
    let lower = p.trim().to_ascii_lowercase();
    let (tag, rest) = if let Some(r) = lower.strip_prefix("alpha") {
        (0u32, r)
    } else if let Some(r) = lower.strip_prefix("beta") {
        (1u32, r)
    } else if let Some(r) = lower.strip_prefix("rc") {
        (2u32, r)
    } else {
        return (0, 0);
    };
    let seq = rest.trim_start_matches(['.', '-']).parse().unwrap_or(0);
    (tag, seq)
}

/// `remote` 是否严格新于 `local`; 任一无法解析返回 false。
pub fn is_newer(remote: &str, local: &str) -> bool {
    match (parse_version(remote), parse_version(local)) {
        (Some(r), Some(l)) => r > l,
        _ => false,
    }
}

/// 开发版本 (git 描述失败回退的 *-dev) 不参与静默更新提示。
pub fn is_dev_version(version: &str) -> bool {
    version.to_ascii_lowercase().contains("dev")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_plain() {
        assert_eq!(parse_version("2.1.0"), Some((2, 1, 0, 3, 0)));
        assert_eq!(parse_version(" v2.1.0 "), Some((2, 1, 0, 3, 0)));
    }

    #[test]
    fn parse_prerelease() {
        assert_eq!(parse_version("2.1.0-beta"), Some((2, 1, 0, 1, 0)));
        assert_eq!(parse_version("2.1.0-beta.2"), Some((2, 1, 0, 1, 2)));
        assert_eq!(parse_version("2.1.0-rc.1"), Some((2, 1, 0, 2, 1)));
        assert_eq!(parse_version("2.1.0-alpha.3"), Some((2, 1, 0, 0, 3)));
    }

    #[test]
    fn parse_invalid() {
        assert_eq!(parse_version("垃圾输入"), None);
        assert_eq!(parse_version(""), None);
        assert_eq!(parse_version("1.2"), None);
    }

    #[test]
    fn newer_matrix() {
        assert!(is_newer("2.2.0", "2.1.0"));
        assert!(!is_newer("2.1.0", "2.1.0"));
        assert!(!is_newer("2.1.0", "2.2.0"));
        assert!(is_newer("2.1.0", "2.1.0-beta"));
        assert!(is_newer("2.1.0-rc.1", "2.1.0-beta.9"));
        assert!(is_newer("10.0.0", "2.9.9"));
    }

    #[test]
    fn newer_unparseable_is_false() {
        assert!(!is_newer("garbage", "2.1.0"));
        assert!(!is_newer("2.1.0", "garbage"));
    }

    #[test]
    fn dev_detection() {
        assert!(is_dev_version("2.0.0-dev"));
        assert!(!is_dev_version("2.1.0"));
    }
}
