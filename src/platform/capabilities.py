# -*- coding: utf-8 -*-
"""平台能力聚合 (M4.1)。

把「当前跑在什么平台」与「该平台实际能做什么」收敛到一个只读快照里,
供各页面读取, 避免在 UI/业务代码里散落 ``sys.platform == "darwin"`` 之类
判断:

* ``is_windows`` / ``is_macos`` / ``is_linux``: 平台判定;
* ``ffmpeg_path`` / ``ffprobe_path``: 实际解析到的可执行文件;
* ``ffmpeg_caps``: M3 的 :class:`FfmpegCaps` 快照 (懒加载: 只有 M3 探测
  完成后才填充, 不在这里重复跑子进程);
* ``avisynth_available``: Windows 且资源目录 bin 下 AviSynth/VSFilter DLL
  齐全 (兼容模式字幕);
* ``self_update_available``: 仅 Windows;
* ``videotoolbox_available``: macOS 且 ffmpeg 探测到 VideoToolbox 编码器。
"""

import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..capabilities.ffmpeg_probe import (
    FfmpegCaps,
    caps_ready,
    get_capabilities,
)
from ..utils import get_ffmpeg_path, get_ffprobe_path
from .paths import resolve_resource_dir

#: macOS 硬件编码器名称 (任一存在即视为 VideoToolbox 可用)
VIDEOTOOLBOX_ENCODERS = frozenset(
    {"h264_videotoolbox", "hevc_videotoolbox"})

#: AviSynth 兼容模式依赖的 DLL (缺一不可)
_AVISYNTH_DLLS = ("AviSynth.dll", "VSFilter.dll")

_capabilities_lock = threading.Lock()
_capabilities: Optional["PlatformCapabilities"] = None


def _current_platform() -> str:
    """当前平台标识 (``sys.platform``; 单测可 monkeypatch 本函数)。"""
    return sys.platform


def _resource_bin_dir() -> Path:
    """打包资源里的 bin 目录 (AviSynth/VSFilter DLL 所在)。"""
    return resolve_resource_dir() / "bin"


def _avisynth_available(platform: str) -> bool:
    """兼容模式字幕是否可用: Windows 且资源 bin 下两个 DLL 都存在。"""
    if platform != "win32":
        return False
    try:
        bin_dir = _resource_bin_dir()
        return all((bin_dir / name).is_file() for name in _AVISYNTH_DLLS)
    except OSError:
        return False


def _videotoolbox_available(platform: str, caps: Optional[FfmpegCaps]) -> bool:
    """macOS 且 ffmpeg 探测到 VideoToolbox 编码器。"""
    if platform != "darwin" or caps is None or caps.probe_error:
        return False
    return bool(VIDEOTOOLBOX_ENCODERS & set(caps.encoders))


def _safe_path(getter) -> str:
    """调用路径 getter; 异常时返回空串 (能力快照绝不因路径失败而崩)。"""
    try:
        return str(getter() or "")
    except Exception:
        return ""


def _current_ffmpeg_caps() -> Optional[FfmpegCaps]:
    """读取 M3 能力快照; 未探测完成时返回 None (不在此层触发探测)。"""
    try:
        if caps_ready():
            return get_capabilities()
    except Exception:
        return None
    return None


@dataclass(frozen=True)
class PlatformCapabilities:
    """平台能力快照 (只读, 可在任意线程读取)。

    Attributes:
        os_name: ``sys.platform`` 值 (win32 / darwin / linux ...)。
        ffmpeg_path: 实际解析到的 ffmpeg 路径。
        ffprobe_path: 实际解析到的 ffprobe 路径。
        ffmpeg_caps: M3 的 FFmpeg 能力快照; M3 探测完成前为 None。
        avisynth_available: Windows 兼容模式字幕 (AviSynth+VSFilter) 可用。
        self_update_available: 是否支持应用内自更新 (仅 Windows)。
        videotoolbox_available: macOS 且探测到 VideoToolbox 编码器。
    """

    os_name: str
    ffmpeg_path: str = ""
    ffprobe_path: str = ""
    ffmpeg_caps: Optional[FfmpegCaps] = None
    avisynth_available: bool = False
    self_update_available: bool = False
    videotoolbox_available: bool = False

    @property
    def is_windows(self) -> bool:
        return self.os_name == "win32"

    @property
    def is_macos(self) -> bool:
        return self.os_name == "darwin"

    @property
    def is_linux(self) -> bool:
        return self.os_name.startswith("linux")


def detect() -> PlatformCapabilities:
    """探测当前平台能力; 不跑 ffmpeg 子进程 (只读 M3 已有快照)。"""
    platform = _current_platform()
    caps = _current_ffmpeg_caps()
    return PlatformCapabilities(
        os_name=platform,
        ffmpeg_path=_safe_path(get_ffmpeg_path),
        ffprobe_path=_safe_path(get_ffprobe_path),
        ffmpeg_caps=caps,
        avisynth_available=_avisynth_available(platform),
        self_update_available=platform == "win32",
        videotoolbox_available=_videotoolbox_available(platform, caps),
    )


def platform_capabilities(refresh: bool = False) -> PlatformCapabilities:
    """进程级平台能力单例。

    Args:
        refresh: 清空缓存重新探测 (例如 M3 后台能力探测完成之后)。
    """
    global _capabilities
    with _capabilities_lock:
        if refresh or _capabilities is None:
            _capabilities = detect()
        return _capabilities


def reset_platform_capabilities() -> None:
    """清空单例 (测试用)。"""
    global _capabilities
    with _capabilities_lock:
        _capabilities = None
