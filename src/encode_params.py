# -*- coding: utf-8 -*-
"""
编码参数模块：封装视频编码相关的参数解析和验证逻辑。

将 execute_encode 函数中的参数解析逻辑抽象为独立模块，
提高代码的可读性、可测试性和可维护性。
"""
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum

from colorama import Fore, Style


class EncodeMode(Enum):
    """编码模式枚举"""
    NORMAL = "normal"           # 普通编码 (FFmpeg subtitles 滤镜)
    COMPAT = "compat"           # 兼容模式 (AviSynth + VSFilter)
    TWO_PASS = "2pass"          # 两遍编码


@dataclass
class EncodeParams:
    """
    编码参数数据类。
    
    封装视频编码所需的所有参数，提供统一的参数访问接口。
    """
    # 必填参数
    input_path: str
    output_path: str
    
    # 编码器参数
    encoder: str = "libx264"
    crf: Optional[int] = None
    bitrate: Optional[str] = None
    speed_preset: Optional[str] = None
    rc_mode: Optional[str] = None
    
    # 视频参数
    resolution: Optional[str] = None
    fps: Optional[int] = None
    
    # 音频参数
    audio_encoder: str = "copy"
    audio_bitrate: str = "192k"
    
    # 字幕参数
    subtitle_path: Optional[str] = None
    compat_mode: bool = False
    
    # 其他参数
    extra_args: Optional[str] = None
    dry_run: bool = False
    
    # 模式标记
    is_custom: bool = False
    preset_name: Optional[str] = None
    
    def get_encode_mode(self) -> EncodeMode:
        """
        根据参数确定编码模式。
        
        Returns:
            编码模式枚举值
        """
        if self.compat_mode and self.subtitle_path:
            return EncodeMode.COMPAT
        elif self.is_custom and self.rc_mode == "2pass" and self.bitrate:
            return EncodeMode.TWO_PASS
        else:
            return EncodeMode.NORMAL
    
    def validate(self) -> tuple[bool, str]:
        """
        验证参数有效性。
        
        Returns:
            (是否有效, 错误信息)
        """
        # 验证输入文件存在
        if not os.path.exists(self.input_path):
            return False, f"输入文件不存在: {self.input_path}"
        
        # 验证字幕文件存在 (如果指定了)
        if self.subtitle_path and not os.path.exists(self.subtitle_path):
            return False, f"字幕文件不存在: {self.subtitle_path}"
        
        # 验证 CRF 范围
        if self.crf is not None and not (0 <= self.crf <= 51):
            return False, f"CRF 值超出范围 (0-51): {self.crf}"
        
        # 验证分辨率格式
        if self.resolution:
            if "x" not in self.resolution:
                return False, f"分辨率格式错误，应为 WxH: {self.resolution}"
            try:
                w, h = self.resolution.split("x")
                int(w), int(h)
            except ValueError:
                return False, f"分辨率格式错误: {self.resolution}"
        
        return True, ""


