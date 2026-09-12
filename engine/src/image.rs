//! 图片格式转换 (移植自 src/image_converter.py)。
//!
//! 基于 image crate; JPEG/BMP 不支持 alpha 时自动白底合成。

use std::path::Path;

use image::DynamicImage;

pub const PIL_FORMAT_MAP: &[(&str, &str)] = &[
    (".png", "png"),
    (".jpg", "jpeg"),
    (".jpeg", "jpeg"),
    (".webp", "webp"),
    (".bmp", "bmp"),
    (".gif", "gif"),
    (".tiff", "tiff"),
    (".tif", "tiff"),
    (".ico", "ico"),
];

/// 无 alpha 通道的目标格式 (需白底合成)。
const FORMATS_NO_ALPHA: &[&str] = &[".jpg", ".jpeg", ".bmp"];

pub fn format_for_extension(ext: &str) -> Option<image::ImageFormat> {
    let ext = ext.to_ascii_lowercase();
    match PIL_FORMAT_MAP.iter().find(|(e, _)| *e == ext).map(|(_, f)| *f) {
        Some("jpeg") => Some(image::ImageFormat::Jpeg),
        Some("png") => Some(image::ImageFormat::Png),
        Some("webp") => Some(image::ImageFormat::WebP),
        Some("bmp") => Some(image::ImageFormat::Bmp),
        Some("gif") => Some(image::ImageFormat::Gif),
        Some("tiff") => Some(image::ImageFormat::Tiff),
        _ => None,
    }
}

/// 归一化扩展名: .jpeg -> .jpg, .tif -> .tiff
/// (image_converter._normalize_extension)。
pub fn normalize_extension(ext: &str) -> String {
    let lower = ext.to_ascii_lowercase();
    match lower.as_str() {
        ".jpeg" => ".jpg".into(),
        ".tif" => ".tiff".into(),
        _ => lower,
    }
}

pub struct ConvertOutcome {
    pub ok: bool,
    pub message: String,
}

/// 转换单张图片 (image_converter.convert_image)。
pub fn convert_image(
    input_path: &Path,
    output_path: &Path,
    quality: u8,
) -> ConvertOutcome {
    let img = match image::open(input_path) {
        Ok(img) => img,
        Err(e) => {
            return ConvertOutcome {
                ok: false,
                message: format!("转换失败: {e}"),
            }
        }
    };

    let output_ext = output_path
        .extension()
        .map(|e| format!(".{}", e.to_string_lossy().to_ascii_lowercase()))
        .unwrap_or_default();
    // 只支持已注册的格式 (与 Python PIL_FORMAT_MAP 一致)
    if format_for_extension(&output_ext).is_none() {
        return ConvertOutcome {
            ok: false,
            message: format!("不支持的目标格式: {output_ext}"),
        };
    }

    // alpha 通道处理: JPEG/BMP 需要不透明底
    let img: DynamicImage = if FORMATS_NO_ALPHA.contains(&output_ext.as_str())
        && matches!(img, DynamicImage::ImageRgba8(_))
    {
        let rgba = img.to_rgba8();
        let (w, h) = (rgba.width(), rgba.height());
        let mut background = image::ImageBuffer::from_fn(w, h, |_, _| {
            image::Rgba([255u8, 255, 255, 255])
        });
        for (x, y, px) in rgba.enumerate_pixels() {
            let a = px[3] as u32;
            let blended = {
                let base = background.get_pixel(x, y);
                image::Rgba([
                    ((px[0] as u32 * a + base[0] as u32 * (255 - a)) / 255) as u8,
                    ((px[1] as u32 * a + base[1] as u32 * (255 - a)) / 255) as u8,
                    ((px[2] as u32 * a + base[2] as u32 * (255 - a)) / 255) as u8,
                    255,
                ])
            };
            background.put_pixel(x, y, blended);
        }
        DynamicImage::ImageRgba8(background)
    } else {
        img
    };

    if let Some(parent) = output_path.parent() {
        if !parent.as_os_str().is_empty() {
            let _ = std::fs::create_dir_all(parent);
        }
    }

    let saved: Result<(), String> = match output_ext.as_str() {
        ".jpg" | ".jpeg" => {
            // JPEG 质量参数需要 JpegEncoder 直接写入
            match std::fs::File::create(output_path) {
                Ok(mut out) => {
                    let encoder = image::codecs::jpeg::JpegEncoder::new_with_quality(
                        &mut out, quality);
                    match img.write_with_encoder(encoder) {
                        Ok(_) => Ok(()),
                        Err(e) => Err(e.to_string()),
                    }
                }
                Err(e) => Err(e.to_string()),
            }
        }
        ".png" => img.save_with_format(output_path, image::ImageFormat::Png)
            .map_err(|e| e.to_string()),
        ".webp" => img.save_with_format(output_path, image::ImageFormat::WebP)
            .map_err(|e| e.to_string()),
        ".bmp" => img.save_with_format(output_path, image::ImageFormat::Bmp)
            .map_err(|e| e.to_string()),
        ".gif" => img.save_with_format(output_path, image::ImageFormat::Gif)
            .map_err(|e| e.to_string()),
        ".tiff" | ".tif" => img.save_with_format(output_path, image::ImageFormat::Tiff)
            .map_err(|e| e.to_string()),
        _ => img.save_with_format(output_path, image::ImageFormat::Png)
            .map_err(|e| e.to_string()),
    };

    match saved {
        Ok(_) => ConvertOutcome {
            ok: true,
            message: format!(
                "成功转换: {}",
                output_path
                    .file_name()
                    .map(|n| n.to_string_lossy().into_owned())
                    .unwrap_or_default()
            ),
        },
        Err(e) => ConvertOutcome {
            ok: false,
            message: format!("转换失败: {e}"),
        },
    }
}

