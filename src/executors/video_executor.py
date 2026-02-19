# -*- coding: utf-8 -*-
"""
视频执行器模块：包含视频压制、音频替换、音频抽取相关执行函数。
"""
import os

from colorama import Fore, Style

from ..core import (
    build_encode_command,
    build_2pass_commands,
    build_replace_audio_command,
    build_extract_audio_command,
    run_ffmpeg_command,
    run_2pass_encode,
)
from ..compat_encoder import run_compat_encode
from ..presets import (
    QUALITY_PRESETS,
    AUDIO_ENCODERS,
    ENCODERS,
    RATE_CONTROL_MODES,
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
from .common import print_task_header


def execute_encode(args) -> int:
    """
    执行视频压制任务。
    
    Args:
        args: argparse 解析后的参数对象
    
    Returns:
        返回码 (0 表示成功)
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
        return 1
    
    # 打印编码信息
    print_encode_info(params, QUALITY_PRESETS)
    
    # 自动生成输出路径提示
    if args.output != params.output_path:
        print(f"[自动生成输出路径] {params.output_path}", flush=True)
    
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
            encoder=args.encoder if params.is_custom else None,
            bitrate=params.bitrate,
            speed_preset=params.speed_preset,
            resolution=params.resolution,
            fps=params.fps,
            audio_encoder=params.audio_encoder if params.is_custom else "aac",
            audio_bitrate=params.audio_bitrate if params.is_custom else None,
            subtitle_path=params.subtitle_path,
            extra_args=params.extra_args,
        )
        return_code = run_2pass_encode(pass1_cmd, pass2_cmd, dry_run=params.dry_run)
    
    else:
        # 普通编码模式
        cmd = build_encode_command(
            input_path=params.input_path,
            output_path=params.output_path,
            preset_name=params.preset_name,
            encoder=args.encoder if params.is_custom else None,
            crf=params.crf if params.is_custom else None,
            bitrate=params.bitrate,
            speed_preset=params.speed_preset,
            resolution=params.resolution,
            fps=params.fps,
            audio_encoder=params.audio_encoder if params.is_custom else "aac",
            audio_bitrate=params.audio_bitrate if params.is_custom else None,
            subtitle_path=params.subtitle_path,
            extra_args=params.extra_args,
            rc_mode=params.rc_mode,
        )
        return_code = run_ffmpeg_command(cmd, dry_run=params.dry_run)
    
    # 压制后分发
    _post_transfer(args, params.output_path, return_code)
    
    return return_code


def _post_transfer(args, output_path: str, return_code: int) -> None:
    """
    压制完成后执行文件分发。
    
    Args:
        args: argparse 解析后的参数对象
        output_path: 成品文件路径
        return_code: 编码返回码 (0 表示成功)
    """
    transfer_mode_name = getattr(args, 'post_transfer_mode', '不分发')
    transfer_mode = POST_TRANSFER_MODES.get(transfer_mode_name, 'none')
    transfer_dir = getattr(args, 'post_transfer_dir', '')

    if transfer_mode == 'none' or not transfer_dir:
        return

    if return_code != 0:
        print(f"{Fore.YELLOW}[分发] 编码未成功，跳过分发{Style.RESET_ALL}")
        return

    if not os.path.isfile(output_path):
        print(f"{Fore.YELLOW}[分发] 输出文件不存在，跳过分发{Style.RESET_ALL}")
        return

    try:
        transfer_file(output_path, transfer_dir, mode=transfer_mode)
    except Exception as e:
        print(f"{Fore.RED}[分发失败] {e}{Style.RESET_ALL}")


def execute_replace_audio(args):
    """
    执行音频替换任务。
    
    Args:
        args: argparse 解析后的参数对象
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

    run_ffmpeg_command(cmd)


def execute_extract_audio(args):
    """
    执行音频抽取任务。
    
    Args:
        args: argparse 解析后的参数对象
    """
    print_task_header("音频抽取")

    output_path = args.extract_output
    if not output_path:
        # 简单推断扩展名
        encoder_key = args.extract_encoder
        ext = ".m4a"
        if "MP3" in encoder_key:
            ext = ".mp3"
        elif "WAV" in encoder_key:
            ext = ".wav"
        elif "FLAC" in encoder_key:
            ext = ".flac"
        
        output_path = auto_generate_output_path(args.extract_input, "_extract", ext)
        print(f"[自动生成输出路径] {output_path}", flush=True)

    cmd = build_extract_audio_command(
        input_path=args.extract_input,
        output_path=output_path,
        audio_encoder=AUDIO_ENCODERS.get(args.extract_encoder, "aac"),
        audio_bitrate=args.extract_bitrate,
    )

    run_ffmpeg_command(cmd)
