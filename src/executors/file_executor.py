# -*- coding: utf-8 -*-
"""
文件执行器模块：包含封装转换、图片转换相关执行函数。
"""
import os

from colorama import Fore, Style

from ..core import build_remux_command, run_ffmpeg_command
from ..presets import REMUX_PRESETS, IMAGE_FORMATS, AUDIO_TRACK_OPTIONS, SUBTITLE_TRACK_OPTIONS
from ..utils import auto_generate_output_path
from ..image_converter import batch_convert_images
from ..capabilities.container import ContainerCheckResult, check_remux
from ..media_probe import probe_detailed
from ..task.report import TaskReport
from ..task.result import TaskResult
from .common import print_task_header


def _path_key(path) -> str:
    """返回路径比较键：存在时解析真实路径，否则退化为 normcase(abspath)。"""
    try:
        if os.path.exists(path):
            return os.path.normcase(os.path.realpath(path))
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(str(path)))


def _is_same_file(path_a, path_b) -> bool:
    """判断两个路径是否指向同一文件（存在时 samefile 优先，否则归一化比较）。"""
    try:
        if os.path.exists(path_a) and os.path.exists(path_b):
            return os.path.samefile(path_a, path_b)
    except OSError:
        pass
    return _path_key(path_a) == _path_key(path_b)


def _reserve_remux_output(candidate: str, reserved: set) -> str:
    """同批输出路径冲突时追加 _1/_2 后缀，避免同一批任务互相覆盖。"""
    base, ext = os.path.splitext(candidate)
    current = candidate
    index = 0
    while _path_key(current) in reserved:
        index += 1
        current = f"{base}_{index}{ext}"
    return current


def _preflight_remux_container(
    input_path: str, extension: str,
) -> ContainerCheckResult | None:
    """封装转换前的容器预检。

    Returns:
        ContainerCheckResult；返回 None 表示跳过预检（探测异常/探测失败/
        探测结果无有效流），此时继续按原流程处理，避免误伤用户。
    """
    try:
        info = probe_detailed(input_path)
    except Exception:  # noqa: BLE001 - 探测异常不应阻断原流程
        return None
    if info is None or getattr(info, "errors", None):
        # 探测失败（文件损坏/ffprobe 不可用等）：跳过预检，交给 ffmpeg 原流程
        return None
    try:
        return check_remux(info, extension)
    except Exception:  # noqa: BLE001 - 预检自身异常不阻断任务
        return None


