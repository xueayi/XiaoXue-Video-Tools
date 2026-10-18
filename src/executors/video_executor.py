# -*- coding: utf-8 -*-
"""
视频执行器模块：包含视频压制、音频替换、音视频抽取相关执行函数。
"""
import os

from colorama import Fore, Style

from ..core import (
    build_encode_command,
    build_2pass_commands,
    build_replace_audio_command,
    build_extract_audio_command,
    build_extract_video_command,
    run_ffmpeg_command,
    run_2pass_encode,
)
from ..compat_encoder import run_compat_encode
from ..capabilities.container import check_encode_output
from ..presets import (
    ALL_QUALITY_PRESETS as QUALITY_PRESETS,
    AUDIO_ENCODERS,
    ENCODERS,
    RATE_CONTROL_MODES,
    EXTRACT_MODES,
)
from ..utils import generate_output_path, auto_generate_output_path
from ..post_transfer import transfer_file
from ..presets import POST_TRANSFER_MODES
from ..encode_params import (
    EncodeParams,
    EncodeMode,
    resolve_encoder_params,
    print_encode_info,
)
from ..media_probe import probe_detailed
from ..clip_plan import select_audio_indices
from ..clip_validation import validate_clip_frames
from ..task.report import TaskReport
from ..task.result import TaskResult
from .common import print_task_header


