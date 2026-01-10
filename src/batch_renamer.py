# -*- coding: utf-8 -*-
"""
批量序列重命名模块：按规则批量重命名图片和视频文件。
"""
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from colorama import Fore, Style


@dataclass
class RenameConfig:
    """重命名配置类。"""
    # 重命名模式: "rename_in_place", "copy_rename", "move_rename"
    mode: str = "rename_in_place"
    # 安全输出路径 (复制/移动模式使用)
    output_dir: Optional[str] = None
    # 目标类型: "images", "videos", "both"
    target_type: str = "both"
    # 图片扩展名列表
    image_extensions: List[str] = field(default_factory=lambda: ["png", "jpg"])
    # 视频扩展名列表
    video_extensions: List[str] = field(default_factory=lambda: ["mp4", "mov"])
    # 是否递归模式
    recursive: bool = True
    # 递归模式下是否排除下划线后的文字
    exclude_underscore: bool = True


def normalize_extensions(extensions: List[str]) -> List[str]:
    """标准化扩展名列表 (小写，无点号)。"""
    result = []
    for ext in extensions:
        ext = ext.strip().lower()
        if ext.startswith("."):
            ext = ext[1:]
        if ext:
            result.append(ext)
    return result


def get_file_size(file_path: str) -> int:
    """获取文件大小 (字节)。"""
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0


def get_files_sorted_by_size(
    directory: str,
    extensions: List[str],
    recursive: bool = True,
) -> List[str]:
    """
    获取按文件大小排序的文件列表。

    Args:
        directory: 目录路径
        extensions: 扩展名列表 (不含点号)
        recursive: 是否递归

    Returns:
        按大小排序的文件路径列表
    """
    files = []
    extensions = set(normalize_extensions(extensions))

    if recursive:
        for root, _, filenames in os.walk(directory):
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower().lstrip(".")
                if ext in extensions:
                    files.append(os.path.join(root, filename))
    else:
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                ext = os.path.splitext(filename)[1].lower().lstrip(".")
                if ext in extensions:
                    files.append(filepath)

    # 按文件大小排序
    files.sort(key=get_file_size)
    return files


def process_parent_folder_name(
    file_path: str,
    base_dir: str,
    exclude_underscore: bool = True,
) -> str:
    """
    处理父文件夹名称，生成前缀。

    Args:
        file_path: 文件完整路径
        base_dir: 基础目录
        exclude_underscore: 是否排除下划线后的文字

    Returns:
        文件夹前缀字符串
    """
    # 获取相对路径
    rel_path = os.path.relpath(file_path, base_dir)
    dir_path = os.path.dirname(rel_path)

    if not dir_path or dir_path == ".":
        return ""

    # 分割路径层级
    parts = dir_path.split(os.sep)
    
    processed_parts = []
    for part in parts:
        if exclude_underscore and "_" in part:
            # 取第一个下划线之前的部分
            part = part.split("_", 1)[0]
        # 清理非法字符
        part = re.sub(r'[\\/:*?"<>|]', "_", part)
        part = part.strip("_")
        if part:
            processed_parts.append(part)

    if processed_parts:
        return "_".join(processed_parts) + "_"
    return ""


def determine_media_type(file_path: str, config: RenameConfig) -> Optional[str]:
    """
    判断文件的媒体类型。

    Args:
        file_path: 文件路径
        config: 重命名配置

    Returns:
        "图片", "视频", 或 None
    """
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    
    image_exts = set(normalize_extensions(config.image_extensions))
    video_exts = set(normalize_extensions(config.video_extensions))

    if config.target_type in ("images", "both") and ext in image_exts:
        return "图片"
    if config.target_type in ("videos", "both") and ext in video_exts:
        return "视频"
    return None


