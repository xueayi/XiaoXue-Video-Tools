# -*- coding: utf-8 -*-
"""
FFmpeg 核心调用模块：构建命令行并执行。
"""
import os
import tempfile
from typing import Optional, List, Tuple

from colorama import Fore, Style

from .utils import get_ffmpeg_path, escape_path_for_ffmpeg
from .presets import ALL_QUALITY_PRESETS as QUALITY_PRESETS, ENCODERS
from .capabilities.encoder import encoder_definition as encoder_capability, plan_rate_control
from .process import (
    CompletedProcess,
    ExecutableMissingError,
    inject_progress,
    resolve_runner,
    run as run_process,
)
from .task.context import TaskCancelled, current_task
from .clip_plan import ClipPlan, build_clip_filters, clip_extra_args

# 初始化 Logger
import logging
logger = logging.getLogger(__name__)


def _build_stream_map_args(
    stream_type: str,
    track_option: str,
    custom_indices: str = "",
) -> List[str]:
    """
    根据用户选择生成 -map 参数。

    Args:
        stream_type: 流类型 ("a"=音频, "s"=字幕)
        track_option: 选择模式 ("all"=全部, "none"=不保留, "custom"=自定义, 数字=单条快捷)
        custom_indices: 自定义模式下的编号字符串 (如 "0,2,3")

    Returns:
        FFmpeg 参数列表
    """
    args = []

    if track_option == "none":
        # 不保留: 音频用 -an，字幕用 -sn
        if stream_type == "a":
            args.append("-an")
        else:
            args.append("-sn")

    elif track_option == "all":
        # 全部保留
        args.extend(["-map", f"0:{stream_type}?"])

    elif track_option == "custom" and custom_indices.strip():
        # 自定义模式: 按编号精确选择
        indices = [idx.strip() for idx in custom_indices.split(",") if idx.strip().isdigit()]
        for idx in indices:
            args.extend(["-map", f"0:{stream_type}:{idx}?"])

    else:
        # 单条快捷模式 (track_option 是数字字符串，如 "0")
        if track_option.isdigit():
            args.extend(["-map", f"0:{stream_type}:{track_option}?"])
        else:
            # 兜底: 保留全部
            args.extend(["-map", f"0:{stream_type}?"])

    return args


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
    rc_mode: Optional[str] = None,
    audio_tracks: str = "0",
    audio_tracks_custom: str = "",
    subtitle_tracks: str = "none",
    subtitle_tracks_custom: str = "",
    clip_plan: Optional[ClipPlan] = None,
    clip_audio_indices: tuple[int, ...] = (),
    clip_video_only: bool = False,
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
        rc_mode: NVENC 码率控制模式 (如 constqp, vbr, cbr)。
        audio_tracks: 音轨选择模式 ("all"/"none"/"custom"/数字)。
        audio_tracks_custom: 自定义音轨编号 (逗号分隔，如 "0,2")。
        subtitle_tracks: 字幕选择模式 ("all"/"none"/"custom"/数字)。
        subtitle_tracks_custom: 自定义字幕编号 (逗号分隔)。

    Returns:
        FFmpeg 命令列表。
    """
    ffmpeg = get_ffmpeg_path()
    cmd = [ffmpeg, "-y", "-i", input_path]

    if clip_plan is None:
        cmd.extend(["-map", "0:v:0"])
        cmd.extend(_build_stream_map_args("a", audio_tracks, audio_tracks_custom))
        cmd.extend(_build_stream_map_args("s", subtitle_tracks, subtitle_tracks_custom))

    # 如果使用预设, 加载预设参数
    if preset_name and preset_name in QUALITY_PRESETS and preset_name != "自定义 (Custom)":
        preset = QUALITY_PRESETS[preset_name]
        encoder = encoder or preset.get("encoder")
        
        # 修复: 正确读取 cq 值 (如果预设中有 cq，则覆盖 crf)
        if "cq" in preset and preset["cq"] is not None:
            crf = preset["cq"]
        else:
            crf = crf if crf is not None else preset.get("crf")
            
        speed_preset = speed_preset or preset.get("preset")
        resolution = resolution or preset.get("resolution")
        fps = fps if fps is not None else preset.get("fps")
        audio_bitrate = audio_bitrate or preset.get("audio_bitrate", "192k")
        
        # 支持预设中的额外参数
        if preset.get("extra_args"):
            preset_extra = preset.get("extra_args")
            if extra_args:
                extra_args = f"{preset_extra} {extra_args}"
            else:
                extra_args = preset_extra

    # 视频滤镜链
    vf_filters = []
    if subtitle_path:
        escaped_sub = escape_path_for_ffmpeg(subtitle_path)
        vf_filters.append(f"subtitles='{escaped_sub}'")
    if resolution and isinstance(resolution, str) and "x" in resolution:
        w, h = resolution.split("x")
        vf_filters.append(f"scale={w}:{h}")

    if clip_plan is not None:
        graph, maps = build_clip_filters(clip_plan, vf_filters, clip_audio_indices, clip_video_only)
        cmd.extend(["-filter_complex", graph] + maps)
        if audio_encoder == "copy":
            audio_encoder = "aac"
    elif vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])

    # 视频编码器
    actual_encoder = ENCODERS.get(encoder, encoder) if encoder else "libx264"
    cmd.extend(["-c:v", actual_encoder])

    # 编码参数 - 根据编码器类型自动适配
    if actual_encoder != "copy":
        # 识别编码器类型 (预设模式的恒定质量分支仍按家族选择参数名)
        is_nvenc = "nvenc" in actual_encoder
        is_qsv = "qsv" in actual_encoder
        is_amf = "amf" in actual_encoder

        capability = encoder_capability(actual_encoder)
        speed_flag = capability.speed_flag if capability is not None else "-preset"

        if rc_mode:
            # M3.2: 自定义模式走能力模型的真实 RC 映射
            # (硬件不再写 -2pass 假两遍; 不支持时回退到自身 VBR/多遍模式)
            plan = plan_rate_control(
                capability, rc_mode, crf=crf, bitrate=bitrate)
            cmd.extend(plan.args)
            if plan.effective_mode != rc_mode and plan.note:
                print(f"{Fore.YELLOW}[提示] {plan.note}{Style.RESET_ALL}",
                      flush=True)
        else:
            # 预设模式: 保持既有 CRF/CQ 行为, 避免破坏预设命令快照
            if bitrate:
                # 如果指定了码率，优先使用码率
                cmd.extend(["-b:v", bitrate])
            elif crf is not None:
                # 根据编码器类型选择正确的参数
                if is_nvenc:
                    cmd.extend(["-cq", str(crf)])
                elif is_qsv:
                    cmd.extend(["-global_quality", str(crf)])
                elif is_amf:
                    # AMF 使用 qp_i/qp_p
                    cmd.extend(["-qp_i", str(crf), "-qp_p", str(crf)])
                else:
                    flag = capability.quality_flag if capability is not None else "-crf"
                    cmd.extend([flag, str(crf)])

        # 速度预设 (AMF 使用 -quality speed/balanced/quality, 其余 -preset)
        if speed_preset:
            cmd.extend([speed_flag, speed_preset])

    # 帧率
    if fps:
        cmd.extend(["-r", str(fps)])

    # 音频编码 (仅在保留音轨时添加)
    if audio_tracks != "none" and "-an" not in cmd:
        cmd.extend(["-c:a", audio_encoder])
        if audio_encoder != "copy":
            cmd.extend(["-b:a", audio_bitrate])

    # 字幕编码 (内封字幕直接复制)
    if subtitle_tracks != "none" and "-sn" not in cmd:
        cmd.extend(["-c:s", "copy"])

    # 额外参数
    if extra_args:
        cmd.extend(clip_extra_args(extra_args) if clip_plan is not None else extra_args.split())

    cmd.append(output_path)
    # M2.4: 结构化进度写入 stdout (-progress pipe:1), 供 UI 解析 percent/ETA
    return inject_progress(cmd)


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
    return inject_progress(cmd)


def build_remux_command(
    input_path: str,
    output_path: str,
    audio_tracks: str = "all",
    audio_tracks_custom: str = "",
    subtitle_tracks: str = "all",
    subtitle_tracks_custom: str = "",
) -> List[str]:
    """
    构建转封装命令 (不重新编码)。

    Args:
        input_path: 输入文件路径。
        output_path: 输出文件路径 (通过扩展名决定容器)。
        audio_tracks: 音轨选择模式。
        audio_tracks_custom: 自定义音轨编号。
        subtitle_tracks: 字幕选择模式。
        subtitle_tracks_custom: 自定义字幕编号。

    Returns:
        FFmpeg 命令列表。
    """
    ffmpeg = get_ffmpeg_path()
    cmd = [ffmpeg, "-y", "-i", input_path]

    # 映射视频流 (全部)
    cmd.extend(["-map", "0:v"])

    # 映射音频流
    audio_map_args = _build_stream_map_args("a", audio_tracks, audio_tracks_custom)
    cmd.extend(audio_map_args)

    # 映射字幕流
    subtitle_map_args = _build_stream_map_args("s", subtitle_tracks, subtitle_tracks_custom)
    cmd.extend(subtitle_map_args)

    cmd.extend(["-c", "copy"])
    cmd.append(output_path)
    return inject_progress(cmd)


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
    return inject_progress(cmd)


def build_extract_video_command(
    input_path: str,
    output_path: str,
) -> List[str]:
    """
    构建纯视频提取命令（剥离音频流）。

    Args:
        input_path: 输入视频路径。
        output_path: 输出视频路径 (通过扩展名决定容器)。

    Returns:
        FFmpeg 命令列表。
    """
    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg, "-y",
        "-i", input_path,
        "-an",          # 剥离音频流
        "-c:v", "copy",  # 视频流直接复制
    ]
    cmd.append(output_path)
    return inject_progress(cmd)


def run_ffmpeg_streaming(
    cmd: List[str],
    *,
    on_line=None,
    on_progress=None,
    on_log=None,
    env=None,
    timeout=None,
) -> CompletedProcess:
    """
    经当前 TaskContext 的 ProcessRunner 执行外部命令（流式回调 + 可取消）。

    - 有活动 TaskContext 时使用其注入的 runner（GUI=QProcess / 测试=fake），
      并把 runner 注册到 TaskContext，使 UI 取消能真正终止子进程；
    - 无 TaskContext（CLI / 单元测试）时退回 SubprocessRunner；
    - 被取消时抛 TaskCancelled，由 executor / TaskRunner 映射为 CANCELLED。

    M2.4 起输出分两条通道：
        * **progress**：stdout 行（ffmpeg ``-progress pipe:1`` 的 ``key=value``）；
          显式 ``on_progress`` 优先，否则使用 ``TaskContext.progress_callback``
          （由 TaskRunner 接到 UI 解析器）；
        * **log**：stderr 行（日志/错误），经 ``on_log`` 回调；
        * 兼容参数 ``on_line``：仍会收到 stdout+stderr 每一行（旧调用方行为）。

    M2.5 起 stderr 行同时写入 ``TaskContext`` 的环形缓冲（最近 200 行），
    失败时由 TaskRunner 补齐到 ``TaskResult.details["stderr_tail"]``，
    供 :mod:`src.ffmpeg.errors` 做用户可读错误归类。

    Args:
        cmd: 命令列表。
        on_line: 兼容回调，接收 stdout/stderr 全部行。
        on_progress: 进度回调，仅 stdout 行；None 时回退到 TaskContext。
        on_log: 日志回调，仅 stderr 行。
        env: 可选的环境变量字典。

    Returns:
        CompletedProcess（exit_code / cancelled / stderr_tail 等）。
    """
    context = current_task()
    if context is not None:
        context.raise_if_cancelled()
    runner = resolve_runner(context)

    progress_cb = on_progress
    if progress_cb is None and context is not None:
        progress_cb = getattr(context, "progress_callback", None)

    def _stdout(line: str) -> None:
        if progress_cb is not None:
            progress_cb(line)
        if on_line is not None:
            on_line(line)

    def _stderr(line: str) -> None:
        # M2.5: 记录最近 stderr 行到任务上下文, 失败时供错误分类归因
        if context is not None:
            context.append_stderr(line)
        if on_log is not None:
            on_log(line)
        if on_line is not None:
            on_line(line)

    if progress_cb is not None or on_line is not None:
        runner.on_stdout = _stdout
    if on_log is not None or on_line is not None:
        runner.on_stderr = _stderr
    if context is not None:
        context.register(runner)
    try:
        completed = run_process(
            cmd, runner=runner, stdin_pipe=True, env=env,
            **({"timeout": timeout} if timeout is not None else {}))
    finally:
        if context is not None:
            context.unregister(runner)
    if (context is not None and not context.stderr_lines
            and completed.stderr_tail):
        # 兜底: 没有 on_stderr 回调时从 CompletedProcess 补齐最近 stderr
        context.extend_stderr(completed.stderr_tail)
    if completed.cancelled:
        raise TaskCancelled("任务已取消")
    return completed


def run_ffmpeg_command(cmd: List[str], progress_callback=None, dry_run: bool = False) -> int:
    """
    执行 FFmpeg 命令，实时打印日志（stderr），进度走独立通道。

    内部经 :class:`~src.process.ProcessRunner` 执行（支持 UI 取消），
    对外保持「返回进程退出码」的既有契约。

    M2.4 起 stdout 是 ``-progress`` 的 ``key=value`` 进度流：只送入进度回调，
    **不再打印到日志**；stderr 仍是日志/错误，逐行打印并用于错误归因。

    Args:
        cmd: 命令列表。
        progress_callback: 可选的进度回调（仅 stdout 进度行）。为 None 时
            GUI 场景由 ``TaskContext.progress_callback`` 接收。
        dry_run: 若为 True，仅打印命令，不执行。

    Returns:
        进程返回码（启动失败/可执行文件缺失返回 -1）。
    """
    cmd_str = " ".join(cmd)
    
    # 记录到日志文件
    logger.info(f"Executing command: {cmd_str}")
    
    print(f"{Fore.CYAN}[小雪工具箱] 执行命令:{Style.RESET_ALL}", flush=True)
    print(cmd_str, flush=True)
    print("-" * 50, flush=True)

    if dry_run:
        print(f"{Fore.YELLOW}[Debug 模式] 仅输出命令，不执行。{Style.RESET_ALL}", flush=True)
        return 0

    # 收集输出用于错误分析
    output_lines = []

    def _on_log(line: str) -> None:
        """日志通道：仅 stderr（避免 key=value 进度行刷屏）。"""
        if not line:
            return
        data = line if line.endswith("\n") else line + "\n"
        print(data, end="", flush=True)
        output_lines.append(data)

    try:
        completed = run_ffmpeg_streaming(
            cmd, on_progress=progress_callback, on_log=_on_log)
    except TaskCancelled:
        raise  # 取消必须向上传播, 由 TaskRunner 映射为 CANCELLED
    except ExecutableMissingError as e:
        print(f"\n{Fore.RED}[错误] 找不到 FFmpeg: {e}{Style.RESET_ALL}", flush=True)
        print(f"请确保 bin 目录下有 ffmpeg.exe", flush=True)
        return -1
    except Exception as e:
        print(f"\n{Fore.RED}[错误] 执行失败: {e}{Style.RESET_ALL}", flush=True)
        return -1

    if completed.cancelled:
        # 防御: 正常路径由 run_ffmpeg_streaming 抛 TaskCancelled, 这里再兜底一次
        raise TaskCancelled("任务已取消")

    return_code = completed.exit_code if completed.exit_code is not None else -1
    if return_code == 0:
        print(f"\n{Fore.GREEN}[成功] 任务完成!{Style.RESET_ALL}", flush=True)
    else:
        print(f"\n{Fore.RED}[失败] FFmpeg 返回错误 (code={return_code}){Style.RESET_ALL}", flush=True)
        # 检测硬件编码器错误并给出友好提示
        _check_hardware_encoder_error(output_lines)

    return return_code


def _check_hardware_encoder_error(output_lines: List[str]) -> None:
    """
    检测硬件编码器错误并输出友好提示。

    Args:
        output_lines: FFmpeg 输出行列表。
    """
    output_text = "\n".join(output_lines)
    
    # NVENC 错误关键词
    nvenc_errors = [
        "No NVENC capable devices found",
        "Cannot load cuvidparser",
        "Driver does not support the required nvenc API version",
        "The minimum required Nvidia driver for nvenc",
        "nvenc encoder error",
        "Failed to init NVENC",
    ]
    
    # QSV 错误关键词  
    qsv_errors = [
        "Error initializing an MFX session",
        "device failed",
        "MFXInit failed",
        "Could not initialize mfx session",
        "QSV is not supported",
    ]
    
    # AMF 错误关键词
    amf_errors = [
        "CreateComponent failed",
        "AMF failed",
        "amf encoder error",
        "Failed to create AMF",
        "AMFComponentOptimizedPush_QueryMHESupport",
    ]
    
    detected_encoder = None
    
    for keyword in nvenc_errors:
        if keyword.lower() in output_text.lower():
            detected_encoder = "nvenc"
            break
    
    if not detected_encoder:
        for keyword in qsv_errors:
            if keyword.lower() in output_text.lower():
                detected_encoder = "qsv"
                break
    
    if not detected_encoder:
        for keyword in amf_errors:
            if keyword.lower() in output_text.lower():
                detected_encoder = "amf"
                break
    
    if detected_encoder:
        print(f"\n{Fore.YELLOW}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[提示] 检测到硬件编码器错误{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}{'='*60}{Style.RESET_ALL}")
        
        if detected_encoder == "nvenc":
            print(f"""
{Fore.CYAN}NVIDIA NVENC 编码失败可能的原因:{Style.RESET_ALL}
  • 显卡驱动版本过低，请更新至最新版本
  • 您的 GPU 不支持 NVENC (需 GTX 600 系列或更新)
  • 驱动版本与 FFmpeg 要求不匹配 (建议驱动版本 ≥ 570.0)