def execute_encode(args) -> TaskResult:
    """
    执行视频压制任务。
    
    Args:
        args: argparse 解析后的参数对象
    
    Returns:
        TaskResult: 成功/失败结果 (失败保留 exit_code 与已产出的文件)。
    """
    print_task_header("视频压制")

    # 解析编码参数
    params = resolve_encoder_params(
        args=args,
        quality_presets=QUALITY_PRESETS,
        encoders=ENCODERS,
        audio_encoders=AUDIO_ENCODERS,
        rate_control_modes=RATE_CONTROL_MODES,
        generate_output_path_func=generate_output_path,
    )
    
    # 验证输入参数
    is_valid, error_msg = params.validate()
    if not is_valid:
        print(f"{Fore.RED}[错误] {error_msg}{Style.RESET_ALL}", flush=True)
        return TaskResult.failed(error_msg, details={"reason": "validation"})

    clip_kwargs = {}
    if params.clip_plan is not None:
        info = probe_detailed(params.input_path)
        try:
            if not info or info.errors or not info.video_streams or info.duration_sec <= 0:
                raise ValueError("片段模式无法确定视频时长，请检查文件和 FFprobe")
            params.clip_plan.validate(round(info.clip_duration_sec * 1_000_000))
            validate_clip_frames(params.clip_plan)
            clip_kwargs = dict(clip_plan=params.clip_plan, clip_audio_indices=select_audio_indices(
                params.audio_tracks, params.audio_tracks_custom, len(info.audio_streams)))
        except ValueError as exc:
            return TaskResult.failed(str(exc), details={"reason": "clip_validation"})
    
    # 打印编码信息
    print_encode_info(params, QUALITY_PRESETS)
    
    # 自动生成输出路径提示
    if args.output != params.output_path:
        print(f"[自动生成输出路径] {params.output_path}", flush=True)

    # 输出容器 × 实际编码器预检: 不兼容时不构建/执行命令 (dry_run 同样提前报错)
    output_extension = os.path.splitext(params.output_path)[1]
    container_check = check_encode_output(params.encoder, output_extension)
    if not container_check.ok:
        message = f"输出容器不兼容: {'；'.join(container_check.reasons)}"
        if container_check.suggestions:
            message += f"。建议: {'；'.join(container_check.suggestions)}"
        print(f"{Fore.RED}[错误] {message}{Style.RESET_ALL}", flush=True)
        return TaskResult.failed(
            message,
            details={
                "reason": "container",
                "reasons": container_check.reasons,
                "suggestions": container_check.suggestions,
            },
        )

    # 根据编码模式执行
    mode = params.get_encode_mode()
    
    if mode == EncodeMode.COMPAT:
        # 兼容模式：字幕渲染使用 AviSynth + VSFilter
        return_code = run_compat_encode(
            input_path=params.input_path,
            output_path=params.output_path,
            subtitle_path=params.subtitle_path,
            encoder=params.encoder,
            crf=params.crf,
            bitrate=params.bitrate,
            speed_preset=params.speed_preset,
            resolution=params.resolution,
            fps=params.fps,
            audio_encoder=params.audio_encoder,
            audio_bitrate=params.audio_bitrate,
            extra_args=params.extra_args,
            rc_mode=params.rc_mode,
            dry_run=params.dry_run,
        )
    
    elif mode == EncodeMode.TWO_PASS:
        # 2-Pass 编码模式
        pass1_cmd, pass2_cmd = build_2pass_commands(
            input_path=params.input_path,
            output_path=params.output_path,
            preset_name=params.preset_name,
            # 统一使用 resolve_encoder_params 的最终结果, 不再按 is_custom 二次覆盖
            encoder=params.encoder,
            bitrate=params.bitrate,
            speed_preset=params.speed_preset,
            resolution=params.resolution,
            fps=params.fps,
            audio_encoder=params.audio_encoder,
            audio_bitrate=params.audio_bitrate,
            subtitle_path=params.subtitle_path,
            extra_args=params.extra_args,
            audio_tracks=params.audio_tracks,
            audio_tracks_custom=params.audio_tracks_custom,
            subtitle_tracks=params.subtitle_tracks,
            subtitle_tracks_custom=params.subtitle_tracks_custom,
            **clip_kwargs,
        )
        return_code = run_2pass_encode(pass1_cmd, pass2_cmd, dry_run=params.dry_run)
    
    else:
        # 普通编码模式
        cmd = build_encode_command(
            input_path=params.input_path,
            output_path=params.output_path,
            preset_name=params.preset_name,
            # 统一使用 resolve_encoder_params 的最终结果, 不再按 is_custom 二次覆盖
            encoder=params.encoder,
            crf=params.crf,
            bitrate=params.bitrate,
            speed_preset=params.speed_preset,
            resolution=params.resolution,
            fps=params.fps,
            audio_encoder=params.audio_encoder,
            audio_bitrate=params.audio_bitrate,
            subtitle_path=params.subtitle_path,
            extra_args=params.extra_args,
            rc_mode=params.rc_mode,
            audio_tracks=params.audio_tracks,
            audio_tracks_custom=params.audio_tracks_custom,
            subtitle_tracks=params.subtitle_tracks,
            subtitle_tracks_custom=params.subtitle_tracks_custom,
            **clip_kwargs,
        )
        return_code = run_ffmpeg_command(cmd, dry_run=params.dry_run)
    
    if return_code == 0 and not params.dry_run and params.clip_plan is not None:
        output_info = probe_detailed(params.output_path)
        if not output_info or output_info.errors or not output_info.video_streams:
            return TaskResult.failed("片段导出未生成有效视频流，请检查输入和时间范围",
                                     outputs=(params.output_path,) if os.path.isfile(params.output_path) else (),
                                     details={"reason": "clip_output_validation"})

    # 压制后分发: dry_run 没有真实产物, 不做分发; 分发失败降级为 warnings
    warnings: tuple = ()
    if not params.dry_run:
        warnings = tuple(_post_transfer(args, params.output_path, return_code) or ())

    details = {"mode": mode.value}

    if params.dry_run:
        # 调试模式只打印命令: 状态为 SUCCESS 但不是真实产出, 用 details 标记
        return TaskResult.ok(
            "Debug 模式：仅输出命令，未实际执行",
            warnings=warnings,
            details={**details, "dry_run": True, "exit_code": return_code},
        )

    if return_code == 0:
        return TaskResult.ok(
            outputs=(params.output_path,),
            warnings=warnings,
            details={**details, "exit_code": 0},
        )

    # 失败: 保留已产生的输出文件 (部分容器可能已落盘)
    produced = tuple(
        path for path in (params.output_path,) if os.path.isfile(path)
    )
    return TaskResult.failed(
        f"FFmpeg 退出码 {return_code}",
        exit_code=return_code,
        outputs=produced,
        warnings=warnings,
        details=details,
    )


def _post_transfer(args, output_path: str, return_code: int) -> list:
    """
    压制完成后执行文件分发。
    
    Args:
        args: argparse 解析后的参数对象
        output_path: 成品文件路径
        return_code: 编码返回码 (0 表示成功)
    
    Returns:
        分发失败等警告消息列表 (编码成功但分发失败不改变任务状态)。
    """
    warnings = []
    transfer_mode_name = getattr(args, 'post_transfer_mode', '不分发')
    transfer_mode = POST_TRANSFER_MODES.get(transfer_mode_name, 'none')
    transfer_dir = getattr(args, 'post_transfer_dir', '')

    if transfer_mode == 'none' or not transfer_dir:
        return warnings

    if return_code != 0:
        print(f"{Fore.YELLOW}[分发] 编码未成功，跳过分发{Style.RESET_ALL}")
        return warnings

    if not os.path.isfile(output_path):
        print(f"{Fore.YELLOW}[分发] 输出文件不存在，跳过分发{Style.RESET_ALL}")
        return warnings

    try:
        transfer_file(output_path, transfer_dir, mode=transfer_mode)
    except Exception as e:
        print(f"{Fore.RED}[分发失败] {e}{Style.RESET_ALL}")
        warnings.append(f"分发失败: {e}")
    return warnings


