# -*- coding: utf-8 -*-
"""
FFmpeg 核心调用模块：构建命令行并执行。
"""
import subprocess
import os
from typing import Optional, List

from colorama import Fore, Style

from .utils import get_ffmpeg_path, escape_path_for_ffmpeg
from .presets import QUALITY_PRESETS, ENCODERS


def build_encode_command(
    input_path: str,
    output_path: str,
    preset_name: Optional[str] = None,
    encoder: Optional[str] = None,
    crf: Optional[int] = None,
    bitrate: Optional[str] = None,
    speed_preset: Optional[str] = None,
    resolution: Optional[str] = None,
    fps: Optional[int] = None,
    audio_encoder: str = "aac",
    audio_bitrate: str = "192k",
    subtitle_path: Optional[str] = None,
    extra_args: Optional[str] = None,
) -> List[str]:
    """
    构建视频编码 FFmpeg 命令。

    Args:
        input_path: 输入视频路径。
        output_path: 输出视频路径。
        preset_name: 预设名称 (来自 QUALITY_PRESETS)。
        encoder: 视频编码器 (覆盖预设)。
        crf: CRF 值 (覆盖预设)。
        bitrate: 视频码率 (覆盖 CRF)。
        speed_preset: 速度预设 (如 medium, p4)。
        resolution: 分辨率 (如 "1920x1080")。
        fps: 帧率。
        audio_encoder: 音频编码器。
        audio_bitrate: 音频码率。
        subtitle_path: 字幕文件路径 (可选，用于烧录)。
        extra_args: 额外的 FFmpeg 参数 (字符串)。

    Returns:
        FFmpeg 命令列表。
    """
    ffmpeg = get_ffmpeg_path()
    cmd = [ffmpeg, "-y", "-i", input_path]

    # 如果使用预设, 加载预设参数
    if preset_name and preset_name in QUALITY_PRESETS and preset_name != "自定义 (Custom)":
        preset = QUALITY_PRESETS[preset_name]
        encoder = encoder or preset.get("encoder")
        crf = crf if crf is not None else preset.get("crf")
        speed_preset = speed_preset or preset.get("preset")
        resolution = resolution or preset.get("resolution")
        fps = fps if fps is not None else preset.get("fps")
        audio_bitrate = audio_bitrate or preset.get("audio_bitrate", "192k")
        # NVENC 使用 cq 而非 crf
        if "cq" in preset and preset["cq"] is not None:
            crf = None  # 禁用 crf

    # 视频滤镜链
    vf_filters = []
    if subtitle_path:
        escaped_sub = escape_path_for_ffmpeg(subtitle_path)
        vf_filters.append(f"subtitles='{escaped_sub}'")
    if resolution:
        w, h = resolution.split("x")
        vf_filters.append(f"scale={w}:{h}")

    if vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])

    # 视频编码器
    actual_encoder = ENCODERS.get(encoder, encoder) if encoder else "libx264"
    cmd.extend(["-c:v", actual_encoder])

    # 编码参数
    if actual_encoder != "copy":
        if bitrate:
            cmd.extend(["-b:v", bitrate])
        elif crf is not None:
            if "nvenc" in actual_encoder:
                cmd.extend(["-cq", str(crf)])
            else:
                cmd.extend(["-crf", str(crf)])

        if speed_preset:
            if "nvenc" in actual_encoder:
                cmd.extend(["-preset", speed_preset])
            else:
                cmd.extend(["-preset", speed_preset])

    # 帧率
    if fps:
        cmd.extend(["-r", str(fps)])

    # 音频
    cmd.extend(["-c:a", audio_encoder])
    if audio_encoder != "copy":
        cmd.extend(["-b:a", audio_bitrate])

    # 额外参数
    if extra_args:
        cmd.extend(extra_args.split())

    cmd.append(output_path)
    return cmd


def build_replace_audio_command(
    video_path: str,
    audio_path: str,
    output_path: str,
    audio_encoder: str = "aac",
    audio_bitrate: str = "192k",
) -> List[str]:
    """
    构建替换音频的 FFmpeg 命令。

    Args:
        video_path: 原始视频路径。
        audio_path: 新音频文件路径。
        output_path: 输出视频路径。
        audio_encoder: 音频编码器。
        audio_bitrate: 音频码率。

    Returns:
        FFmpeg 命令列表。
    """
    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0",  # 取第一个输入的视频流
        "-map", "1:a:0",  # 取第二个输入的音频流
        "-c:v", "copy",   # 视频流直接复制
        "-c:a", audio_encoder,
    ]
    if audio_encoder != "copy":
        cmd.extend(["-b:a", audio_bitrate])
    cmd.append(output_path)
    return cmd


def build_remux_command(input_path: str, output_path: str) -> List[str]:
    """
    构建转封装命令 (不重新编码)。

    Args:
        input_path: 输入文件路径。
        output_path: 输出文件路径 (通过扩展名决定容器)。

    Returns:
        FFmpeg 命令列表。
    """
    ffmpeg = get_ffmpeg_path()
    return [ffmpeg, "-y", "-i", input_path, "-c", "copy", output_path]


def build_extract_audio_command(
    input_path: str,
    output_path: str,
    audio_encoder: str = "aac",
    audio_bitrate: str = "192k",
) -> List[str]:
    """
    构建音频抽取命令。

    Args:
        input_path: 输入视频路径。
        output_path: 输出音频路径 (通过扩展名决定格式)。
        audio_encoder: 音频编码器 ("copy" 表示直接提取)。
        audio_bitrate: 音频码率。

    Returns:
        FFmpeg 命令列表。
    """
    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg, "-y",
        "-i", input_path,
        "-vn",  # 禁用视频
        "-c:a", audio_encoder,
    ]
    if audio_encoder != "copy":
        cmd.extend(["-b:a", audio_bitrate])
    cmd.append(output_path)
    return cmd


def run_ffmpeg_command(cmd: List[str], progress_callback=None) -> int:
    """
    执行 FFmpeg 命令，实时打印输出。

    Args:
        cmd: 命令列表。
        progress_callback: 可选的进度回调函数。

    Returns:
        进程返回码。
    """
    print(f"{Fore.CYAN}[小雪工具箱] 执行命令:{Style.RESET_ALL}", flush=True)
    print(" ".join(cmd), flush=True)
    print("-" * 50, flush=True)

    try:
        # 使用 Popen 以实时读取输出
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,  # 行缓冲
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )

        # 实时读取输出
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                print(line, end='', flush=True)
                if progress_callback:
                    progress_callback(line)

        process.wait()

        if process.returncode == 0:
            print(f"\n{Fore.GREEN}[成功] 任务完成!{Style.RESET_ALL}", flush=True)
        else:
            print(f"\n{Fore.RED}[失败] FFmpeg 返回错误 (code={process.returncode}){Style.RESET_ALL}", flush=True)

        return process.returncode

    except FileNotFoundError as e:
        print(f"\n{Fore.RED}[错误] 找不到 FFmpeg: {e}{Style.RESET_ALL}", flush=True)
        print(f"请确保 bin 目录下有 ffmpeg.exe", flush=True)
        return -1
    except Exception as e:
        print(f"\n{Fore.RED}[错误] 执行失败: {e}{Style.RESET_ALL}", flush=True)
        return -1