{Fore.GREEN}解决建议:{Style.RESET_ALL}
  1. 访问 NVIDIA 官网下载最新驱动: https://www.nvidia.cn/drivers/
  2. 若无法更新驱动，可改用 CPU 编码器 (H.264/H.265)
""")
        elif detected_encoder == "qsv":
            print(f"""
{Fore.CYAN}Intel QSV 编码失败可能的原因:{Style.RESET_ALL}
  • 未安装 Intel 核显驱动
  • CPU 不带集成显卡或已在 BIOS 中禁用
  • 驱动版本过低

{Fore.GREEN}解决建议:{Style.RESET_ALL}
  1. 下载 Intel 核显驱动: https://www.intel.cn/content/www/cn/zh/download-center/home.html
  2. 确认 BIOS 中核显未被禁用
  3. 若无法使用 QSV，可改用 CPU 编码器 (H.264/H.265)
""")
        elif detected_encoder == "amf":
            print(f"""
{Fore.CYAN}AMD AMF 编码失败可能的原因:{Style.RESET_ALL}
  • AMD 显卡驱动版本过低
  • 显卡不支持 AMF 硬件编码
  • 驱动安装不完整

{Fore.GREEN}解决建议:{Style.RESET_ALL}
  1. 下载最新 AMD 驱动: https://www.amd.com/zh-hans/support
  2. 若无法更新驱动，可改用 CPU 编码器 (H.264/H.265)