def execute_replace_audio(args) -> TaskResult:
    """
    执行音频替换任务。

    Args:
        args: argparse 解析后的参数对象

    Returns:
        TaskResult: rc 0 -> SUCCESS(outputs=[输出路径])；非 0 -> FAILED(exit_code)。
    """
    print_task_header("音频替换")

    output_path = args.audio_output
    if not output_path:
        output_path = auto_generate_output_path(args.video_input, "_replaced")
        print(f"[自动生成输出路径] {output_path}", flush=True)

    cmd = build_replace_audio_command(
        video_path=args.video_input,
        audio_path=args.audio_input,
        output_path=output_path,
        audio_encoder=AUDIO_ENCODERS.get(args.audio_enc, "aac"),
        audio_bitrate=args.audio_br,
    )

    return_code = run_ffmpeg_command(cmd)
    if return_code == 0:
        return TaskResult.ok(outputs=(output_path,), exit_code=0)
    return TaskResult.failed(
        f"FFmpeg 退出码 {return_code}", exit_code=return_code)


def execute_extract_av(args) -> TaskResult:
    """
    执行音视频抽取任务。

    根据用户选择的抽取模式，分离输出纯音频和/或纯视频。

    Args:
        args: argparse 解析后的参数对象

    Returns:
        TaskResult: 单产物 rc 0 -> SUCCESS；音频+视频模式下单个失败为 PARTIAL，
        全部失败为 FAILED；输出路径写入 outputs。
    """
    print_task_header("音视频抽取")

    # 获取抽取模式
    extract_mode_key = getattr(args, 'extract_mode', '仅音频')
    extract_mode = EXTRACT_MODES.get(extract_mode_key, 'audio_only')

    report = TaskReport()

    # ---- 音频抽取逻辑 ----
    if extract_mode in ("audio_only", "both"):
        print(f"\n{Fore.CYAN}[音频抽取]{Style.RESET_ALL}")

        audio_output = args.extract_output
        if not audio_output:
            # 推断音频扩展名
            encoder_key = args.extract_encoder
            ext = ".m4a"
            if "MP3" in encoder_key:
                ext = ".mp3"
            elif "WAV" in encoder_key:
                ext = ".wav"
            elif "FLAC" in encoder_key:
                ext = ".flac"

            audio_output = auto_generate_output_path(
                args.extract_input, "_extract", ext
            )
            print(f"[自动生成音频输出路径] {audio_output}", flush=True)

        cmd = build_extract_audio_command(
            input_path=args.extract_input,
            output_path=audio_output,
            audio_encoder=AUDIO_ENCODERS.get(args.extract_encoder, "aac"),
            audio_bitrate=args.extract_bitrate,
        )
        return_code = run_ffmpeg_command(cmd)
        if return_code == 0:
            report.add_success(audio_output)
        else:
            report.add_failure(
                f"音频抽取失败 (FFmpeg 退出码 {return_code})",
                exit_code=return_code)

    # ---- 视频抽取逻辑 ----
    if extract_mode in ("video_only", "both"):
        print(f"\n{Fore.CYAN}[视频抽取]{Style.RESET_ALL}")

        video_output = getattr(args, 'extract_video_output', '')
        if not video_output:
            # 保持原视频的容器格式
            input_ext = os.path.splitext(args.extract_input)[1]
            video_output = auto_generate_output_path(
                args.extract_input, "_noaudio", input_ext
            )
            print(f"[自动生成视频输出路径] {video_output}", flush=True)

        cmd = build_extract_video_command(
            input_path=args.extract_input,
            output_path=video_output,
        )
        return_code = run_ffmpeg_command(cmd)
        if return_code == 0:
            report.add_success(video_output)
        else:
            report.add_failure(
                f"视频抽取失败 (FFmpeg 退出码 {return_code})",
                exit_code=return_code)

    return report.finalize()