def execute_remux(args) -> TaskResult:
    """
    执行封装转换任务（支持批量）。

    覆盖模式只删除 rc==0、输出文件真实存在且与源文件不是同一文件的源文件；
    失败的源绝不删。同批输出路径冲突时自动追加 _1/_2 后缀，避免互相覆盖。

    Args:
        args: argparse 解析后的参数对象

    Returns:
        TaskResult: 全部成功=SUCCESS、全部失败=FAILED、混合=PARTIAL；
        输出路径进 outputs，删除失败/删除跳过进 warnings。
    """
    print_task_header("封装转换")

    preset_name = getattr(args, 'remux_preset', 'MP4')
    preset = REMUX_PRESETS.get(preset_name, {})
    
    if preset_name == "自定义":
        extension = getattr(args, 'remux_format_custom', '')
        if not extension:
            print(f"{Fore.RED}[错误] 选择自定义格式时必须输入自定义后缀名{Style.RESET_ALL}")
            return TaskResult.failed("选择自定义格式时必须输入自定义后缀名")
        if not extension.startswith('.'):
            extension = '.' + extension
    else:
        extension = preset.get("extension", ".mp4")
        
    overwrite = getattr(args, 'remux_overwrite', False)
    
    # 解析流选择参数
    audio_track_key = getattr(args, 'remux_audio_tracks', '全部保留')
    audio_tracks = AUDIO_TRACK_OPTIONS.get(audio_track_key, "all")
    audio_tracks_custom = getattr(args, 'remux_audio_tracks_custom', '')
    
    subtitle_track_key = getattr(args, 'remux_subtitle_tracks', '全部保留')
    subtitle_tracks = SUBTITLE_TRACK_OPTIONS.get(subtitle_track_key, "all")
    subtitle_tracks_custom = getattr(args, 'remux_subtitle_tracks_custom', '')
    
    # 获取输入文件列表
    input_files = args.remux_input
    if isinstance(input_files, str):
        input_files = [input_files]
    
    output_dir = args.remux_output if args.remux_output else None
    
    print(f"[预设] {preset_name}")
    print(f"[输入文件数] {len(input_files)}")
    if output_dir:
        print(f"[输出目录] {output_dir}")
    if audio_tracks != "all":
        if audio_tracks == "custom":
            print(f"[音轨] 自定义选择: #{audio_tracks_custom}")
        elif audio_tracks == "none":
            print(f"[音轨] 不保留")
        else:
            print(f"[音轨] 仅保留 #{audio_tracks}")
    if subtitle_tracks != "all":
        if subtitle_tracks == "custom":
            print(f"[字幕] 自定义选择: #{subtitle_tracks_custom}")
        elif subtitle_tracks == "none":
            print(f"[字幕] 不保留")
        else:
            print(f"[字幕] 仅保留 #{subtitle_tracks}")
    if overwrite:
        print(f"{Fore.YELLOW}[警告] 覆盖模式已开启，原文件将被删除{Style.RESET_ALL}")
    print("-" * 50)

    report = TaskReport()
    deleted_count = 0
    delete_errors = []
    files_to_delete = []  # 成功且输出校验通过后需要删除的原文件
    reserved_outputs = set()  # 本批已占用的输出路径键，防止同批互相覆盖

    for i, input_path in enumerate(input_files, 1):
        print(f"\n[{i}/{len(input_files)}] 处理: {os.path.basename(input_path)}")

        # 容器预检：不兼容时不启动 ffmpeg，直接按文件记失败（源文件保留）
        preflight = _preflight_remux_container(input_path, extension)
        if preflight is not None and not preflight.ok:
            reasons = "；".join(preflight.reasons)
            message = f"容器不兼容，未执行转换: {reasons}"
            if preflight.suggestions:
                message += f"。建议: {'；'.join(preflight.suggestions)}"
            print(
                f"{Fore.RED}[跳过] {os.path.basename(input_path)}: "
                f"{message}{Style.RESET_ALL}"
            )
            report.add_failure(f"{os.path.basename(input_path)}: {message}")
            continue

        # 生成输出路径（同批输出冲突时追加 _1/_2 后缀）
        if output_dir:
            basename = os.path.splitext(os.path.basename(input_path))[0]
            candidate = os.path.join(output_dir, basename + "_remux" + extension)
        else:
            candidate = auto_generate_output_path(input_path, "_remux", extension)
        output_path = _reserve_remux_output(candidate, reserved_outputs)
        reserved_outputs.add(_path_key(output_path))

        print(f"[输出] {output_path}")

        cmd = build_remux_command(
            input_path=input_path,
            output_path=output_path,
            audio_tracks=audio_tracks,
            audio_tracks_custom=audio_tracks_custom,
            subtitle_tracks=subtitle_tracks,
            subtitle_tracks_custom=subtitle_tracks_custom,
        )

        return_code = run_ffmpeg_command(cmd)
        if return_code == 0:
            report.add_success(output_path)
            # 删除门槛：rc==0 且输出文件真实存在且与源文件不是同一文件；
            # 任何不确定都保留源文件（就低不就高），失败的源绝不删。
            if overwrite:
                if not os.path.isfile(output_path):
                    message = (
                        f"输出文件不存在，保留源文件: "
                        f"{os.path.basename(input_path)}"
                    )
                    print(f"{Fore.YELLOW}[警告] {message}{Style.RESET_ALL}")
                    report.warn(message)
                elif _is_same_file(input_path, output_path):
                    message = (
                        f"输出与源文件为同一文件，保留源文件: "
                        f"{os.path.basename(input_path)}"
                    )
                    print(f"{Fore.YELLOW}[警告] {message}{Style.RESET_ALL}")
                    report.warn(message)
                else:
                    files_to_delete.append(input_path)
        else:
            report.add_failure(
                f"{os.path.basename(input_path)}: FFmpeg 退出码 {return_code}",
                exit_code=return_code)

    # 覆盖模式：删除校验通过的原文件（删除失败逐条收集，不中断）
    if overwrite and files_to_delete:
        print(f"\n{Fore.YELLOW}[覆盖模式] 删除 {len(files_to_delete)} 个原文件...{Style.RESET_ALL}")
        deleted_keys = set()
        for f in files_to_delete:
            key = _path_key(f)
            if key in deleted_keys:
                continue
            try:
                os.remove(f)
            except OSError as e:
                message = f"删除失败: {os.path.basename(f)} - {e}"
                delete_errors.append(message)
                report.warn(message)
                print(f"  ✗ {message}")
            else:
                deleted_keys.add(key)
                deleted_count += 1
                print(f"  ✓ 已删除: {os.path.basename(f)}")

    print(f"\n{'='*50}")
    summary = f"批量转换完成: 成功 {report.success_count} 个, 失败 {report.failure_count} 个"
    if overwrite:
        summary += f", 已删除 {deleted_count} 个原文件"
        if delete_errors:
            summary += f", 删除失败 {len(delete_errors)} 个"
    print(summary)

    if delete_errors:
        print(f"{Fore.YELLOW}[警告] {len(delete_errors)} 个原文件删除失败（源文件已保留，请手动处理）{Style.RESET_ALL}")

    report.details.update({
        "deleted_count": deleted_count,
        "delete_errors": tuple(delete_errors),
    })
    return report.finalize()


