# -*- coding: utf-8 -*-
"""
图片格式转换模块：支持批量图片格式互转。
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Tuple

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

# 单张图片的转换状态
ConvertStatus = Literal["success", "failed", "skipped"]


@dataclass(frozen=True)
class FileConvertResult:
    """单张图片的转换结果。

    调用方删除源文件前必须先通过 can_delete_source() 校验，
    避免转换失败/被跳过/输出不存在时误删用户源文件。
    """

    source: Path
    output: Optional[Path]
    status: ConvertStatus
    error: Optional[str] = None

    def __post_init__(self):
        # 兼容 str / Path 两种调用方式，统一为 Path
        object.__setattr__(self, "source", Path(self.source))
        if self.output is not None:
            object.__setattr__(self, "output", Path(self.output))

    def can_delete_source(self) -> bool:
        """是否可安全删除源文件：转换成功 + 输出存在 + 与源不是同一文件。"""
        if self.status != "success" or self.output is None:
            return False
        try:
            if not self.output.is_file():
                return False
        except OSError:
            # 就低不就高：任何校验异常都保留源文件
            return False
        return not _is_same_file(self.source, self.output)


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

        # 保存后复核输出文件确实落盘，避免“看似成功但文件不存在”时误删源文件
        if not os.path.isfile(output_path):
            return False, f"转换失败: 输出文件未生成 ({os.path.basename(output_path)})"

        return True, f"成功转换: {os.path.basename(output_path)}"
        
    except Exception as e:
        return False, f"转换失败: {str(e)}"


def _normalize_extension(ext: str) -> str:
    """
    归一化图片扩展名，使 .jpg 和 .jpeg 视为同一格式。

    Args:
        ext: 文件扩展名 (含前导点号)

    Returns:
        归一化后的扩展名
    """
    ext = ext.lower()
    if ext == ".jpeg":
        return ".jpg"
    if ext == ".tif":
        return ".tiff"
    return ext


def _path_key(path) -> str:
    """返回路径比较键：存在时解析真实路径，否则退化为 normcase(abspath)。"""
    try:
        if os.path.exists(path):
            return os.path.normcase(os.path.realpath(path))
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(str(path)))


def _is_same_file(path_a, path_b) -> bool:
    """判断两个路径是否指向同一文件。

    文件都存在时优先 os.path.samefile（可识别大小写、符号链接、长路径等），
    否则退化为归一化路径比较（Windows 大小写不敏感）。
    """
    try:
        if os.path.exists(path_a) and os.path.exists(path_b):
            return os.path.samefile(path_a, path_b)
    except OSError:
        pass
    return _path_key(path_a) == _path_key(path_b)


def _output_available(candidate: str, input_paths: List[str], reserved: set) -> bool:
    """候选输出路径是否可用：不与输入同一文件、未被本批占用、不覆盖既有文件。"""
    if _path_key(candidate) in reserved:
        return False
    if any(_is_same_file(candidate, p) for p in input_paths):
        return False
    try:
        return not os.path.exists(candidate)
    except OSError:
        return False


def _reserve_output(candidate: str, input_paths: List[str], reserved: set) -> str:
    """为输出路径预占位，避免覆盖输入文件、既有文件或同批其他输出。

    冲突时依次尝试 `_converted`（与输入同一文件的旧命名习惯）、`_1`/`_2`… 后缀；
    成功占位后写入 reserved，供同批后续输入使用。

    Args:
        candidate: 初始输出路径
        input_paths: 本批全部输入路径
        reserved: 本批已被其他输入占用的输出路径键集合

    Returns:
        可安全写入的输出路径
    """
    base, ext = os.path.splitext(candidate)
    current = candidate

    # 与任一输入是同一文件时优先使用 _converted 后缀（保留历史命名）
    if any(_is_same_file(candidate, p) for p in input_paths):
        current = base + "_converted" + ext

    index = 0
    while not _output_available(current, input_paths, reserved):
        index += 1
        current = f"{base}_{index}{ext}"

    reserved.add(_path_key(current))
    return current


def batch_convert_images(
    input_paths: List[str],
    output_dir: Optional[str],
    target_extension: str,
    quality: int = 95,
    skip_same_format: bool = True,
) -> List[FileConvertResult]:
    """
    批量转换图片格式。

    Args:
        input_paths: 输入图片路径列表
        output_dir: 输出目录 (None 则在原文件位置生成)
        target_extension: 目标扩展名 (如 ".png", ".jpg")
        quality: JPEG/WEBP 质量
        skip_same_format: 跳过与目标格式相同的文件

    Returns:
        逐文件结果列表（success/failed/skipped），供调用方决定是否删除源文件
    """
    if isinstance(input_paths, str):
        input_paths = [input_paths]
    input_paths = [str(p) for p in input_paths]

    if not check_pillow_available():
        results = [
            FileConvertResult(p, None, "failed", "Pillow 库不可用")
            for p in input_paths
        ]
        print(f"完成: 成功 0 个, 失败 {len(results)} 个")
        return results

    # 确保扩展名格式正确
    if not target_extension.startswith("."):
        target_extension = "." + target_extension
    target_extension = target_extension.lower()

    # 检查是否为支持的格式
    if target_extension not in PIL_FORMAT_MAP:
        error = f"不支持的目标格式: {target_extension}"
        print(f"{Fore.RED}[错误] {error}{Style.RESET_ALL}")
        results = [
            FileConvertResult(p, None, "failed", error)
            for p in input_paths
        ]
        print(f"完成: 成功 0 个, 失败 {len(results)} 个")
        return results

    target_format = PIL_FORMAT_MAP[target_extension]
    target_ext_normalized = _normalize_extension(target_extension)

    results: List[FileConvertResult] = []
    success_count = 0
    fail_count = 0
    skip_count = 0
    reserved: set = set()

    print(f"\n{Fore.CYAN}[批量图片转换] 开始处理 {len(input_paths)} 个文件{Style.RESET_ALL}")
    print(f"目标格式: {target_extension.upper()}")
    if skip_same_format:
        print(f"已启用: 忽略同格式文件")
    print("-" * 50)

    for i, input_path in enumerate(input_paths, 1):
        # 跳过同格式文件（.jpeg/.jpg、.tif/.tiff 视为同一格式）
        input_ext = os.path.splitext(input_path)[1]
        input_ext_normalized = _normalize_extension(input_ext)

        if skip_same_format and input_ext_normalized == target_ext_normalized:
            print(
                f"[{i}/{len(input_paths)}] "
                f"{Fore.YELLOW}[跳过] {os.path.basename(input_path)} "
                f"已是目标格式 ({target_extension}){Style.RESET_ALL}"
            )
            skip_count += 1
            results.append(FileConvertResult(input_path, None, "skipped"))
            continue

        # 生成输出路径（预占位：不覆盖输入/既有文件/同批其他输出）
        basename = os.path.splitext(os.path.basename(input_path))[0]

        if output_dir:
            candidate = os.path.join(output_dir, basename + target_extension)
        else:
            # 在原文件目录生成
            input_dir = os.path.dirname(input_path)
            candidate = os.path.join(input_dir, basename + target_extension)

        output_path = _reserve_output(candidate, input_paths, reserved)

        # 转换
        print(f"[{i}/{len(input_paths)}] {os.path.basename(input_path)} -> {os.path.basename(output_path)}", end=" ")

        success, msg = convert_image(input_path, output_path, target_format, quality)

        if success:
            print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
            success_count += 1
            results.append(FileConvertResult(input_path, output_path, "success"))
        else:
            print(f"{Fore.RED}✗ {msg}{Style.RESET_ALL}")
            fail_count += 1
            results.append(FileConvertResult(input_path, None, "failed", msg))

    print("-" * 50)
    summary_parts = [f"成功 {success_count} 个", f"失败 {fail_count} 个"]
    if skip_count > 0:
        summary_parts.append(f"跳过 {skip_count} 个")
    print(f"完成: {', '.join(summary_parts)}")

    return results
