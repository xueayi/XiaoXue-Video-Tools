# -*- coding: utf-8 -*-
"""
质量检测执行器模块：包含素材质量检测相关执行函数。
"""
import os

from ..qc import scan_directory, generate_report
from ..presets import RESOLUTION_PRESETS
from ..utils import auto_generate_output_path
from .common import print_task_header, parse_comma_list


def execute_qc(args):
    """
    执行素材质量检测任务。
    
    Args:
        args: argparse 解析后的参数对象
    """
    print_task_header("素材质量检测")

    report_path = args.report_output
    if not report_path:
        if os.path.isdir(args.scan_dir):
            report_path = os.path.join(args.scan_dir, "QC_报告.txt")
        else:
            report_path = auto_generate_output_path(args.scan_dir, "_QC_报告", ".txt")
        print(f"[自动生成报告路径] {report_path}", flush=True)

    # 处理分辨率预设
    max_res = RESOLUTION_PRESETS.get(args.max_res_preset, "")
    if max_res == "custom":
        max_res = args.max_res_custom
        
    min_res = RESOLUTION_PRESETS.get(args.min_res_preset, "")
    if min_res == "custom":
        min_res = args.min_res_custom

    # 解析自定义兼容性规则
    custom_containers = parse_comma_list(getattr(args, 'custom_containers', ''), prefix='.')
    custom_codecs = parse_comma_list(getattr(args, 'custom_codecs', ''))
    custom_images = parse_comma_list(getattr(args, 'custom_images', ''), prefix='.')

    results = scan_directory(
        directory=args.scan_dir,
        max_bitrate_kbps=args.max_bitrate,
        max_resolution=max_res,
        min_bitrate_kbps=args.min_bitrate,
        min_resolution=min_res,
        check_pr_video=args.check_pr_video,
        check_pr_image=args.check_pr_image,
        incompatible_containers=custom_containers if custom_containers else None,
        incompatible_codecs=custom_codecs if custom_codecs else None,
        incompatible_images=custom_images if custom_images else None,
    )

    report = generate_report(results, report_path)

    # 在终端显示报告预览
    print("\n" + "=" * 50)
    print("报告预览:")
    print("=" * 50)
    print(report)