def execute_image_convert(args) -> TaskResult:
    """
    执行图片格式转换任务。

    覆盖模式只删除转换成功、输出文件存在且与源文件不是同一文件的源文件；
    跳过/失败/输出缺失的源文件一律保留。删除失败逐条收集且不中断。

    Args:
        args: argparse 解析后的参数对象

    Returns:
        TaskResult: 全部成功=SUCCESS、全部失败=FAILED、混合=PARTIAL；
        输出路径进 outputs，跳过/删除失败/删除跳过进 warnings，
        逐文件明细保留在 details["results"]。
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
            return TaskResult.failed("选择自定义格式时必须输入扩展名")
    else:
        target_ext = IMAGE_FORMATS.get(format_preset, ".png")

    # 确保扩展名格式正确
    if target_ext and not target_ext.startswith("."):
        target_ext = "." + target_ext

    output_dir = args.img_output_dir if args.img_output_dir else None
    quality = getattr(args, 'img_quality', 95)
    overwrite = getattr(args, 'img_overwrite', False)
    skip_same = getattr(args, 'img_skip_same_format', True)

    print(f"[目标格式] {target_ext}")
    print(f"[质量] {quality}")
    print(f"[文件数量] {len(input_files)}")
    if overwrite:
        print(f"{Fore.YELLOW}[警告] 覆盖模式已开启，原文件将被删除{Style.RESET_ALL}")

    results = batch_convert_images(
        input_paths=input_files,
        output_dir=output_dir,
        target_extension=target_ext,
        quality=quality,
        skip_same_format=skip_same,
    )

    success_count = sum(1 for r in results if r.status == "success")
    fail_count = sum(1 for r in results if r.status == "failed")
    skip_count = sum(1 for r in results if r.status == "skipped")

    report = TaskReport()
    for r in results:
        if r.status == "success":
            report.add_success(str(r.output) if r.output is not None else None)
        elif r.status == "failed":
            report.add_failure(
                f"{os.path.basename(str(r.source))}: {r.error or '转换失败'}")
    if skip_count > 0:
        report.warn(f"{skip_count} 个文件已是目标格式，已跳过转换")

    # 覆盖模式：只删除“转换成功 + 输出存在 + 非同一文件”的源文件
    deleted_count = 0
    delete_errors = []
    if overwrite:
        # 成功但输出不存在/与源同文件 -> 无法安全删除，计入 warnings
        for r in results:
            if r.status == "success" and not r.can_delete_source():
                report.warn(
                    f"未删除源文件（输出不存在或与源同文件）: "
                    f"{os.path.basename(str(r.source))}")

        deletable = [r for r in results if r.can_delete_source()]
        if deletable:
            print(f"\n{Fore.YELLOW}[覆盖模式] 删除转换成功的原文件...{Style.RESET_ALL}")
            deleted_keys = set()
            for r in deletable:
                source = str(r.source)
                key = _path_key(source)
                if key in deleted_keys:
                    continue
                try:
                    os.remove(source)
                except OSError as e:
                    message = f"删除失败: {os.path.basename(source)} - {e}"
                    delete_errors.append(message)
                    report.warn(message)
                    print(f"  ✗ {message}")
                else:
                    deleted_keys.add(key)
                    deleted_count += 1
                    print(f"  ✓ 已删除: {os.path.basename(source)}")
            if deleted_count > 0:
                print(f"  ✓ 已删除 {deleted_count} 个原文件")
        else:
            print(
                f"\n{Fore.YELLOW}[覆盖模式] 没有可安全删除的原文件，"
                f"跳过/失败/输出缺失的源文件已全部保留{Style.RESET_ALL}"
            )

    print(f"\n{'='*50}")
    summary_parts = [f"成功 {success_count} 个", f"失败 {fail_count} 个"]
    if skip_count > 0:
        summary_parts.append(f"跳过 {skip_count} 个")
    if overwrite:
        summary_parts.append(f"已删除 {deleted_count} 个原文件")
    if delete_errors:
        summary_parts.append(f"删除失败 {len(delete_errors)} 个")
    print(f"图片转换完成: {', '.join(summary_parts)}")

    if delete_errors:
        print(f"\n{Fore.YELLOW}[警告] {len(delete_errors)} 个原文件删除失败（源文件已保留，请手动处理）:{Style.RESET_ALL}")
        for err in delete_errors[:5]:
            print(f"  - {err}")

    failed = [r for r in results if r.status == "failed" and r.error]
    if failed:
        print(f"\n{Fore.YELLOW}[警告] 部分转换失败:{Style.RESET_ALL}")
        for r in failed[:5]:
            print(f"  - {os.path.basename(str(r.source))}: {r.error}")

    report.details.update({
        "results": tuple(results),
        "skip_count": skip_count,
        "deleted_count": deleted_count,
        "delete_errors": tuple(delete_errors),
    })
    task_result = report.finalize()
    if (report.success_count == 0 and report.failure_count == 0
            and skip_count > 0):
        # 全部跳过（已是目标格式）不是失败：没有需要转换的文件但输入有效
        task_result = TaskResult.ok(
            f"跳过 {skip_count} 个（已是目标格式）",
            warnings=report.warnings,
            details=task_result.details,
        )
    return task_result
