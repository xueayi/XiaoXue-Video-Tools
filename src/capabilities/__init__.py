# -*- coding: utf-8 -*-
"""能力探测层 (M3.1)。

对上层暴露一组只读的 FFmpeg 能力快照, 供 M3.2 编码器能力矩阵 /
M3.3 容器能力矩阵与 UI 状态展示复用:

* :mod:`src.capabilities.ffmpeg_probe` —— 纯标准库的解析 / 探测 / 单例缓存
  (不依赖 Qt, 可独立单测);
* :mod:`src.capabilities.worker` —— QThread 后台探测包装, 避免阻塞启动。
"""

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
    "KEY_ENCODERS",
    "NVENC_ENCODERS",
    "PROBE_ERROR_LIMIT",
    "CapabilityProbeWorker",
    "FfmpegCaps",
    "available_key_encoders",
    "caps_ready",
    "failed_caps",
    "get_capabilities",
    "nvenc_available",
    "parse_encoder_kinds",
    "parse_encoders",
    "parse_filters",
    "parse_hwaccels",
    "parse_version",
    "probe_ffmpeg",
    "set_capabilities",
    "short_probe_error",
    "start_capability_probe",
]
