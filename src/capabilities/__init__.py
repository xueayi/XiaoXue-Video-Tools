# -*- coding: utf-8 -*-
"""能力探测层 (M3.1) 与编码器能力模型 (M3.2)。

对上层暴露一组只读的 FFmpeg 能力快照与编码器能力矩阵, 供编码参数映射 /
容器能力矩阵与 UI 状态展示复用:

* :mod:`src.capabilities.ffmpeg_probe` —— 纯标准库的解析 / 探测 / 单例缓存
  (不依赖 Qt, 可独立单测);
* :mod:`src.capabilities.worker` —— QThread 后台探测包装, 避免阻塞启动;
* :mod:`src.capabilities.encoder` —— 编码器能力模型 + 硬件 RC 真实参数映射
  (纯 Python, 以 presets.ENCODERS 为单一数据源)。
"""

from .encoder import (
    AMF_SPEED_VALUES,
    CPU_RC_MODES,
    HARDWARE_RC_MODES,
    RC_CBR,
    RC_CRF,
    RC_TWO_PASS,
    RC_VBR,
    EncoderCapability,
    RcPlan,
    build_encoder_capabilities,
    default_speed_preset,
    encoder_capability,
    plan_rate_control,
    supported_rc_modes,
    visible_encoders,
)
from .ffmpeg_probe import (
    KEY_ENCODERS,
    NVENC_ENCODERS,
    PROBE_ERROR_LIMIT,
    FfmpegCaps,
    available_key_encoders,
    caps_ready,
    failed_caps,
    get_capabilities,
    nvenc_available,
    parse_encoder_kinds,
    parse_encoders,
    parse_filters,
    parse_hwaccels,
    parse_version,
    probe_ffmpeg,
    set_capabilities,
    short_probe_error,
)
from .worker import CapabilityProbeWorker, start_capability_probe

__all__ = [
    "AMF_SPEED_VALUES",
    "CPU_RC_MODES",
    "HARDWARE_RC_MODES",
    "KEY_ENCODERS",
    "NVENC_ENCODERS",
    "PROBE_ERROR_LIMIT",
    "RC_CBR",
    "RC_CRF",
    "RC_TWO_PASS",
    "RC_VBR",
    "CapabilityProbeWorker",
    "EncoderCapability",
    "FfmpegCaps",
    "RcPlan",
    "available_key_encoders",
    "build_encoder_capabilities",
    "caps_ready",
    "default_speed_preset",
    "encoder_capability",
    "failed_caps",
    "get_capabilities",
    "nvenc_available",
    "parse_encoder_kinds",
    "parse_encoders",
    "parse_filters",
    "parse_hwaccels",
    "parse_version",
    "plan_rate_control",
    "probe_ffmpeg",
    "set_capabilities",
    "short_probe_error",
    "start_capability_probe",
    "supported_rc_modes",
    "visible_encoders",
]
