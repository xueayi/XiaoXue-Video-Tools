//! 批量序列重命名 (移植自 src/batch_renamer.py)。

use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// 重命名模式 (RenameConfig.mode)。
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RenameMode {
    /// 原地重命名
    InPlace,
    /// 复制后重命名 (源文件保留)
    CopyRename,
    /// 移动后重命名 (源文件删除)
    MoveRename,
}

/// 目标类型。
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TargetType {
    Images,
    Videos,
    Both,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SortMethod {
    Name,
    Size,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SortOrder {
    Asc,
    Desc,
}

/// 重命名配置 (batch_renamer.RenameConfig)。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(default)]
pub struct RenameConfig {
    pub mode: RenameMode,
    pub output_dir: Option<PathBuf>,
    pub target_type: TargetType,
    pub image_extensions: Vec<String>,
    pub video_extensions: Vec<String>,
    pub recursive: bool,
    pub exclude_underscore: bool,
    pub sort_method: SortMethod,
    pub sort_order: SortOrder,
    pub priority_keyword: String,
}

impl Default for RenameConfig {
    fn default() -> Self {
        Self {
            mode: RenameMode::InPlace,
            output_dir: None,
            target_type: TargetType::Both,
            image_extensions: vec!["png".into(), "jpg".into()],
            video_extensions: vec!["mp4".into(), "mov".into()],
            recursive: true,
            exclude_underscore: true,
            sort_method: SortMethod::Name,
            sort_order: SortOrder::Asc,
            priority_keyword: String::new(),
        }
    }
}

/// 标准化扩展名列表: 小写、去点号、去空白 (batch_renamer.normalize_extensions)。
pub fn normalize_extensions(extensions: &[String]) -> Vec<String> {
    let mut out = Vec::new();
    for ext in extensions {
        let e = ext.trim().to_ascii_lowercase();
        let e = e.strip_prefix('.').unwrap_or(&e).to_string();
        if !e.is_empty() {
            out.push(e);
        }
    }
    out
}

fn file_size(path: &Path) -> u64 {
    std::fs::metadata(path).map(|m| m.len()).unwrap_or(0)
}

fn collect_files(directory: &Path, extensions: &[String], recursive: bool) -> Vec<PathBuf> {
    let exts: std::collections::HashSet<String> =
        normalize_extensions(extensions).into_iter().collect();
    let mut files: Vec<PathBuf> = Vec::new();
    if recursive {
        walk(directory, &mut |p| {
            if let Some(ext) = p.extension().and_then(|e| e.to_str()) {
                if exts.contains(&ext.to_ascii_lowercase()) {
                    files.push(p.to_path_buf());
                }
            }
        });
    } else if let Ok(entries) = std::fs::read_dir(directory) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.is_file() {
                if let Some(ext) = p.extension().and_then(|e| e.to_str()) {
                    if exts.contains(&ext.to_ascii_lowercase()) {
                        files.push(p);
                    }
                }
            }
        }
    }
    files
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

/// 获取排序后的文件列表 (batch_renamer.get_sorted_files)。
pub fn get_sorted_files(
    directory: &Path,
    extensions: &[String],
    recursive: bool,
    sort_method: SortMethod,
    sort_order: SortOrder,
    priority_keyword: &str,
) -> Vec<PathBuf> {
    let mut files = collect_files(directory, extensions, recursive);
    let reverse = sort_order == SortOrder::Desc;
    match sort_method {
        SortMethod::Size => {
            files.sort_by_key(|f| file_size(f));
        }
        SortMethod::Name => {
            files.sort_by_key(|f| {
                f.file_name()
                    .map(|n| n.to_string_lossy().to_ascii_lowercase())
                    .unwrap_or_default()
            });
        }
    }
    if reverse {
        files.reverse();
    }
    if !priority_keyword.trim().is_empty() {
        let keyword = priority_keyword.trim();
        let (mut priority, mut normal): (Vec<PathBuf>, Vec<PathBuf>) =
            files.into_iter().partition(|f| {
                f.file_name()
                    .map(|n| n.to_string_lossy().contains(keyword))
                    .unwrap_or(false)
            });
        priority.append(&mut normal);
        files = priority;
    }
    files
}

/// 处理父文件夹名称生成前缀 (batch_renamer.process_parent_folder_name)。
pub fn process_parent_folder_name(
    file_path: &Path,
    base_dir: &Path,
    exclude_underscore: bool,
) -> String {
    let rel = file_path.strip_prefix(base_dir).unwrap_or(file_path);
    let dir = match rel.parent() {
        Some(d) if d.as_os_str().is_empty() || d == Path::new(".") => return String::new(),
        Some(d) => d,
        None => return String::new(),
    };
    let mut parts: Vec<String> = Vec::new();
    for part in dir.components() {
        let mut part = part.as_os_str().to_string_lossy().into_owned();
        if exclude_underscore {
            if let Some(pos) = part.find('_') {
                part.truncate(pos);
            }
        }
        let cleaned: String = part
            .chars()
            .map(|c| {
                if ['\\', '/', ':', '*', '?', '"', '<', '>', '|'].contains(&c) {
                    '_'
                } else {
                    c
                }
            })
            .collect();
        let cleaned = cleaned.trim_matches('_').to_string();
        if !cleaned.is_empty() {
            parts.push(cleaned);
        }
    }
    if parts.is_empty() {
        String::new()
    } else {
        format!("{}_", parts.join("_"))
    }
}

/// 判断媒体类型: Some("图片") / Some("视频") / None
/// (batch_renamer.determine_media_type)。
pub fn determine_media_type(file_path: &Path, config: &RenameConfig) -> Option<&'static str> {
    let ext = file_path
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| e.to_ascii_lowercase())
        .unwrap_or_default();
    let images = normalize_extensions(&config.image_extensions);
    let videos = normalize_extensions(&config.video_extensions);
    match config.target_type {
        TargetType::Images | TargetType::Both
            if images.contains(&ext) => Some("图片"),
        TargetType::Videos | TargetType::Both
            if videos.contains(&ext) => Some("视频"),
        _ => None,
    }
}

