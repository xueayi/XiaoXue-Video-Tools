# -*- coding: utf-8 -*-
"""
批量执行器模块：包含批量创建文件夹、批量重命名相关执行函数。
"""
import os

from colorama import Fore, Style

from ..presets import RENAME_MODES, RENAME_TARGETS, RENAME_BEHAVIORS
from ..folder_creator import batch_create_folders
from ..batch_renamer import batch_rename, RenameConfig
from .common import print_task_header


def execute_folder_creator(args):
    """
    执行批量创建文件夹任务。
    
    Args:
        args: argparse 解析后的参数对象
    """
    print_task_header("批量创建文件夹")

    txt_path = args.folder_txt
    output_dir = args.folder_output_dir
    auto_number = getattr(args, 'folder_auto_number', True)

    # 如果未指定输出目录，使用 TXT 文件所在目录
    if not output_dir or not output_dir.strip():
        output_dir = os.path.dirname(txt_path)
        print(f"[自动设置] 输出目录: {output_dir}")
    else:
        # 清理尾部斜杠
        output_dir = output_dir.rstrip("/\\")

    success, fail, errors = batch_create_folders(
        txt_path=txt_path,
        output_dir=output_dir,
        auto_number=auto_number,
    )

    if errors:
        print(f"\n{Fore.YELLOW}[警告] 部分创建失败:{Style.RESET_ALL}")
        for err in errors[:5]:
            print(f"  - {err}")


def execute_batch_rename(args):
    """
    执行批量序列重命名任务。
    
    Args:
        args: argparse 解析后的参数对象
    """
    print_task_header("批量序列重命名")

    input_dir = args.rename_input_dir
    
    # 解析模式
    mode_name = getattr(args, 'rename_mode', '原地重命名')
    mode = RENAME_MODES.get(mode_name, 'rename_in_place')
    
    # 解析目标类型
    target_name = getattr(args, 'rename_target', '图片和视频')
    target_type = RENAME_TARGETS.get(target_name, 'both')
    
    # 解析递归行为
    behavior_name = getattr(args, 'rename_recursive', '递归模式（保持目录结构）')
    recursive = RENAME_BEHAVIORS.get(behavior_name, True)
    
    # 解析扩展名
    image_exts = [ext.strip() for ext in args.rename_image_exts.split(',') if ext.strip()]
    video_exts = [ext.strip() for ext in args.rename_video_exts.split(',') if ext.strip()]
    
    # 输出目录
    output_dir = args.rename_output_dir if args.rename_output_dir else None
    
    # 排除下划线
    exclude_underscore = getattr(args, 'rename_exclude_underscore', True)

    # 创建配置
    config = RenameConfig(
        mode=mode,
        output_dir=output_dir,
        target_type=target_type,
        image_extensions=image_exts,
        video_extensions=video_exts,
        recursive=recursive,
        exclude_underscore=exclude_underscore,
    )

    success, fail, errors = batch_rename(
        input_path=input_dir,
        config=config,
    )

    if errors:
        print(f"\n{Fore.YELLOW}[警告] 部分重命名失败:{Style.RESET_ALL}")
        for err in errors[:5]:
            print(f"  - {err}")
