# -*- coding: utf-8 -*-
"""
FFmpeg 核心调用模块：构建命令行并执行。
"""
import subprocess
import os
import tempfile
from typing import Optional, List, Tuple

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
    rc_mode: Optional[str] = None,
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
    if resolution and isinstance(resolution, str) and "x" in resolution:
        try:
            w, h = resolution.split("x")
            vf_filters.append(f"scale={w}:{h}")
        except ValueError:
            pass  # 无效分辨率格式，跳过

    if vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])

    # 视频编码器
    actual_encoder = ENCODERS.get(encoder, encoder) if encoder else "libx264"
    cmd.extend(["-c:v", actual_encoder])

    # 编码参数 - 根据编码器类型自动适配
    if actual_encoder != "copy":
        # 识别编码器类型
        is_nvenc = "nvenc" in actual_encoder
        is_qsv = "qsv" in actual_encoder
        is_amf = "amf" in actual_encoder
        is_cpu = actual_encoder in ("libx264", "libx265")
        
        # 处理码率控制模式
        if rc_mode == "2pass":
            # 2-Pass 编码逻辑 (当前简化为 VBR 高质量模式)
            # 注意: 真正的 2-pass 需要运行两次 ffmpeg，这里用高质量 VBR 替代
            if bitrate:
                cmd.extend(["-b:v", bitrate])
                if is_nvenc:
                    cmd.extend(["-rc", "vbr_hq", "-2pass", "1"])
                elif is_amf:
                    cmd.extend(["-rc", "vbr_peak", "-2pass", "1"])
                else:
                    # CPU 编码器使用 VBR 高质量
                    cmd.extend(["-maxrate", bitrate, "-bufsize", bitrate])
            elif crf is not None:
                # 没有码率时回退到 CRF/CQ 模式
                if is_nvenc:
                    cmd.extend(["-cq", str(crf)])
                elif is_qsv:
                    cmd.extend(["-global_quality", str(crf)])
                else:
                    cmd.extend(["-crf", str(crf)])
                    
        elif rc_mode == "vbr":
            # VBR 可变码率模式
            if bitrate:
                cmd.extend(["-b:v", bitrate])
                if is_nvenc:
                    cmd.extend(["-rc", "vbr"])
                elif is_amf:
                    cmd.extend(["-rc", "vbr_peak"])
                # CPU 编码器默认就是 VBR
                cmd.extend(["-maxrate", bitrate, "-bufsize", bitrate])
            elif crf is not None:
                # 没有码率时回退到 CRF/CQ 模式
                if is_nvenc:
                    cmd.extend(["-cq", str(crf)])
                elif is_qsv:
                    cmd.extend(["-global_quality", str(crf)])
                else:
                    cmd.extend(["-crf", str(crf)])
                    
        elif rc_mode == "cbr":
            # CBR 恒定码率模式
            if bitrate:
                cmd.extend(["-b:v", bitrate])
                if is_nvenc:
                    cmd.extend(["-rc", "cbr"])
                elif is_amf:
                    cmd.extend(["-rc", "cbr"])
                # CPU 编码器通过 minrate=maxrate=bitrate 实现 CBR
                cmd.extend(["-minrate", bitrate, "-maxrate", bitrate, "-bufsize", bitrate])
            elif crf is not None:
                # CBR 必须有码率，回退到 CRF
                if is_nvenc:
                    cmd.extend(["-cq", str(crf)])
                elif is_qsv:
                    cmd.extend(["-global_quality", str(crf)])
                else:
                    cmd.extend(["-crf", str(crf)])
                    
        else:
            # 默认 CRF/CQ 恒定质量模式
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
                    # AMF 使用 qp_i/qp_p/qp_b
                    cmd.extend(["-qp_i", str(crf), "-qp_p", str(crf)])
                else:
                    # CPU 编码器 (libx264/libx265)
                    cmd.extend(["-crf", str(crf)])

        # 速度预设
        if speed_preset:
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

    # 收集输出用于错误分析
    output_lines = []

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
                output_lines.append(line)
                if progress_callback:
                    progress_callback(line)

        process.wait()

        if process.returncode == 0:
            print(f"\n{Fore.GREEN}[成功] 任务完成!{Style.RESET_ALL}", flush=True)
        else:
            print(f"\n{Fore.RED}[失败] FFmpeg 返回错误 (code={process.returncode}){Style.RESET_ALL}", flush=True)
            # 检测硬件编码器错误并给出友好提示
            _check_hardware_encoder_error(output_lines)

        return process.returncode

    except FileNotFoundError as e:
        print(f"\n{Fore.RED}[错误] 找不到 FFmpeg: {e}{Style.RESET_ALL}", flush=True)
        print(f"请确保 bin 目录下有 ffmpeg.exe", flush=True)
        return -1
    except Exception as e:
        print(f"\n{Fore.RED}[错误] 执行失败: {e}{Style.RESET_ALL}", flush=True)
        return -1


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
        try:
            w, h = resolution.split("x")
            vf_filters.append(f"scale={w}:{h}")
        except ValueError:
            pass

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

    # 音频设置
    pass2_cmd.extend(["-c:a", audio_encoder])
    if audio_encoder != "copy":
        pass2_cmd.extend(["-b:a", audio_bitrate])

    pass2_cmd.append(output_path)

    return pass1_cmd, pass2_cmd


def run_2pass_encode(pass1_cmd: List[str], pass2_cmd: List[str]) -> int:
    """
    执行真正的两遍编码。

    Args:
        pass1_cmd: 第一遍命令。
        pass2_cmd: 第二遍命令。

    Returns:
        最终返回码 (0 表示成功)。
    """
    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[Pass 1/2] 分析视频...{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    result1 = run_ffmpeg_command(pass1_cmd)
    
    if result1 != 0:
        print(f"\n{Fore.RED}[错误] Pass 1 失败，终止编码{Style.RESET_ALL}")
        return result1

    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[Pass 2/2] 正式编码...{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    result2 = run_ffmpeg_command(pass2_cmd)

    # 清理 2-pass 临时文件
    for ext in [".log", ".log.mbtree", "-0.log", "-0.log.mbtree"]:
        log_file = f"ffmpeg2pass{ext}"
        if os.path.exists(log_file):
            try:
                os.remove(log_file)
            except Exception:
                pass

    return result2

