# -*- coding: utf-8 -*-
"""
元数据检测执行器：使用 ffprobe 探测媒体文件元数据并输出报告。
"""
import os

from colorama import Fore, Style

from ..media_probe import (
    probe_detailed,
    format_media_report,
    generate_media_report,
    PROBE_EXTENSIONS,
)
from .common import print_task_header


def execute_media_probe(args):
    """
    执行媒体元数据检测任务。

    支持两种输入模式:
    1. 多文件选择 (--probe-input-files)
    2. 目录扫描 (--probe-input-dir)

    Args:
        args: argparse 解析后的参数对象
    """
    print_task_header("媒体元数据检测")

    # 收集输入文件
    input_files = []

    # 模式一：多文件选择
    probe_files = getattr(args, 'probe_input_files', None)
    if probe_files:
        if isinstance(probe_files, str):
            probe_files = [probe_files]
        input_files.extend(probe_files)

    # 模式二：目录扫描
    probe_dir = getattr(args, 'probe_input_dir', '')
    if probe_dir and os.path.isdir(probe_dir):
        recursive = getattr(args, 'probe_recursive', True)
        print(f"[扫描目录] {probe_dir} (递归: {'是' if recursive else '否'})")

        if recursive:
            for root, dirs, files in os.walk(probe_dir):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in PROBE_EXTENSIONS:
                        input_files.append(os.path.join(root, filename))
        else:
            for filename in os.listdir(probe_dir):
                filepath = os.path.join(probe_dir, filename)
                if os.path.isfile(filepath):
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in PROBE_EXTENSIONS:
                        input_files.append(filepath)

    # 去重
    input_files = list(dict.fromkeys(input_files))

    if not input_files:
        print(f"{Fore.YELLOW}[提示] 未找到可分析的媒体文件。请选择文件或目录。{Style.RESET_ALL}")
        return

    print(f"[文件数量] {len(input_files)}")
    print("-" * 50)

    # 逐个探测并打印报告
    results = []
    for i, file_path in enumerate(input_files, 1):
        print(f"\n{Fore.CYAN}[{i}/{len(input_files)}] 正在分析: {os.path.basename(file_path)}{Style.RESET_ALL}")

        info = probe_detailed(file_path)
        if info:
            results.append(info)
            # 控制台实时打印报告
            report = format_media_report(info)
            print(report)

    # 保存报告文件（如果指定了输出路径）
    report_output = getattr(args, 'probe_report_output', '')
    if report_output and results:
        generate_media_report(results, report_output)

    # 汇总
    print(f"\n{'=' * 50}")
    print(f"{Fore.GREEN}[完成] 共分析 {len(results)} 个文件{Style.RESET_ALL}")

    # 统计
    total_video = sum(len(r.video_streams) for r in results)
    total_audio = sum(len(r.audio_streams) for r in results)
    total_subtitle = sum(len(r.subtitle_streams) for r in results)
    total_errors = sum(1 for r in results if r.errors)

    print(f"  视频流: {total_video} | 音频流: {total_audio} | 字幕流: {total_subtitle}")
    if total_errors > 0:
        print(f"  {Fore.YELLOW}有 {total_errors} 个文件探测出错{Style.RESET_ALL}")
