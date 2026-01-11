# -*- coding: utf-8 -*-
"""
兼容模式编码模块：使用 AviSynth + VSFilter 方案进行字幕压制。

复刻小丸工具箱的字幕渲染流程，解决 FFmpeg 内置 libass 无法正确渲染
Windows 系统字体、字重等兼容性问题。

核心流程:
1. 生成 .avs 脚本 (加载视频源 + 烧录字幕)
2. 临时修改 PATH 环境变量，添加 bin 目录 (便携版方案)
3. FFmpeg 读取 AVS 视频流 + 原视频音频流，合成输出
4. 清理临时文件 (.avs, .lwi)
"""
import os
import subprocess
import tempfile
import shutil
from typing import Optional, List, Tuple

from colorama import Fore, Style

from .utils import get_base_dir, get_internal_dir, get_ffmpeg_path
from .presets import ENCODERS

import logging
logger = logging.getLogger(__name__)


def get_bin_dir() -> str:
    """
    获取 bin 目录的绝对路径。
    
    Returns:
        bin 目录路径
    """
    # 优先检查 _internal/bin (打包环境)
    internal_bin = os.path.join(get_internal_dir(), 'bin')
    if os.path.isdir(internal_bin):
        return internal_bin
    
    # 开发环境: 项目根目录/bin
    base_bin = os.path.join(get_base_dir(), 'bin')
    if os.path.isdir(base_bin):
        return base_bin
    
    return base_bin


def generate_avs_script(
    video_path: str,
    subtitle_path: str,
    output_avs_path: str,
) -> Tuple[str, str]:
    """
    生成 AviSynth 脚本文件。
    
    为避免 VSFilter TextSub 无法处理中文路径的问题，
    将字幕文件复制到临时目录使用 ASCII 文件名。
    
    Args:
        video_path: 输入视频的绝对路径
        subtitle_path: 字幕文件的绝对路径
        output_avs_path: 输出 .avs 脚本的路径
        
    Returns:
        (avs_path, temp_subtitle_path) - AVS 文件路径和临时字幕文件路径
    """
    bin_dir = get_bin_dir()
    temp_dir = tempfile.gettempdir()
    
    # 诊断日志: 打印 bin 目录信息
    print(f"{Fore.CYAN}[诊断] bin 目录路径: {bin_dir}{Style.RESET_ALL}")
    print(f"[诊断] bin 目录是否存在: {os.path.isdir(bin_dir)}")
    
    # 检查关键 DLL 文件
    dlls = ["AviSynth.dll", "LSMASHSource.dll", "VSFilter.dll"]
    for dll in dlls:
        dll_path = os.path.join(bin_dir, dll)
        exists = os.path.isfile(dll_path)
        size = os.path.getsize(dll_path) if exists else 0
        print(f"[诊断] {dll}: 存在={exists}, 大小={size} bytes, 路径={dll_path}")
    
    # 将字幕文件复制到临时目录，使用 ASCII 文件名
    subtitle_ext = os.path.splitext(subtitle_path)[1]
    temp_subtitle = os.path.join(temp_dir, f"xiaoxue_temp_sub{subtitle_ext}")
    shutil.copy2(subtitle_path, temp_subtitle)
    logger.info(f"复制字幕到临时目录: {temp_subtitle}")
    
    # 将所有路径转换为正斜杠格式 (AviSynth 要求)
    lsmash_dll = os.path.join(bin_dir, "LSMASHSource.dll").replace("\\", "/")
    vsfilter_dll = os.path.join(bin_dir, "VSFilter.dll").replace("\\", "/")
    video_avs_path = os.path.abspath(video_path).replace("\\", "/")
    subtitle_avs_path = temp_subtitle.replace("\\", "/")
    
    # 诊断日志: 打印 AVS 脚本中使用的路径
    print(f"[诊断] AVS 中 LSMASHSource.dll 路径: {lsmash_dll}")
    print(f"[诊断] AVS 中 VSFilter.dll 路径: {vsfilter_dll}")
    
    # AVS 脚本内容
    avs_content = f'''# XiaoXue Toolbox - Compat Mode AVS Script
LoadPlugin("{lsmash_dll}")
LoadPlugin("{vsfilter_dll}")
LWLibavVideoSource("{video_avs_path}", cache=False)
TextSub("{subtitle_avs_path}")
ConvertToYV12()
'''
    
    # 使用不带 BOM 的 UTF-8 编码 (FFmpeg AviSynth 模块不支持 BOM)
    with open(output_avs_path, 'w', encoding='utf-8') as f:
        f.write(avs_content)
    
    logger.info(f"生成 AVS 脚本: {output_avs_path}")
    return output_avs_path, temp_subtitle


