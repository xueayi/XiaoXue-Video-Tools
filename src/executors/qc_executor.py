# -*- coding: utf-8 -*-
"""
质量检测执行器模块：包含素材质量检测相关执行函数。
"""
import os

from colorama import Fore, Style

from ..qc import scan_directory, generate_report
from ..presets import RESOLUTION_PRESETS
from ..utils import auto_generate_output_path
from ..task.report import TaskReport
from ..task.result import TaskResult
from .common import print_task_header, parse_comma_list


def execute_qc(args) -> TaskResult:
    """
    执行素材质量检测任务。

    Args:
        args: argparse 解析后的参数对象

    Returns:
        TaskResult: 扫描本身失败=FAILED；部分文件探测失败=PARTIAL+warnings；
        全部探测失败=FAILED；成功=SUCCESS(outputs=[报告路径])。
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

    try:
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
    except Exception as e:  # 扫描本身失败: 无法给出任何检测结果
        print(f"{Fore.RED}[错误] 扫描失败: {e}{Style.RESET_ALL}")
        return TaskResult.failed(f"扫描失败: {e}")

    try:
        report = generate_report(results, report_path)
    except Exception as e:  # 报告落盘失败也算任务失败
        print(f"{Fore.RED}[错误] 报告生成失败: {e}{Style.RESET_ALL}")
        return TaskResult.failed(f"生成报告失败: {e}")

    # 在终端显示报告预览
    print("\n" + "=" * 50)
    print("报告预览:")
    print("=" * 50)
    print(report)

    # 逐文件汇总: is_valid=False 表示该文件探测失败
    task_report = TaskReport()
    report_output_added = False
    for info in results:
        if getattr(info, "is_valid", True):
            task_report.add_success(
                report_path if not report_output_added else None)
            report_output_added = True
        else:
            reason = f"{info.filename}: 探测失败"
            if info.errors:
                reason += f"（{info.errors[0]}）"
            task_report.add_failure(reason)
            for error in info.errors:
                task_report.warn(f"{info.filename}: {error}")

    task_report.details.update({
        "report_path": report_path,
        "file_count": len(results),
    })
    return task_report.finalize()