/// 批量重命名 (batch_renamer.batch_rename)。
///
/// 返回 (成功数, 失败数, 错误消息列表)。
pub fn batch_rename(input_path: &Path, config: &RenameConfig) -> (u32, u32, Vec<String>) {
    if !input_path.is_dir() {
        return (0, 1, vec![format!("输入路径不是有效目录: {}", input_path.display())]);
    }

    let mut all_extensions: Vec<String> = Vec::new();
    if matches!(config.target_type, TargetType::Images | TargetType::Both) {
        all_extensions.extend(config.image_extensions.clone());
    }
    if matches!(config.target_type, TargetType::Videos | TargetType::Both) {
        all_extensions.extend(config.video_extensions.clone());
    }

    let files = get_sorted_files(
        input_path,
        &all_extensions,
        config.recursive,
        config.sort_method,
        config.sort_order,
        &config.priority_keyword,
    );
    if files.is_empty() {
        return (0, 0, Vec::new());
    }

    let output_base: PathBuf = match config.mode {
        RenameMode::InPlace => input_path.to_path_buf(),
        _ => {
            let base = config
                .output_dir
                .clone()
                .unwrap_or_else(|| input_path.join("rename_output"));
            let _ = std::fs::create_dir_all(&base);
            base
        }
    };

    // 按 (相对目录, 媒体类型) 分组, 保持插入顺序
    let mut group_order: Vec<(String, &'static str)> = Vec::new();
    let mut grouped: HashMap<(String, &'static str), Vec<PathBuf>> = HashMap::new();
    for file in &files {
        let media_type = match determine_media_type(file, config) {
            Some(t) => t,
            None => continue,
        };
        let rel_dir = if config.recursive {
            file.strip_prefix(input_path)
                .ok()
                .and_then(|p| p.parent())
                .map(|d| d.to_string_lossy().into_owned())
                .unwrap_or_default()
        } else {
            String::new()
        };
        let key = (rel_dir, media_type);
        if !grouped.contains_key(&key) {
            group_order.push(key.clone());
        }
        grouped.entry(key).or_default().push(file.clone());
    }

    let mut success = 0u32;
    let mut fail = 0u32;
    let mut errors: Vec<String> = Vec::new();

    for (rel_dir, media_type) in &group_order {
        let list = &grouped[&(rel_dir.clone(), *media_type)];
        for (idx, file_path) in list.iter().enumerate() {
            let ext = file_path
                .extension()
                .map(|e| format!(".{}", e.to_string_lossy()))
                .unwrap_or_default();
            let new_name = if config.recursive && !rel_dir.is_empty() {
                let prefix = process_parent_folder_name(
                    file_path,
                    input_path,
                    config.exclude_underscore,
                );
                format!("{prefix}{media_type}_{}{ext}", idx + 1)
            } else {
                format!("{media_type}_{}{ext}", idx + 1)
            };

            let mut new_path = if config.mode == RenameMode::InPlace {
                file_path.parent().unwrap().join(&new_name)
            } else if !rel_dir.is_empty() {
                let target_dir = output_base.join(rel_dir);
                let _ = std::fs::create_dir_all(&target_dir);
                target_dir.join(&new_name)
            } else {
                output_base.join(&new_name)
            };

            // 避免覆盖
            let mut counter = 1;
            while new_path.exists()
                && !paths_equal(file_path, &new_path)
            {
                let stem = new_path
                    .file_stem()
                    .map(|s| s.to_string_lossy().into_owned())
                    .unwrap_or_default();
                new_path = new_path
                    .parent()
                    .unwrap()
                    .join(format!("{stem}_{counter}{ext}"));
                counter += 1;
            }

            let result = match config.mode {
                RenameMode::InPlace => std::fs::rename(file_path, &new_path),
                RenameMode::CopyRename => std::fs::copy(file_path, &new_path).map(|_| ()),
                RenameMode::MoveRename => std::fs::rename(file_path, &new_path),
            };
            match result {
                Ok(_) => success += 1,
                Err(e) => {
                    fail += 1;
                    let name = file_path
                        .file_name()
                        .map(|n| n.to_string_lossy().into_owned())
                        .unwrap_or_default();
                    errors.push(format!("{name}: {e}"));
                }
            }
        }
    }
    (success, fail, errors)
}

fn paths_equal(a: &Path, b: &Path) -> bool {
    // 大小写不敏感的简易比较 (Windows 语义)
    a.to_string_lossy().to_lowercase() == b.to_string_lossy().to_lowercase()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_tree(dir: &Path) {
        std::fs::create_dir_all(dir.join("sub")).unwrap();
        std::fs::write(dir.join("sub/img_01.png"), b"1").unwrap();
        std::fs::write(dir.join("sub/img_02.png"), b"22").unwrap();
        std::fs::write(dir.join("vid.mp4"), b"v".repeat(10)).unwrap();
        std::fs::write(dir.join("note.txt"), b"x").unwrap();
    }

    #[test]
    fn normalize() {
        assert_eq!(
            normalize_extensions(&[".PNG".into(), " Jpg ".into(), "".into(), ".".into()]),
            vec!["png", "jpg"]
        );
    }

    #[test]
    fn size_of_missing_is_zero() {
        assert_eq!(file_size(Path::new("Z:/nope")), 0);
    }

    #[test]
    fn collect_recursive_and_not() {
        let dir = tempfile::tempdir().unwrap();
        make_tree(dir.path());
        let files = collect_files(dir.path(), &["png".into(), "mp4".into()], true);
        assert_eq!(files.len(), 3);
        let files = collect_files(dir.path(), &["png".into(), "mp4".into()], false);
        assert_eq!(files.len(), 1);
    }

    #[test]
    fn sorted_by_size_with_priority() {
        let dir = tempfile::tempdir().unwrap();
        make_tree(dir.path());
        let files = get_sorted_files(
            dir.path(),
            &["png".into(), "mp4".into()],
            true,
            SortMethod::Size,
            SortOrder::Desc,
            "vid",
        );
        assert!(files[0].ends_with("vid.mp4"));
        let files = get_sorted_files(
            dir.path(),
            &["png".into(), "mp4".into()],
            true,
            SortMethod::Size,
            SortOrder::Asc,
            "",
        );
        assert!(files[0].ends_with("img_01.png"));
    }

    #[test]
    fn parent_folder_prefix() {
        let dir = tempfile::tempdir().unwrap();
        let sub = dir.path().join("Series_01");
        std::fs::create_dir_all(&sub).unwrap();
        let f = sub.join("img.png");
        std::fs::write(&f, b"x").unwrap();
        assert_eq!(
            process_parent_folder_name(&f, dir.path(), true),
            "Series_"
        );
        assert_eq!(
            process_parent_folder_name(&f, dir.path(), false),
            "Series_01_"
        );
        assert_eq!(
            process_parent_folder_name(&dir.path().join("top.png"), dir.path(), true),
            ""
        );
    }

    #[test]
    fn media_type_detection() {
        let cfg = RenameConfig::default();
        assert_eq!(determine_media_type(Path::new("a.png"), &cfg), Some("图片"));
        assert_eq!(determine_media_type(Path::new("a.mp4"), &cfg), Some("视频"));
        assert_eq!(determine_media_type(Path::new("a.gif"), &cfg), None);
    }

    #[test]
    fn rename_in_place() {
        let dir = tempfile::tempdir().unwrap();
        make_tree(dir.path());
        let cfg = RenameConfig::default();
        let (ok, fail, errors) = batch_rename(dir.path(), &cfg);
        assert_eq!((ok, fail, errors.len()), (3, 0, 0));
        let names: Vec<String> = walk_names(dir.path());
        assert!(names.iter().any(|n| n.starts_with("视频_")));
        assert!(names.iter().any(|n| n.contains("图片_1")));
    }

    #[test]
    fn rename_copy_and_move() {
        let dir = tempfile::tempdir().unwrap();
        make_tree(dir.path());
        let out = dir.path().join("out");
        let cfg = RenameConfig {
            mode: RenameMode::CopyRename,
            output_dir: Some(out.clone()),
            ..Default::default()
        };
        let (ok, fail, _) = batch_rename(dir.path(), &cfg);
        assert_eq!((ok, fail), (3, 0));
        assert!(walk_names(&out).iter().any(|n| n.starts_with("视频_")));
        assert!(std::fs::read_dir(dir.path())
            .unwrap()
            .filter_map(Result::ok)
            .any(|e| e.path().extension().map(|x| x == "mp4").unwrap_or(false)));

        // move 模式: 源文件消失
        let src2 = dir.path().join("src2");
        std::fs::create_dir_all(src2.join("sub")).unwrap();
        std::fs::write(src2.join("sub/img_01.png"), b"1").unwrap();
        std::fs::write(src2.join("vid.mp4"), b"v").unwrap();
        let cfg2 = RenameConfig {
            mode: RenameMode::MoveRename,
            ..Default::default()
        };
        let (ok2, _, _) = batch_rename(&src2, &cfg2);
        assert_eq!(ok2, 2);
        assert!(!walk_names(&src2).iter().any(|n| n == "img_01.png"));
    }

    #[test]
    fn rename_invalid_dir() {
        let dir = tempfile::tempdir().unwrap();
        let cfg = RenameConfig::default();
        let (ok, fail, _) = batch_rename(&dir.path().join("nope"), &cfg);
        assert_eq!((ok, fail), (0, 1));
    }

    #[test]
    fn rename_no_files() {
        let dir = tempfile::tempdir().unwrap();
        let empty = dir.path().join("empty");
        std::fs::create_dir(&empty).unwrap();
        let (ok, fail, _) = batch_rename(&empty, &RenameConfig::default());
        assert_eq!((ok, fail), (0, 0));
    }

    #[test]
    fn copy_collision_gets_counter() {
        let dir = tempfile::tempdir().unwrap();
        make_tree(dir.path());
        let out = dir.path().join("out");
        let cfg = RenameConfig {
            mode: RenameMode::CopyRename,
            output_dir: Some(out.clone()),
            ..Default::default()
        };
        batch_rename(dir.path(), &cfg);
        batch_rename(dir.path(), &cfg);
        // 第二轮碰撞目标自动追加 _1 后缀, 任何文件都没有被覆盖
        assert!(out.join("视频_1.mp4").exists());
        assert!(out.join("视频_1_1.mp4").exists());
    }

    #[test]
    #[cfg(windows)]
    fn rename_failure_counts() {
        use std::os::windows::fs::OpenOptionsExt;
        // Windows: 以无 SHARE_DELETE 句柄占用源文件, rename 必失败
        let dir = tempfile::tempdir().unwrap();
        let media = dir.path().join("media");
        std::fs::create_dir(&media).unwrap();
        std::fs::write(media.join("a.png"), b"x").unwrap();
        std::fs::write(media.join("b.png"), b"y").unwrap();
        let _lock = std::fs::OpenOptions::new()
            .read(true)
            .share_mode(1) // 仅 FILE_SHARE_READ: 占用文件使 rename 失败
            .open(media.join("a.png"))
            .unwrap();
        let (ok, fail, errors) = batch_rename(&media, &RenameConfig::default());
        assert_eq!(ok, 1); // b.png 正常改名
        assert_eq!(fail, 1); // a.png 被占用计入错误
        assert!(!errors.is_empty());
    }

    fn walk_names(dir: &Path) -> Vec<String> {
        let mut names = Vec::new();
        walk(dir, &mut |p| {
            names.push(p.file_name().unwrap().to_string_lossy().into_owned());
        });
        names
    }
}