def batch_rename(
    input_path: str,
    config: RenameConfig,
) -> Tuple[int, int, List[str]]:
    """
    批量重命名文件。

    Args:
        input_path: 输入目录路径
        config: 重命名配置

    Returns:
        (成功数, 失败数, 错误消息列表)
    """
    print(f"\n{Fore.CYAN}[批量序列重命名]{Style.RESET_ALL}")
    print(f"输入路径: {input_path}")
    print(f"重命名模式: {config.mode}")
    print(f"目标类型: {config.target_type}")
    print(f"递归模式: {'是' if config.recursive else '否'}")
    print(f"排除下划线后文字: {'是' if config.exclude_underscore else '否'}")
    print("-" * 50)

    if not os.path.isdir(input_path):
        return 0, 1, [f"输入路径不是有效目录: {input_path}"]

    # 获取所有扩展名
    all_extensions = []
    if config.target_type in ("images", "both"):
        all_extensions.extend(config.image_extensions)
    if config.target_type in ("videos", "both"):
        all_extensions.extend(config.video_extensions)

    # 获取所有符合条件的文件
    files = get_files_sorted_by_size(input_path, all_extensions, config.recursive)

    if not files:
        print(f"{Fore.YELLOW}[提示] 未找到符合条件的文件{Style.RESET_ALL}")
        return 0, 0, []

    print(f"找到 {len(files)} 个文件")
    print("-" * 50)

    # 确定输出目录
    if config.mode == "rename_in_place":
        output_base = input_path
    else:
        if config.output_dir:
            output_base = config.output_dir
        else:
            output_base = os.path.join(input_path, "rename_output")
        os.makedirs(output_base, exist_ok=True)

    # 按 (相对目录, 媒体类型) 分组并计数
    # 键: (相对目录路径, 媒体类型) -> 文件列表
    grouped_files: Dict[Tuple[str, str], List[str]] = defaultdict(list)

    for file_path in files:
        media_type = determine_media_type(file_path, config)
        if not media_type:
            continue

        if config.recursive:
            rel_dir = os.path.dirname(os.path.relpath(file_path, input_path))
        else:
            rel_dir = ""

        key = (rel_dir, media_type)
        grouped_files[key].append(file_path)

    success_count = 0
    fail_count = 0
    errors = []

    # 处理每个分组
    for (rel_dir, media_type), file_list in grouped_files.items():
        # 每个分组独立编号
        for idx, file_path in enumerate(file_list, 1):
            ext = os.path.splitext(file_path)[1]
            
            # 生成新文件名
            if config.recursive and rel_dir:
                prefix = process_parent_folder_name(
                    file_path, input_path, config.exclude_underscore
                )
                new_name = f"{prefix}{media_type}_{idx}{ext}"
            else:
                new_name = f"{media_type}_{idx}{ext}"

            # 确定输出路径
            if config.mode == "rename_in_place":
                # 原地重命名：在原目录
                new_path = os.path.join(os.path.dirname(file_path), new_name)
            else:
                # 复制/移动：保持目录结构
                if rel_dir:
                    target_dir = os.path.join(output_base, rel_dir)
                    os.makedirs(target_dir, exist_ok=True)
                    new_path = os.path.join(target_dir, new_name)
                else:
                    new_path = os.path.join(output_base, new_name)

            # 避免覆盖
            if os.path.exists(new_path) and os.path.normpath(file_path) != os.path.normpath(new_path):
                base, ext = os.path.splitext(new_path)
                counter = 1
                while os.path.exists(new_path):
                    new_path = f"{base}_{counter}{ext}"
                    counter += 1

            try:
                if config.mode == "rename_in_place":
                    os.rename(file_path, new_path)
                    op = "重命名"
                elif config.mode == "copy_rename":
                    shutil.copy2(file_path, new_path)
                    op = "复制"
                else:  # move_rename
                    shutil.move(file_path, new_path)
                    op = "移动"

                rel_src = os.path.relpath(file_path, input_path)
                rel_dst = os.path.relpath(new_path, output_base if config.mode != "rename_in_place" else input_path)
                print(f"{Fore.GREEN}[{op}]{Style.RESET_ALL} {rel_src} -> {rel_dst}")
                success_count += 1

            except Exception as e:
                print(f"{Fore.RED}[失败]{Style.RESET_ALL} {os.path.basename(file_path)}: {e}")
                fail_count += 1
                errors.append(f"{os.path.basename(file_path)}: {str(e)}")

    print("-" * 50)
    print(f"完成: 成功 {success_count} 个, 失败 {fail_count} 个")

    if config.mode != "rename_in_place":
        print(f"输出目录: {output_base}")

    return success_count, fail_count, errors