def build_compat_encode_command(
    avs_script_path: str,
    original_video_path: str,
    output_path: str,
    encoder: str = "libx264",
    crf: Optional[int] = None,
    bitrate: Optional[str] = None,
    speed_preset: Optional[str] = None,
    resolution: Optional[str] = None,
    fps: Optional[int] = None,
    audio_encoder: str = "aac",
    audio_bitrate: str = "192k",
    extra_args: Optional[str] = None,
    rc_mode: Optional[str] = None,
) -> List[str]:
    """
    构建兼容模式的 FFmpeg 编码命令。
    
    使用两个输入源:
    - 输入 0: AVS 脚本 (视频画面 + 烧录字幕)
    - 输入 1: 原始视频 (音频流)
    
    Args:
        avs_script_path: AVS 脚本路径
        original_video_path: 原始视频路径 (用于提取音频)
        output_path: 输出视频路径
        encoder: 视频编码器
        crf: CRF/CQ 值
        bitrate: 目标码率
        speed_preset: 编码速度预设
        resolution: 分辨率 (如 "1920x1080")
        fps: 帧率
        audio_encoder: 音频编码器
        audio_bitrate: 音频码率
        extra_args: 额外 FFmpeg 参数
        rc_mode: 码率控制模式
        
    Returns:
        FFmpeg 命令列表
    """
    ffmpeg = get_ffmpeg_path()
    
    # 基础命令: 双输入源
    cmd = [
        ffmpeg, "-y",
        "-i", avs_script_path,     # 输入 0: AVS (视频+字幕)
        "-i", original_video_path,  # 输入 1: 原视频 (音频)
        "-map", "0:v",              # 取 AVS 的视频流
        "-map", "1:a?",             # 取原视频的音频流 (可选, 避免无音频报错)
    ]
    
    # 视频滤镜 (仅分辨率缩放，字幕已由 AVS 处理)
    vf_filters = []
    if resolution and isinstance(resolution, str) and "x" in resolution:
        try:
            w, h = resolution.split("x")
            vf_filters.append(f"scale={w}:{h}")
        except ValueError:
            pass
    
    if vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])
    
    # 视频编码器
    actual_encoder = ENCODERS.get(encoder, encoder) if encoder else "libx264"
    cmd.extend(["-c:v", actual_encoder])
    
    # 编码参数 - 复用 core.py 的逻辑
    if actual_encoder != "copy":
        is_nvenc = "nvenc" in actual_encoder
        is_qsv = "qsv" in actual_encoder
        is_amf = "amf" in actual_encoder
        
        # 码率控制
        if rc_mode == "vbr" and bitrate:
            cmd.extend(["-b:v", bitrate])
            if is_nvenc:
                cmd.extend(["-rc", "vbr"])
            cmd.extend(["-maxrate", bitrate, "-bufsize", bitrate])
        elif rc_mode == "cbr" and bitrate:
            cmd.extend(["-b:v", bitrate])
            if is_nvenc:
                cmd.extend(["-rc", "cbr"])
            cmd.extend(["-minrate", bitrate, "-maxrate", bitrate, "-bufsize", bitrate])
        elif bitrate:
            cmd.extend(["-b:v", bitrate])
        elif crf is not None:
            if is_nvenc:
                cmd.extend(["-cq", str(crf)])
            elif is_qsv:
                cmd.extend(["-global_quality", str(crf)])
            elif is_amf:
                cmd.extend(["-qp_i", str(crf), "-qp_p", str(crf)])
            else:
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


