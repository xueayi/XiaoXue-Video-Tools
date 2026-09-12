//! 批量创建文件夹 (移植自 src/folder_creator.py)。
//!
//! 编码策略: UTF-8 (含 BOM) 优先, 失败回退 GBK 解码 (覆盖 gb2312);
//! 与 Python 版的 chardet 检测相比简化, 中文场景效果一致。

use std::collections::HashSet;
use std::path::Path;

/// Windows 文件名非法字符。
const ILLEGAL_CHARS: &[char] = &['\\', '/', ':', '*', '?', '"', '<', '>', '|'];

/// 清理文件夹名称: 非法字符换下划线、折叠连续下划线、去首尾,
/// 空名称返回 "untitled" (folder_creator.sanitize_folder_name)。
pub fn sanitize_folder_name(name: &str) -> String {
    let cleaned: String = name
        .trim()
        .chars()
        .map(|c| if ILLEGAL_CHARS.contains(&c) { '_' } else { c })
        .collect();
    let mut collapsed = String::new();
    let mut prev_underscore = false;
    for c in cleaned.chars() {
        if c == '_' {
            if !prev_underscore {
                collapsed.push('_');
            }
            prev_underscore = true;
        } else {
            collapsed.push(c);
            prev_underscore = false;
        }
    }
    let trimmed = collapsed.trim_matches('_');
    if trimmed.is_empty() {
        "untitled".into()
    } else {
        trimmed.to_string()
    }
}

/// 读取 TXT 中的文件夹名称 (去空行/去重/清理)。
///
/// UTF-8 (含 BOM) 优先, 失败回退 GBK。
pub fn read_folder_names(txt_path: &Path) -> Result<Vec<String>, String> {
    let bytes = std::fs::read(txt_path).map_err(|e| format!("读取 TXT 文件失败: {e}"))?;
    let text = decode_text(&bytes);
    let mut names: Vec<String> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    for line in text.lines() {
        let name = sanitize_folder_name(line);
        if !name.is_empty() && !seen.contains(&name) {
            seen.insert(name.clone());
            names.push(name);
        }
    }
    Ok(names)
}

fn decode_text(bytes: &[u8]) -> String {
    let stripped = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(bytes);
    match std::str::from_utf8(stripped) {
        Ok(s) => s.to_string(),
        Err(_) => {
            let (decoded, _, _) = encoding_rs::GBK.decode(bytes);
            decoded.into_owned()
        }
    }
}

/// 批量创建文件夹 (folder_creator.batch_create_folders)。
///
/// 返回 (成功数, 失败数, 错误消息列表)。
pub fn batch_create_folders(
    txt_path: &Path,
    output_dir: &Path,
    auto_number: bool,
) -> (u32, u32, Vec<String>) {
    let names = match read_folder_names(txt_path) {
        Ok(n) => n,
        Err(e) => return (0, 1, vec![e]),
    };
    if names.is_empty() {
        return (0, 0, Vec::new());
    }
    if let Err(e) = std::fs::create_dir_all(output_dir) {
        return (0, names.len() as u32, vec![format!("创建输出目录失败: {e}")]);
    }

    let mut success = 0u32;
    let mut fail = 0u32;
    let mut errors: Vec<String> = Vec::new();
    for (i, name) in names.iter().enumerate() {
        let folder_name = if auto_number {
            format!("{}_{}", i + 1, name)
        } else {
            name.clone()
        };
        match std::fs::create_dir(output_dir.join(&folder_name)) {
            Ok(_) => success += 1,
            Err(e) => {
                fail += 1;
                errors.push(format!("{folder_name}: {e}"));
            }
        }
    }
    (success, fail, errors)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitize_replaces_illegal() {
        assert_eq!(sanitize_folder_name("  a<b>c  "), "a_b_c");
        assert_eq!(sanitize_folder_name("正常名称"), "正常名称");
        assert_eq!(sanitize_folder_name("a//b"), "a_b");
    }

    #[test]
    fn sanitize_collapses_and_defaults() {
        assert_eq!(sanitize_folder_name("___"), "untitled");
        assert_eq!(sanitize_folder_name("_a__b_"), "a_b");
    }

    #[test]
    fn read_txt_utf8_and_dedupe() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("names.txt");
        std::fs::write(&f, "动漫\n\n动漫\n  音乐  \n").unwrap();
        let names = read_folder_names(&f).unwrap();
        assert_eq!(names, vec!["动漫", "untitled", "音乐"]);
    }

    #[test]
    fn read_txt_gbk_fallback() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("gbk.txt");
        let (encoded, _, _) = encoding_rs::GBK.encode("动漫音乐");
        std::fs::write(&f, encoded).unwrap();
        let names = read_folder_names(&f).unwrap();
        assert_eq!(names, vec!["动漫音乐"]);
    }

    #[test]
    fn read_txt_utf8_bom() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("bom.txt");
        let mut bytes = vec![0xEF, 0xBB, 0xBF];
        bytes.extend("动漫".as_bytes());
        std::fs::write(&f, bytes).unwrap();
        assert_eq!(read_folder_names(&f).unwrap(), vec!["动漫"]);
    }

    #[test]
    fn create_folders_numbered() {
        let dir = tempfile::tempdir().unwrap();
        let txt = dir.path().join("names.txt");
        std::fs::write(&txt, "动漫\n音乐\n").unwrap();
        let out = dir.path().join("out");
        let (ok, fail, errors) = batch_create_folders(&txt, &out, true);
        assert_eq!((ok, fail, errors.len()), (2, 0, 0));
        assert!(out.join("1_动漫").is_dir());
        assert!(out.join("2_音乐").is_dir());
    }

    #[test]
    fn create_folders_empty_txt() {
        let dir = tempfile::tempdir().unwrap();
        let txt = dir.path().join("names.txt");
        std::fs::write(&txt, "").unwrap();
        let (ok, fail, errors) = batch_create_folders(&txt, &dir.path(), true);
        assert_eq!((ok, fail, errors.len()), (0, 0, 0));
    }

    #[test]
    fn create_folders_missing_txt() {
        let dir = tempfile::tempdir().unwrap();
        let (ok, fail, errors) =
            batch_create_folders(&dir.path().join("nope.txt"), &dir.path(), true);
        assert_eq!((ok, fail), (0, 1));
        assert!(!errors.is_empty());
    }
}
