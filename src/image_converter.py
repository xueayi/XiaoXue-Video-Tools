# -*- coding: utf-8 -*-
"""
图片格式转换模块：支持批量图片格式互转。
"""
import os
from typing import List, Optional, Tuple
from colorama import Fore, Style

try:
    from PIL import Image
except ImportError:
    Image = None


# 支持的图片格式映射 (扩展名 -> PIL 格式名)
PIL_FORMAT_MAP = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".webp": "WEBP",
    ".bmp": "BMP",
    ".gif": "GIF",
    ".tiff": "TIFF",
    ".tif": "TIFF",
    ".ico": "ICO",
}

# 需要特殊处理的格式 (如 JPEG 不支持 alpha 通道)
FORMATS_NO_ALPHA = {".jpg", ".jpeg", ".bmp"}


def check_pillow_available() -> bool:
    """检查 Pillow 库是否可用。"""
    if Image is None:
        print(f"{Fore.RED}[错误] 未安装 Pillow 库，请运行: pip install Pillow{Style.RESET_ALL}")
        return False
    return True


def convert_image(
    input_path: str,
    output_path: str,
    target_format: Optional[str] = None,
    quality: int = 95,
) -> Tuple[bool, str]:
    """
    转换单张图片格式。

    Args:
        input_path: 输入图片路径
        output_path: 输出图片路径
        target_format: 目标格式 (如 "PNG", "JPEG")，如果为 None 则从输出路径推断
        quality: JPEG/WEBP 质量 (1-100)

    Returns:
        (成功标志, 消息)
    """
    if not check_pillow_available():
        return False, "Pillow 库不可用"

    try:
        # 打开图片
        img = Image.open(input_path)
        
        # 推断目标格式
        if target_format is None:
            ext = os.path.splitext(output_path)[1].lower()
            target_format = PIL_FORMAT_MAP.get(ext, "PNG")
        
        # 处理 alpha 通道
        output_ext = os.path.splitext(output_path)[1].lower()
        if output_ext in FORMATS_NO_ALPHA and img.mode in ("RGBA", "LA", "P"):
            # 创建白色背景并合成
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background
        elif img.mode == "P" and target_format != "GIF":
            # 调色板模式转换为 RGBA
            img = img.convert("RGBA")
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        
        # 保存参数
        save_kwargs = {}
        if target_format in ("JPEG", "WEBP"):
            save_kwargs["quality"] = quality
        if target_format == "PNG":
            save_kwargs["optimize"] = True
        
        # 保存图片
        img.save(output_path, format=target_format, **save_kwargs)
        img.close()
        
        return True, f"成功转换: {os.path.basename(output_path)}"
        
    except Exception as e:
        return False, f"转换失败: {str(e)}"


def batch_convert_images(
    input_paths: List[str],
    output_dir: Optional[str],
    target_extension: str,
    quality: int = 95,
) -> Tuple[int, int, List[str]]:
    """
    批量转换图片格式。

    Args:
        input_paths: 输入图片路径列表
        output_dir: 输出目录 (None 则在原文件位置生成)
        target_extension: 目标扩展名 (如 ".png", ".jpg")
        quality: JPEG/WEBP 质量

    Returns:
        (成功数, 失败数, 错误消息列表)
    """
    if not check_pillow_available():
        return 0, len(input_paths), ["Pillow 库不可用"]

    # 确保扩展名格式正确
    if not target_extension.startswith("."):
        target_extension = "." + target_extension
    target_extension = target_extension.lower()

    # 检查是否为支持的格式
    if target_extension not in PIL_FORMAT_MAP:
        return 0, len(input_paths), [f"不支持的目标格式: {target_extension}"]

    target_format = PIL_FORMAT_MAP[target_extension]
    
    success_count = 0
    fail_count = 0
    errors = []

    print(f"\n{Fore.CYAN}[批量图片转换] 开始处理 {len(input_paths)} 个文件{Style.RESET_ALL}")
    print(f"目标格式: {target_extension.upper()}")
    print("-" * 50)

    for i, input_path in enumerate(input_paths, 1):
        # 生成输出路径
        basename = os.path.splitext(os.path.basename(input_path))[0]
        
        if output_dir:
            output_path = os.path.join(output_dir, basename + target_extension)
        else:
            # 在原文件目录生成
            input_dir = os.path.dirname(input_path)
            output_path = os.path.join(input_dir, basename + target_extension)
        
        # 避免覆盖原文件
        if os.path.normpath(input_path) == os.path.normpath(output_path):
            output_path = os.path.join(
                os.path.dirname(output_path),
                basename + "_converted" + target_extension
            )

        # 转换
        print(f"[{i}/{len(input_paths)}] {os.path.basename(input_path)} -> {os.path.basename(output_path)}", end=" ")
        
        success, msg = convert_image(input_path, output_path, target_format, quality)
        
        if success:
            print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
            success_count += 1
        else:
            print(f"{Fore.RED}✗ {msg}{Style.RESET_ALL}")
            fail_count += 1
            errors.append(f"{os.path.basename(input_path)}: {msg}")

    print("-" * 50)
    print(f"完成: 成功 {success_count} 个, 失败 {fail_count} 个")

    return success_count, fail_count, errors
