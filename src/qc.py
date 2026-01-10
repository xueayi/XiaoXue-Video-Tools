# -*- coding: utf-8 -*-
"""
素材质量检测 (QC) 模块：分析视频文件，生成兼容性报告。
"""
import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from colorama import Fore, Style

from .utils import get_ffprobe_path


# Premiere Pro 不兼容的容器格式
PR_INCOMPATIBLE_CONTAINERS = {".mkv", ".webm", ".ogv", ".ogg", ".flv"}

# Premiere Pro 不兼容的视频编码
PR_INCOMPATIBLE_CODECS = {"vp8", "vp9", "av1", "theora"}

# 不兼容的图片格式 (作为视频序列导入时可能有问题)
PR_INCOMPATIBLE_IMAGE_FORMATS = {".webp", ".heic", ".avif"}


@dataclass
class MediaInfo:
    """媒体文件信息数据类。"""
    path: str
    filename: str = ""
    container: str = ""
    duration_sec: float = 0.0
    video_codec: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    bitrate_kbps: int = 0
    audio_codec: str = ""
    audio_bitrate_kbps: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    is_valid: bool = True

    def __post_init__(self):
        self.filename = os.path.basename(self.path)
        self.container = os.path.splitext(self.path)[1].lower()


def probe_media(file_path: str) -> Optional[MediaInfo]:
    """
    使用 ffprobe 获取媒体文件信息。

    Args:
        file_path: 文件路径。

    Returns:
        MediaInfo 对象, 若失败则返回 None。
    """
    ffprobe = get_ffprobe_path()
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-print_format", "json",
        file_path
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )

        if result.returncode != 0:
            info = MediaInfo(path=file_path)
            info.is_valid = False
            info.errors.append(f"无法读取文件: {result.stderr.strip()}")
            return info

        data = json.loads(result.stdout)
        return _parse_ffprobe_output(file_path, data)

    except Exception as e:
        info = MediaInfo(path=file_path)
        info.is_valid = False
        info.errors.append(f"探测失败: {str(e)}")
        return info


def _parse_ffprobe_output(file_path: str, data: Dict[str, Any]) -> MediaInfo:
    """解析 ffprobe JSON 输出。"""
    info = MediaInfo(path=file_path)

    # 格式信息
    fmt = data.get("format", {})
    info.duration_sec = float(fmt.get("duration", 0))
    total_bitrate = int(fmt.get("bit_rate", 0)) // 1000  # kbps
    info.bitrate_kbps = total_bitrate

    # 流信息
    streams = data.get("streams", [])
    for stream in streams:
        codec_type = stream.get("codec_type")
        if codec_type == "video":
            info.video_codec = stream.get("codec_name", "unknown")
            info.width = int(stream.get("width", 0))
            info.height = int(stream.get("height", 0))
            # FPS 解析
            fps_str = stream.get("r_frame_rate", "0/1")
            try:
                num, den = map(int, fps_str.split("/"))
                info.fps = round(num / den, 2) if den else 0
            except:
                info.fps = 0
        elif codec_type == "audio":
            info.audio_codec = stream.get("codec_name", "unknown")
            info.audio_bitrate_kbps = int(stream.get("bit_rate", 0)) // 1000

    return info


def check_compatibility(
    info: MediaInfo,
    max_bitrate_kbps: int = 0,
    max_resolution: str = "",
    min_bitrate_kbps: int = 0,
    min_resolution: str = "",
    check_pr_video: bool = True,
    check_pr_image: bool = True,
    incompatible_containers: Optional[set] = None,
    incompatible_codecs: Optional[set] = None,
    incompatible_images: Optional[set] = None,
) -> MediaInfo:
    """
    检查媒体文件的兼容性和阈值。

    Args:
        info: MediaInfo 对象。
        max_bitrate_kbps: 最大码率阈值 (kbps), 0 表示不检查。
        max_resolution: 最大分辨率 (如 "1920x1080"), 空表示不检查。
        min_bitrate_kbps: 最小码率阈值 (kbps), 0 表示不检查。
        min_resolution: 最小分辨率 (如 "1920x1080"), 空表示不检查。
        check_pr_video: 是否开启 PR 视频兼容性检查。
        check_pr_image: 是否开启 PR 图片兼容性检查。
        incompatible_containers: 自定义不兼容容器集合 (如 {".mkv", ".webm"})。
        incompatible_codecs: 自定义不兼容编码集合 (如 {"vp9", "av1"})。
        incompatible_images: 自定义不兼容图片格式集合 (如 {".webp"})。

    Returns:
        更新后的 MediaInfo (添加 warnings/errors)。
    """
    # 使用用户自定义规则或默认规则
    containers_to_check = incompatible_containers if incompatible_containers else PR_INCOMPATIBLE_CONTAINERS
    codecs_to_check = incompatible_codecs if incompatible_codecs else PR_INCOMPATIBLE_CODECS
    images_to_check = incompatible_images if incompatible_images else PR_INCOMPATIBLE_IMAGE_FORMATS
    
    # ----------------------------------------
    # 1. 基础阈值检查
    # ----------------------------------------
    
    # 最大码率阈值
    if max_bitrate_kbps > 0 and info.bitrate_kbps > max_bitrate_kbps:
        info.warnings.append(f"码率 {info.bitrate_kbps}kbps 超过最大阈值 {max_bitrate_kbps}kbps")

    # 最小码率阈值
    if min_bitrate_kbps > 0 and info.bitrate_kbps < min_bitrate_kbps:
        info.warnings.append(f"码率 {info.bitrate_kbps}kbps 低于最小阈值 {min_bitrate_kbps}kbps")

    # 最大分辨率阈值
    if max_resolution:
        try:
            max_w, max_h = map(int, max_resolution.split("x"))
            if info.width > max_w or info.height > max_h:
                info.warnings.append(f"分辨率 {info.width}x{info.height} 超过最大阈值 {max_resolution}")
        except:
            pass
            
    # 最小分辨率阈值
    if min_resolution:
        try:
            min_w, min_h = map(int, min_resolution.split("x"))
            if info.width < min_w or info.height < min_h:
                info.warnings.append(f"分辨率 {info.width}x{info.height} 低于最小阈值 {min_resolution}")
        except:
            pass

    # ----------------------------------------
    # 2. 兼容性检查 (使用自定义或默认规则)
    # ----------------------------------------
    
    if check_pr_video:
        # 容器格式
        if info.container in containers_to_check:
            info.warnings.append(f"[兼容性] 容器 {info.container} 可能导致兼容性问题")
        
        # 视频编码
        if info.video_codec.lower() in codecs_to_check:
            info.warnings.append(f"[兼容性] 编码 {info.video_codec} 可能导致兼容性问题")
            
        # MKV 封装额外提示
        if info.container == ".mkv":
             info.warnings.append(f"[兼容性] MKV 封装对某些软件不友好，建议转封装为 MP4/MOV")

    if check_pr_image:
        if info.container in images_to_check:
            info.errors.append(f"[兼容性] 图片格式 {info.container} 可能不被支持")

    return info