/// 批量转换结果 (image_converter.batch_convert_images)。
pub struct BatchResult {
    pub success: u32,
    pub fail: u32,
    pub skipped: u32,
    pub errors: Vec<String>,
}

/// 批量转换 (image_converter.batch_convert_images)。
pub fn batch_convert(
    input_paths: &[String],
    output_dir: Option<&Path>,
    target_extension: &str,
    quality: u8,
    skip_same_format: bool,
) -> BatchResult {
    let mut target_extension = target_extension.to_ascii_lowercase();
    if !target_extension.starts_with('.') {
        target_extension = format!(".{target_extension}");
    }
    if format_for_extension(&target_extension).is_none() {
        return BatchResult {
            success: 0,
            fail: input_paths.len() as u32,
            skipped: 0,
            errors: vec![format!("不支持的目标格式: {target_extension}")],
        };
    }
    let target_norm = normalize_extension(&target_extension);

    let mut result = BatchResult {
        success: 0,
        fail: 0,
        skipped: 0,
        errors: Vec::new(),
    };

    for input in input_paths {
        let input_ext = std::path::Path::new(input)
            .extension()
            .map(|e| format!(".{}", e.to_string_lossy().to_ascii_lowercase()))
            .unwrap_or_default();
        if skip_same_format && normalize_extension(&input_ext) == target_norm {
            result.skipped += 1;
            continue;
        }
        let basename = std::path::Path::new(input)
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_else(|| "image".into());
        let output_path = match output_dir {
            Some(dir) => std::path::Path::new(dir).join(format!("{basename}{target_extension}")),
            None => std::path::Path::new(input)
                .with_file_name(format!("{basename}{target_extension}")),
        };
        // 避免覆盖原文件
        if paths_equal(&output_path, std::path::Path::new(input)) {
            let parent = output_path.parent().unwrap_or(Path::new("."));
            result
                .errors
                .push(format!("{basename}: 输出与输入相同, 已跳过"));
            result.fail += 1;
            let _ = parent;
            continue;
        }
        let outcome = convert_image(
            std::path::Path::new(input),
            &output_path,
            quality,
        );
        if outcome.ok {
            result.success += 1;
        } else {
            result.fail += 1;
            result
                .errors
                .push(format!("{basename}: {}", outcome.message));
        }
    }
    result
}

fn paths_equal(a: &Path, b: &Path) -> bool {
    a.to_string_lossy().to_lowercase() == b.to_string_lossy().to_lowercase()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn png(tmp: &Path, name: &str) -> String {
        let p = tmp.join(name);
        image::DynamicImage::new_rgb8(4, 4).save(&p).unwrap();
        p.to_string_lossy().into_owned()
    }

    #[test]
    fn convert_png_to_jpg() {
        let dir = tempfile::tempdir().unwrap();
        let src = png(dir.path(), "a.png");
        let out = dir.path().join("a.jpg");
        let r = convert_image(Path::new(&src), &out, 95);
        assert!(r.ok, "{}", r.message);
        assert!(out.exists());
    }

    #[test]
    fn convert_rgba_to_jpg_flattens() {
        let dir = tempfile::tempdir().unwrap();
        let src = dir.path().join("t.png");
        image::DynamicImage::new_rgba8(4, 4).save(&src).unwrap();
        let r = convert_image(&src, &dir.path().join("t.jpg"), 95);
        assert!(r.ok);
    }

    #[test]
    fn convert_failure_reported() {
        let dir = tempfile::tempdir().unwrap();
        let r = convert_image(&dir.path().join("nope.png"), &dir.path().join("x.jpg"), 95);
        assert!(!r.ok);
    }

    #[test]
    fn normalize_cases() {
        assert_eq!(normalize_extension(".JPEG"), ".jpg");
        assert_eq!(normalize_extension(".tif"), ".tiff");
        assert_eq!(normalize_extension(".png"), ".png");
    }

    #[test]
    fn batch_with_skip_and_errors() {
        let dir = tempfile::tempdir().unwrap();
        let a = png(dir.path(), "a.png");
        let out = dir.path().join("out");
        let r = batch_convert(&[a.clone(), "Z:/ghost.png".into()],
                              Some(out.as_path()), ".jpg", 95, true);
        assert_eq!((r.success, r.fail, r.skipped), (1, 1, 0));
    }

    #[test]
    fn batch_unsupported_format() {
        let r = batch_convert(&["x.png".into()], None, ".xyz", 95, true);
        assert_eq!(r.fail, 1);
        assert!(r.errors[0].contains("不支持"));
    }

    #[test]
    fn batch_output_none_writes_beside_source() {
        let dir = tempfile::tempdir().unwrap();
        let a = png(dir.path(), "b.png");
        let r = batch_convert(&[a.clone()], None, ".bmp", 95, true);
        assert_eq!(r.success, 1);
        assert!(dir.path().join("b.bmp").exists());
    }

    #[test]
    fn batch_same_target_skips() {
        let tmp = tempfile::tempdir().unwrap();
        let a = png(tmp.path(), "c.png");
        let r = batch_convert(&[a], None, ".png", 95, true);
        assert_eq!(r.skipped, 1);
    }
}