def resolve_encoder_params(
    args,
    quality_presets: Dict[str, Any],
    encoders: Dict[str, str],
    audio_encoders: Dict[str, str],
    rate_control_modes: Dict[str, str],
    generate_output_path_func,
) -> EncodeParams:
    """
    从 argparse 参数解析编码参数。
    
    统一处理预设模式和自定义模式的参数解析逻辑。
    
    Args:
        args: argparse 解析后的参数对象
        quality_presets: 质量预设字典
        encoders: 编码器映射字典
        audio_encoders: 音频编码器映射字典
        rate_control_modes: 码率控制模式映射字典
        generate_output_path_func: 生成输出路径的函数
        
    Returns:
        EncodeParams 实例
    """
    preset_name = args.preset
    is_custom = preset_name == "自定义 (Custom)"
    
    # 默认值
    encoder = "libx264"
    crf = None
    speed_preset = None
    audio_encoder = "copy"
    audio_bitrate = "192k"
    
    # 根据模式获取参数
    if not is_custom and preset_name in quality_presets:
        # 预设模式：从预设中读取参数
        preset = quality_presets[preset_name]
        encoder = preset.get("encoder", "libx264")
        crf = preset.get("cq") or preset.get("crf")
        speed_preset = preset.get("preset")
        audio_encoder = preset.get("audio_encoder", "copy")
        audio_bitrate = preset.get("audio_bitrate", "192k")
        
        # NVENC 预设：检查用户是否选择了自定义档位
        nvenc_preset = getattr(args, 'nvenc_preset', '使用预设默认')
        if nvenc_preset and nvenc_preset != '使用预设默认':
            # 用户选择了 NVENC 档位，覆盖预设默认值
            if "nvenc" in encoder:
                speed_preset = nvenc_preset
    else:
        # 自定义模式：从 args 中读取参数
        encoder = encoders.get(args.encoder, "libx264")
        crf = args.crf
        audio_encoder = audio_encoders.get(args.audio_encoder, "copy")
        audio_bitrate = args.audio_bitrate
        
        # 自定义模式下根据编码器类型选择速度预设
        if "nvenc" in encoder:
            # NVENC 编码器：使用 N卡速度档位
            nvenc_preset = getattr(args, 'nvenc_preset', '使用预设默认')
            if nvenc_preset and nvenc_preset != '使用预设默认':
                speed_preset = nvenc_preset
            else:
                speed_preset = "p4"  # NVENC 默认档位
        else:
            # CPU 编码器：使用编码速度预设
            speed_preset = getattr(args, 'speed_preset', None)
    
    # 获取码率控制参数
    rc_mode_name = getattr(args, 'rate_control', 'CRF/CQ (恒定质量)')
    rc_mode = rate_control_modes.get(rc_mode_name, "crf")
    video_bitrate = getattr(args, 'video_bitrate', '') or None
    
    # 自动生成输出路径
    output_path = args.output
    if not output_path or output_path.strip() == "":
        output_path = generate_output_path_func(args.input, encoder)
    
    # 构建参数对象
    return EncodeParams(
        input_path=args.input,
        output_path=output_path,
        encoder=encoder,
        crf=crf,
        bitrate=video_bitrate if is_custom else None,
        speed_preset=speed_preset,
        rc_mode=rc_mode if is_custom else None,
        resolution=args.resolution if args.resolution and is_custom else None,
        fps=args.fps if args.fps > 0 and is_custom else None,
        audio_encoder=audio_encoder,
        audio_bitrate=audio_bitrate,
        subtitle_path=args.subtitle if args.subtitle else None,
        compat_mode=getattr(args, 'compat_mode', False),
        extra_args=args.extra_args if args.extra_args else None,
        dry_run=getattr(args, 'debug_mode', False),
        is_custom=is_custom,
        preset_name=preset_name,
    )


def print_encode_info(params: EncodeParams, quality_presets: Dict[str, Any]) -> None:
    """
    打印编码参数信息。
    
    Args:
        params: 编码参数对象
        quality_presets: 质量预设字典 (用于获取预设信息)
    """
    if not params.is_custom and params.preset_name in quality_presets:
        preset = quality_presets[params.preset_name]
        print(f"[预设] {params.preset_name}", flush=True)
        print(f"  编码器: {params.encoder}", flush=True)
        print(f"  CRF: {preset.get('crf') or preset.get('cq', 'N/A')}", flush=True)
        print(f"  速度: {preset.get('preset', 'N/A')}", flush=True)
    else:
        print(f"[自定义模式]", flush=True)
        print(f"  编码器: {params.encoder}", flush=True)
        print(f"  CRF: {params.crf}", flush=True)
        if params.rc_mode:
            print(f"  码率控制: {params.rc_mode}", flush=True)
        if params.bitrate:
            print(f"  视频码率: {params.bitrate}", flush=True)
    
    # 打印编码模式
    mode = params.get_encode_mode()
    if mode == EncodeMode.COMPAT:
        print(f"{Fore.CYAN}[兼容模式] 已启用 AviSynth + VSFilter 字幕渲染{Style.RESET_ALL}", flush=True)
    elif mode == EncodeMode.TWO_PASS:
        print(f"{Fore.CYAN}[2-Pass 模式] 将执行真正的两遍编码{Style.RESET_ALL}", flush=True)