""")


def build_2pass_commands(
    input_path: str,
    output_path: str,
    preset_name: Optional[str] = None,
    encoder: Optional[str] = None,
    bitrate: str = "10M",
    speed_preset: Optional[str] = None,
    resolution: Optional[str] = None,
    fps: Optional[int] = None,
    audio_encoder: str = "aac",
    audio_bitrate: str = "192k",
    subtitle_path: Optional[str] = None,
    extra_args: Optional[str] = None,
    audio_tracks: str = "0",
    audio_tracks_custom: str = "",
    subtitle_tracks: str = "none",
    subtitle_tracks_custom: str = "",
    clip_plan: Optional[ClipPlan] = None,
    clip_audio_indices: tuple[int, ...] = (),
) -> Tuple[List[str], List[str]]:
    """
    构建真正的两遍编码 FFmpeg 命令。

    Args:
        input_path: 输入视频路径。
        output_path: 输出视频路径。
        preset_name: 预设名称。
        encoder: 视频编码器。
        bitrate: 目标码率 (如 "10M")。
        speed_preset: 速度预设。
        resolution: 分辨率。
        fps: 帧率。
        audio_encoder: 音频编码器。
        audio_bitrate: 音频码率。
        subtitle_path: 字幕文件路径。
        extra_args: 额外参数。

    Returns:
        (pass1_cmd, pass2_cmd) 两遍编码的命令列表。
    """
    if clip_plan is not None:
        common = dict(input_path=input_path, output_path=output_path, preset_name=preset_name,
                      encoder=encoder, bitrate=bitrate, speed_preset=speed_preset,
                      resolution=resolution, fps=fps, audio_encoder=audio_encoder,
                      audio_bitrate=audio_bitrate, subtitle_path=subtitle_path,
                      extra_args=extra_args, clip_plan=clip_plan)
        first = build_encode_command(**common, clip_audio_indices=clip_audio_indices,
                                     audio_tracks="none", clip_video_only=True)
        second = build_encode_command(**common, clip_audio_indices=clip_audio_indices)
        # 两遍使用同一音视频拼接时间线；第一遍音频接入空滤镜，不输出音轨。
        first = first[:-1] + ["-pass", "1", "-f", "null", "NUL" if os.name == "nt" else "/dev/null"]
        second = second[:-1] + ["-pass", "2"] + second[-1:]
        for flag, size in (("-progress", 2), ("-nostats", 1), ("-stats_period", 2)):
            if flag in first:
                index = first.index(flag)
                del first[index:index + size]
        return first, second

    ffmpeg = get_ffmpeg_path()

    # 如果使用预设, 加载预设参数
    if preset_name and preset_name in QUALITY_PRESETS and preset_name != "自定义 (Custom)":
        preset = QUALITY_PRESETS[preset_name]
        encoder = encoder or preset.get("encoder")
        speed_preset = speed_preset or preset.get("preset")
        resolution = resolution or preset.get("resolution")
        fps = fps if fps is not None else preset.get("fps")
        audio_bitrate = audio_bitrate or preset.get("audio_bitrate", "192k")

    # 确定实际编码器
    actual_encoder = ENCODERS.get(encoder, encoder) if encoder else "libx264"
    
    # 识别编码器类型
    is_nvenc = "nvenc" in actual_encoder
    is_qsv = "qsv" in actual_encoder
    is_amf = "amf" in actual_encoder
    is_cpu = actual_encoder in ("libx264", "libx265")

    # 视频滤镜链
    vf_filters = []
    if subtitle_path:
        escaped_sub = escape_path_for_ffmpeg(subtitle_path)
        vf_filters.append(f"subtitles='{escaped_sub}'")
    if resolution and isinstance(resolution, str) and "x" in resolution:
        w, h = resolution.split("x")
        vf_filters.append(f"scale={w}:{h}")

    # 构建基础命令部分
    base_cmd = [ffmpeg, "-y", "-i", input_path]
    
    if vf_filters:
        base_cmd.extend(["-vf", ",".join(vf_filters)])

    base_cmd.extend(["-c:v", actual_encoder])
    base_cmd.extend(["-b:v", bitrate])

    # 根据编码器类型添加速度预设
    if speed_preset:
        base_cmd.extend(["-preset", speed_preset])

    if fps:
        base_cmd.extend(["-r", str(fps)])

    # 额外参数
    if extra_args:
        base_cmd.extend(extra_args.split())

    # ===== Pass 1: 分析阶段 =====
    pass1_cmd = base_cmd.copy()
    
    if is_nvenc:
        # NVENC 2-pass
        pass1_cmd.extend(["-multipass", "fullres"])
        pass1_cmd.extend(["-2pass", "1"])
    elif is_amf:
        # AMF 2-pass
        pass1_cmd.extend(["-2pass", "1"])
    else:
        # CPU 编码器 (libx264/libx265)
        pass1_cmd.extend(["-pass", "1"])
    
    # 第一遍禁用音频，输出到空设备
    pass1_cmd.extend(["-an", "-f", "null"])
    pass1_cmd.append("NUL" if os.name == "nt" else "/dev/null")

    # ===== Pass 2: 实际编码 =====
    pass2_cmd = base_cmd.copy()
    
    if is_nvenc:
        pass2_cmd.extend(["-multipass", "fullres"])
        pass2_cmd.extend(["-2pass", "1"])  # NVENC 不需要单独的 pass 2 标志
    elif is_amf:
        pass2_cmd.extend(["-2pass", "1"])
    else:
        # CPU 编码器
        pass2_cmd.extend(["-pass", "2"])

    # 流映射 (Pass 2)
    pass2_cmd.extend(["-map", "0:v:0"])
    audio_map_args = _build_stream_map_args("a", audio_tracks, audio_tracks_custom)
    pass2_cmd.extend(audio_map_args)
    subtitle_map_args = _build_stream_map_args("s", subtitle_tracks, subtitle_tracks_custom)
    pass2_cmd.extend(subtitle_map_args)

    # 音频设置
    if audio_tracks != "none" and "-an" not in pass2_cmd:
        pass2_cmd.extend(["-c:a", audio_encoder])
        if audio_encoder != "copy":
            pass2_cmd.extend(["-b:a", audio_bitrate])

    # 字幕编码
    if subtitle_tracks != "none" and "-sn" not in pass2_cmd:
        pass2_cmd.extend(["-c:s", "copy"])

    pass2_cmd.append(output_path)

    # M2.4: 仅 Pass 2 注入结构化进度。Pass 1 是分析阶段 (输出到 NUL, 结束后
    # 才运行 Pass 2), 若也注入会让进度条先走满一遍再回退, 反而误导用户;
    # 分析阶段 UI 保持不确定进度。
    return pass1_cmd, inject_progress(pass2_cmd)


def run_2pass_encode(pass1_cmd: List[str], pass2_cmd: List[str], dry_run: bool = False) -> int:
    """两遍共用独立的可写统计文件；成功、失败和取消均自动清理。"""
    if dry_run:
        print(f"[小雪工具箱] 执行命令 (2-Pass):", flush=True)
        print(f"Pass 1: {' '.join(pass1_cmd)}", flush=True)
        print(f"Pass 2: {' '.join(pass2_cmd)}", flush=True)
        print("[Debug 模式] 仅输出命令，不执行。", flush=True)
        return 0

    from .platform.paths import platform_paths
    with tempfile.TemporaryDirectory(prefix="encode-", dir=platform_paths().temp_dir) as directory:
        prefix = os.path.join(directory, "ffmpeg2pass")
        commands = [cmd[:-1] + ["-passlogfile", prefix] + cmd[-1:]
                    for cmd in (pass1_cmd, pass2_cmd)]
        print("[Pass 1/2] 分析视频...", flush=True)
        result = run_ffmpeg_command(commands[0], dry_run=False)
        if result != 0:
            print("[错误] Pass 1 失败，终止编码", flush=True)
            return result
        context = current_task()
        if context is not None:
            context.raise_if_cancelled()
        print("[Pass 2/2] 正式编码...", flush=True)
        return run_ffmpeg_command(commands[1], dry_run=False)
