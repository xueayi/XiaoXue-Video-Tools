# -*- coding: utf-8 -*-
"""
Shield 执行器模块：包含露骨图片识别相关执行函数。

该模块依赖 imgutils 库，仅在可用时才能导入。
"""
import os

from colorama import Fore, Style

from .common import print_task_header


# 条件导入 imgutils
try:
    from imgutils.validate import anime_rating
    SHIELD_AVAILABLE = True
except ImportError:
    SHIELD_AVAILABLE = False


def execute_shield(args):
    """
    执行露骨图片识别任务 (Shield)。
    
    Args:
        args: argparse 解析后的参数对象
    """
    print_task_header("露骨图片识别")
    
    if not SHIELD_AVAILABLE:
        print(f"{Fore.RED}[错误] Shield 功能不可用，请使用 Shield 增强版{Style.RESET_ALL}")
        return
    
    from ..nsfw_detect import (
        scan_directory as shield_scan_directory,
        scan_files as shield_scan_files,
        generate_report as shield_generate_report,
    )
    from ..presets import SHIELD_THRESHOLDS, SHIELD_CENSOR_TYPES
    
    # 获取参数
    input_dir = getattr(args, 'shield_input_dir', '')
    input_files = getattr(args, 'shield_input_files', None) or []
    output_dir = getattr(args, 'shield_output_dir', '')
    report_path = getattr(args, 'shield_report', '')
    
    threshold_name = getattr(args, 'shield_threshold', 'Questionable 及以上 (推荐)')
    threshold = SHIELD_THRESHOLDS.get(threshold_name, 'questionable')
    
    recursive = getattr(args, 'shield_recursive', True)
    enable_censor = getattr(args, 'shield_enable_censor', False)
    
    censor_type_name = getattr(args, 'shield_censor_type', '马赛克 (Pixelate)')
    censor_type = SHIELD_CENSOR_TYPES.get(censor_type_name, 'pixelate')
    
    mosaic_size = int(getattr(args, 'shield_mosaic_size', '16'))
    overlay_path = getattr(args, 'shield_overlay_image', '')
    expand_pixels = int(getattr(args, 'shield_expand_pixels', '0'))
    
    # 确定输入源
    if not input_dir and not input_files:
        print(f"{Fore.RED}[错误] 请选择扫描目录或图片文件{Style.RESET_ALL}")
        return
    
    # 确定输出目录
    if not output_dir:
        if input_dir:
            output_dir = os.path.join(input_dir, 'shield_output')
        elif input_files:
            output_dir = os.path.join(os.path.dirname(input_files[0]), 'shield_output')
    
    # 确定报告路径
    if not report_path:
        report_path = os.path.join(output_dir, 'shield_report.txt')
    
    print(f"[风险阈值] {threshold_name} -> {threshold}")
    print(f"[自动打码] {'是' if enable_censor else '否'}")
    if enable_censor:
        print(f"[打码类型] {censor_type_name}")
        if censor_type == "custom":
            print(f"[覆盖图片] {overlay_path}")
        else:
            print(f"[马赛克大小] {mosaic_size}px")
        if expand_pixels > 0:
            print(f"[范围扩展] {expand_pixels}px")
    print(f"[输出目录] {output_dir}")
    print(f"[报告路径] {report_path}")
    print("-" * 50)
    
    # 执行扫描
    if input_dir:
        results = shield_scan_directory(
            directory=input_dir,
            threshold=threshold,
            recursive=recursive,
            enable_censor=enable_censor,
            output_dir=output_dir,
            censor_type=censor_type,
            mosaic_size=mosaic_size,
            overlay_path=overlay_path,
            expand_pixels=expand_pixels,
        )
    else:
        results = shield_scan_files(
            file_paths=input_files,
            threshold=threshold,
            enable_censor=enable_censor,
            output_dir=output_dir,
            censor_type=censor_type,
            mosaic_size=mosaic_size,
            overlay_path=overlay_path,
            expand_pixels=expand_pixels,
        )
    
    # 生成报告
    if results:
        report = shield_generate_report(results, report_path)
        
        # 显示报告预览
        print("\n" + "=" * 50)
        print("报告预览:")
        print("=" * 50)
        print(report)
    else:
        print(f"\n{Fore.YELLOW}[提示] 未找到可扫描的图片{Style.RESET_ALL}")
