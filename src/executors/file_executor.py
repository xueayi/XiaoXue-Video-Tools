# -*- coding: utf-8 -*-
"""
文件执行器模块：包含封装转换、图片转换相关执行函数。
"""
import os

from colorama import Fore, Style

from ..core import build_remux_command, run_ffmpeg_command
from ..presets import REMUX_PRESETS, IMAGE_FORMATS
from ..utils import auto_generate_output_path
from ..image_converter import batch_convert_images
from .common import print_task_header


def execute_remux(args):
    """
    执行封装转换任务（支持批量）。
    
    Args:
        args: argparse 解析后的参数对象
    """
    print_task_header("封装转换")

    preset_name = getattr(args, 'remux_preset', 'MP4 (H.264 兼容)')
    preset = REMUX_PRESETS.get(preset_name, {})
    extension = preset.get("extension", ".mp4")
    overwrite = getattr(args, 'remux_overwrite', False)
    
    # 获取输入文件列表
    input_files = args.remux_input
    if isinstance(input_files, str):
        input_files = [input_files]
    
    output_dir = args.remux_output if args.remux_output else None
    
    print(f"[预设] {preset_name}")
    print(f"[输入文件数] {len(input_files)}")
    if output_dir:
        print(f"[输出目录] {output_dir}")
    if overwrite:
        print(f"{Fore.YELLOW}[警告] 覆盖模式已开启，原文件将被删除{Style.RESET_ALL}")
    print("-" * 50)

    success_count = 0
    fail_count = 0
    files_to_delete = []  # 成功后需要删除的原文件

    for i, input_path in enumerate(input_files, 1):
        print(f"\n[{i}/{len(input_files)}] 处理: {os.path.basename(input_path)}")
        
        # 生成输出路径
        if output_dir:
            basename = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(output_dir, basename + "_remux" + extension)
        else:
            output_path = auto_generate_output_path(input_path, "_remux", extension)
        
        print(f"[输出] {output_path}")

        cmd = build_remux_command(
            input_path=input_path,
            output_path=output_path,
        )

        result = run_ffmpeg_command(cmd)
        if result == 0:
            success_count += 1
            if overwrite and os.path.normpath(input_path) != os.path.normpath(output_path):
                files_to_delete.append(input_path)
        else:
            fail_count += 1

    # 覆盖模式：删除原文件
    if overwrite and files_to_delete:
        print(f"\n{Fore.YELLOW}[覆盖模式] 删除 {len(files_to_delete)} 个原文件...{Style.RESET_ALL}")
        for f in files_to_delete:
            try:
                os.remove(f)
                print(f"  ✓ 已删除: {os.path.basename(f)}")
            except Exception as e:
                print(f"  ✗ 删除失败: {os.path.basename(f)} - {e}")

    print(f"\n{'='*50}")
    print(f"批量转换完成: 成功 {success_count} 个, 失败 {fail_count} 个")


def execute_image_convert(args):
    """
    执行图片格式转换任务。
    
    Args:
        args: argparse 解析后的参数对象
    """
    print_task_header("图片格式转换")

    # 获取输入文件列表
    input_files = args.img_input
    if isinstance(input_files, str):
        input_files = [input_files]

    # 确定目标格式
    format_preset = getattr(args, 'img_format', 'PNG (无损)')
    if format_preset == "自定义":
        target_ext = getattr(args, 'img_format_custom', 'png')
        if not target_ext:
            print(f"{Fore.RED}[错误] 选择自定义格式时必须输入扩展名{Style.RESET_ALL}")
            return
    else:
        target_ext = IMAGE_FORMATS.get(format_preset, ".png")

    # 确保扩展名格式正确
    if target_ext and not target_ext.startswith("."):
        target_ext = "." + target_ext

    output_dir = args.img_output_dir if args.img_output_dir else None
    quality = getattr(args, 'img_quality', 95)
    overwrite = getattr(args, 'img_overwrite', False)

    print(f"[目标格式] {target_ext}")
    print(f"[质量] {quality}")
    print(f"[文件数量] {len(input_files)}")
    if overwrite:
        print(f"{Fore.YELLOW}[警告] 覆盖模式已开启，原文件将被删除{Style.RESET_ALL}")

    success, fail, errors = batch_convert_images(
        input_paths=input_files,
        output_dir=output_dir,
        target_extension=target_ext,
        quality=quality,
    )

    # 覆盖模式：删除成功转换的原文件
    if overwrite and success > 0:
        print(f"\n{Fore.YELLOW}[覆盖模式] 删除原文件...{Style.RESET_ALL}")
        deleted_count = 0
        for input_path in input_files:
            # 只删除成功转换的，且新旧文件扩展名不同的
            input_ext = os.path.splitext(input_path)[1].lower()
            if input_ext != target_ext.lower():
                try:
                    os.remove(input_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"  ✗ 删除失败: {os.path.basename(input_path)} - {e}")
        if deleted_count > 0:
            print(f"  ✓ 已删除 {deleted_count} 个原文件")

    if errors:
        print(f"\n{Fore.YELLOW}[警告] 部分转换失败:{Style.RESET_ALL}")
        for err in errors[:5]:
            print(f"  - {err}")