def scan_directory(
    directory: str,
    extensions: Optional[List[str]] = None,
    max_bitrate_kbps: int = 0,
    max_resolution: str = "",
    min_bitrate_kbps: int = 0,
    min_resolution: str = "",
    check_pr_video: bool = False,
    check_pr_image: bool = False,
    incompatible_containers: Optional[set] = None,
    incompatible_codecs: Optional[set] = None,
    incompatible_images: Optional[set] = None,
) -> List[MediaInfo]:
    """
    递归扫描目录下的媒体文件。

    Args:
        directory: 目标目录。
        extensions: 要扫描的扩展名列表。
        max_bitrate_kbps: 最大码率阈值。
        max_resolution: 最大分辨率阈值。
        min_bitrate_kbps: 最小码率阈值。
        min_resolution: 最小分辨率阈值。
        check_pr_video: 检查 PR 视频兼容性。
        check_pr_image: 检查 PR 图片兼容性。
        incompatible_containers: 自定义不兼容容器集合。
        incompatible_codecs: 自定义不兼容编码集合。
        incompatible_images: 自定义不兼容图片格式集合。

    Returns:
        MediaInfo 列表。
    """
    if extensions is None:
        extensions = [".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".mts", ".m2ts"]

    # 使用自定义或默认的图片格式集合
    image_formats = incompatible_images if incompatible_images else PR_INCOMPATIBLE_IMAGE_FORMATS
    
    extensions = [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions]
    results = []

    print(f"{Fore.CYAN}[小雪工具箱] 开始扫描目录: {directory}{Style.RESET_ALL}")

    for root, dirs, files in os.walk(directory):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in extensions or ext in image_formats:
                file_path = os.path.join(root, filename)
                print(f"  扫描: {file_path}")
                info = probe_media(file_path)
                if info:
                    info = check_compatibility(
                        info, 
                        max_bitrate_kbps=max_bitrate_kbps, 
                        max_resolution=max_resolution,
                        min_bitrate_kbps=min_bitrate_kbps,
                        min_resolution=min_resolution,
                        check_pr_video=check_pr_video,
                        check_pr_image=check_pr_image,
                        incompatible_containers=incompatible_containers,
                        incompatible_codecs=incompatible_codecs,
                        incompatible_images=incompatible_images,
                    )
                    results.append(info)

    print(f"{Fore.GREEN}[完成] 共扫描 {len(results)} 个文件{Style.RESET_ALL}")
    return results


def generate_report(results: List[MediaInfo], output_path: str) -> str:
    """
    生成 QC 报告 (TXT 格式)。

    Args:
        results: MediaInfo 列表。
        output_path: 报告输出路径。

    Returns:
        报告内容字符串。
    """
    lines = []
    lines.append("=" * 60)
    lines.append("小雪工具箱 - 素材质量检测报告 (QC Report)")
    lines.append("=" * 60)
    lines.append("")

    # 统计
    total = len(results)
    errors_count = sum(1 for r in results if r.errors)
    warnings_count = sum(1 for r in results if r.warnings)
    ok_count = total - errors_count - warnings_count + sum(1 for r in results if r.errors and r.warnings)

    lines.append(f"总计扫描: {total} 个文件")
    lines.append(f"  ✓ 通过: {ok_count}")
    lines.append(f"  ⚠ 警告: {warnings_count}")
    lines.append(f"  ✗ 错误: {errors_count}")
    lines.append("")
    lines.append("-" * 60)

    for info in results:
        status_icon = "✓"
        if info.errors:
            status_icon = "✗"
        elif info.warnings:
            status_icon = "⚠"

        lines.append(f"\n[{status_icon}] {info.filename}")
        lines.append(f"    路径: {info.path}")
        if info.is_valid:
            lines.append(f"    容器: {info.container} | 编码: {info.video_codec} | 分辨率: {info.width}x{info.height}")
            lines.append(f"    帧率: {info.fps} FPS | 码率: {info.bitrate_kbps} kbps | 时长: {info.duration_sec:.1f}s")

        for err in info.errors:
            lines.append(f"    [错误] {err}")
        for warn in info.warnings:
            lines.append(f"    [警告] {warn}")

    lines.append("\n" + "=" * 60)
    lines.append("报告生成完毕")
    lines.append("=" * 60)

    report_content = "\n".join(lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"{Fore.GREEN}[成功] 报告已保存到: {output_path}{Style.RESET_ALL}")
    return report_content