def run_compat_encode(
    input_path: str,
    output_path: str,
    subtitle_path: str,
    encoder: str = "libx264",
    crf: Optional[int] = None,
    bitrate: Optional[str] = None,
    speed_preset: Optional[str] = None,
    resolution: Optional[str] = None,
    fps: Optional[int] = None,
    audio_encoder: str = "aac",
    audio_bitrate: str = "192k",
    extra_args: Optional[str] = None,
    rc_mode: Optional[str] = None,
    dry_run: bool = False,
) -> int:
    """
    执行兼容模式字幕压制的完整流程。
    
    Args:
        input_path: 输入视频路径
        output_path: 输出视频路径
        subtitle_path: 字幕文件路径
        encoder: 视频编码器
        crf: CRF/CQ 值
        bitrate: 目标码率
        speed_preset: 编码速度预设
        resolution: 分辨率
        fps: 帧率
        audio_encoder: 音频编码器
        audio_bitrate: 音频码率
        extra_args: 额外 FFmpeg 参数
        rc_mode: 码率控制模式
        dry_run: 仅打印命令，不执行
        
    Returns:
        进程返回码 (0 表示成功)
    """
    print(f"{Fore.CYAN}[兼容模式] 使用 AviSynth + VSFilter 渲染字幕{Style.RESET_ALL}", flush=True)
    
    # 生成临时 AVS 脚本
    avs_script = os.path.join(tempfile.gettempdir(), "xiaoxue_compat_temp.avs")
    temp_subtitle = None  # 临时字幕文件路径
    
    try:
        # 步骤 1: 生成 AVS 脚本 (会复制字幕到临时目录)
        print(f"[1/3] 生成 AVS 脚本...", flush=True)
        _, temp_subtitle = generate_avs_script(input_path, subtitle_path, avs_script)
        
        # 步骤 2: 构建 FFmpeg 命令
        print(f"[2/3] 构建编码命令...", flush=True)
        cmd = build_compat_encode_command(
            avs_script_path=avs_script,
            original_video_path=input_path,
            output_path=output_path,
            encoder=encoder,
            crf=crf,
            bitrate=bitrate,
            speed_preset=speed_preset,
            resolution=resolution,
            fps=fps,
            audio_encoder=audio_encoder,
            audio_bitrate=audio_bitrate,
            extra_args=extra_args,
            rc_mode=rc_mode,
        )
        
        cmd_str = " ".join(cmd)
        logger.info(f"Compat mode command: {cmd_str}")
        
        print(f"{Fore.CYAN}[小雪工具箱] 执行命令:{Style.RESET_ALL}", flush=True)
        print(cmd_str, flush=True)
        print("-" * 50, flush=True)
        
        if dry_run:
            print(f"{Fore.YELLOW}[Debug 模式] 仅输出命令，不执行。{Style.RESET_ALL}", flush=True)
            return 0
        
        # 步骤 3: 执行编码 (使用临时 PATH 环境变量)
        print(f"[3/3] 开始编码...", flush=True)
        
        # 便携版方案: 临时修改 PATH 和工作目录
        bin_dir = get_bin_dir()
        env = os.environ.copy()
        env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
        
        # 诊断: 打印传递给 FFmpeg 的 PATH (只打印前300字符)
        print(f"[诊断] FFmpeg PATH 前缀: {bin_dir}")
        print(f"[诊断] 工作目录设为: {bin_dir}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            env=env,  # 使用修改后的环境变量
            cwd=bin_dir,  # 将工作目录设为 bin 目录
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        
        # 实时读取输出
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                print(line, end='', flush=True)
        
        process.wait()
        
        if process.returncode == 0:
            print(f"\n{Fore.GREEN}[成功] 兼容模式压制完成!{Style.RESET_ALL}", flush=True)
        else:
            print(f"\n{Fore.RED}[失败] 兼容模式压制失败 (code={process.returncode}){Style.RESET_ALL}", flush=True)
            _print_compat_error_tips()
        
        return process.returncode
        
    except Exception as e:
        print(f"\n{Fore.RED}[错误] 兼容模式执行失败: {e}{Style.RESET_ALL}", flush=True)
        logger.exception("Compat encode failed")
        return -1
        
    finally:
        # 清理临时文件
        cleanup_temp_files(avs_script, input_path, temp_subtitle)


def cleanup_temp_files(avs_path: str, video_path: str, temp_subtitle: str = None) -> None:
    """
    清理兼容模式产生的临时文件。
    
    Args:
        avs_path: AVS 脚本路径
        video_path: 原视频路径 (用于定位 .lwi 文件)
        temp_subtitle: 临时字幕文件路径
    """
    files_to_clean = []
    
    # AVS 脚本
    if avs_path and os.path.exists(avs_path):
        files_to_clean.append(avs_path)
    
    # 临时字幕文件
    if temp_subtitle and os.path.exists(temp_subtitle):
        files_to_clean.append(temp_subtitle)
    
    # L-SMASH 索引文件 (在原视频同目录)
    if video_path:
        lwi_path = video_path + ".lwi"
        if os.path.exists(lwi_path):
            files_to_clean.append(lwi_path)
    
    for f in files_to_clean:
        try:
            os.remove(f)
            logger.info(f"清理临时文件: {f}")
        except Exception as e:
            logger.warning(f"清理临时文件失败: {f}, 错误: {e}")


def _print_compat_error_tips() -> None:
    """打印兼容模式失败的排查提示。"""
    print(f"""
{Fore.YELLOW}[排查提示] 兼容模式失败可能的原因:{Style.RESET_ALL}
  • bin/ 目录下缺少 AviSynth.dll、LSMASHSource.dll 或 VSFilter.dll
  • 视频编码格式不受 L-SMASH 支持 (尝试先转封装为 MP4)
  • 字幕文件编码有问题 (建议使用 UTF-8 编码的 .ass 文件)
  • 路径中包含特殊字符 (尝试移动文件到简单路径)

{Fore.GREEN}建议:{Style.RESET_ALL}
  如果问题持续，请关闭"兼容模式"使用 FFmpeg 内置字幕滤镜。
""", flush=True)
