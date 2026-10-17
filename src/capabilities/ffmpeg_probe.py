# -*- coding: utf-8 -*-
"""FFmpeg 能力探测 (M3.1)。

本模块只依赖标准库, 负责:

* 解析 FFmpeg CLI 的文本输出 (``-version`` / ``-encoders`` / ``-filters`` /
  ``-hwaccels``), 解析函数保持纯函数, 便于用 canned 文本单测;
* 调用 ffmpeg 子进程做一次能力探测, **任何异常/超时都不得抛出**, 失败统一
  收敛到 :attr:`FfmpegCaps.probe_error` 并保留已探测到的部分;
* 提供进程级单例缓存: 后台线程探测完成后写入, UI / 后续能力矩阵只读复用。

设计约束:
    * 探测只调用一次 CLI (4 个子进程), 结果不可变 (:class:`FfmpegCaps` frozen);
    * 不在此层做业务选择 (选哪个编码器由 M3.2 能力矩阵决定), 这里只提供
      原始能力集合与少量展示用便捷判定 (关键编码器可用数 / NVENC 判定);
    * Windows 下子进程带 ``CREATE_NO_WINDOW``, 避免无控制台时弹窗。
"""

import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Tuple, Union

from ..presets import ENCODERS
from ..utils import get_ffmpeg_path

#: 默认单个子进程超时 (秒)
DEFAULT_TIMEOUT = 15.0

#: UI 展示用的关键编码器 —— 以 presets.ENCODERS 为单一数据源
#: (新增/删除编码器只需改 presets, 探测层与首页/设置页自动跟随)
KEY_ENCODERS: Tuple[str, ...] = tuple(ENCODERS.values())

#: 任一命中即视为 NVENC 可用
NVENC_ENCODERS: FrozenSet[str] = frozenset(
    {"h264_nvenc", "hevc_nvenc", "av1_nvenc"})

#: probe_error 在 UI 上的默认截断长度
PROBE_ERROR_LIMIT = 120

_VERSION_RE = re.compile(r"ffmpeg version\s+(\S+)", re.IGNORECASE)

#: `` V....D libx264   H.264 ...`` -> 类型 / 标志 / 名称
_ENCODER_RE = re.compile(
    r"^\s*([VAS])([A-Z.]{5})\s+([A-Za-z0-9_]+)\s{2,}\S",
    re.MULTILINE,
)

#: `` TSC aap   AA->A   Apply ...`` -> 标志 / 名称 / 输入输出
_FILTER_RE = re.compile(
    r"^\s*([TSC.]{2,3})\s+([A-Za-z0-9_]+)\s+(\S+->\S+)\s{2,}\S",
    re.MULTILINE,
)

#: hwaccels 输出: 头部 + 每行一个方法名
_HWACCEL_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*$")


@dataclass(frozen=True)
class FfmpegCaps:
    """一次 FFmpeg 能力探测的不可变快照。

    Attributes:
        ffmpeg_path: 本次探测使用的 ffmpeg 路径 (失败时保留尝试路径)。
        version: ``-version`` 解析出的版本串, 未探测到为空串。
        encoders: ``-encoders`` 中的编码器名集合 (V/A/S 全部收录)。
        filters: ``-filters`` 中的滤镜名集合。
        hwaccels: ``-hwaccels`` 中的硬件加速方法集合。
        probe_error: 探测失败原因 (None 表示成功)。
        probed_at: 探测完成时间 (``time.monotonic()``, 用于判断快照新旧)。
    """

    ffmpeg_path: str
    version: str = ""
    encoders: FrozenSet[str] = frozenset()
    filters: FrozenSet[str] = frozenset()
    hwaccels: FrozenSet[str] = frozenset()
    probe_error: Optional[str] = None
    probed_at: float = 0.0

    @property
    def ok(self) -> bool:
        """探测是否成功 (有完整结果)。"""
        return self.probe_error is None

    def has_encoder(self, name: str) -> bool:
        """是否探测到指定编码器。"""
        return name in self.encoders


# ----------------------------------------------------------------
# 纯解析函数 (canned 文本单测)
# ----------------------------------------------------------------

def parse_version(text: str) -> str:
    """从 ``ffmpeg -version`` 输出解析版本串; 解析不到返回 ``""``。"""
    match = _VERSION_RE.search(text or "")
    return match.group(1) if match else ""


def parse_encoder_kinds(text: str) -> Dict[str, str]:
    """解析 ``ffmpeg -hide_banner -encoders`` 输出 -> ``{名称: V/A/S}``。

    ffmpeg 输出前半段是图例 (`` V..... = Video``), 只在分隔线之后才算
    编码器条目; 这里用「名称后至少两个空格」区分图例, 图例名是 ``=``
    不满足名称字符集, 因此不会误收。
    """
    kinds: Dict[str, str] = {}
    for kind, _flags, name in _ENCODER_RE.findall(text or ""):
        kinds[name] = kind
    return kinds


def parse_encoders(text: str) -> FrozenSet[str]:
    """解析 ``-encoders`` 输出 -> 编码器名集合 (视频/音频/字幕全部)。"""
    return frozenset(parse_encoder_kinds(text))


def parse_filters(text: str) -> FrozenSet[str]:
    """解析 ``ffmpeg -hide_banner -filters`` 输出 -> 滤镜名集合。

    图例行 (``  T.. = Timeline support``) 没有 ``A->B`` 输入输出描述,
    因此不会被 ``_FILTER_RE`` 命中。
    """
    return frozenset(name for _flags, name, _io in _FILTER_RE.findall(text or ""))


def parse_hwaccels(text: str) -> FrozenSet[str]:
    """解析 ``ffmpeg -hide_banner -hwaccels`` 输出 -> 方法名集合。

    跳过 ``Hardware acceleration methods:`` 头部; 若传入文本没有头部
    (便于单测), 则直接按每行一个名称解析。
    """
    lines = (text or "").splitlines()
    for index, line in enumerate(lines):
        if "Hardware acceleration" in line:
            lines = lines[index + 1:]
            break
    names = []
    for line in lines:
        match = _HWACCEL_RE.match(line)
        if match:
            names.append(match.group(1))
    return frozenset(names)


# ----------------------------------------------------------------
# 展示辅助 (UI 复用, 保持单一实现)
# ----------------------------------------------------------------

def short_probe_error(
    error: Union["FfmpegCaps", str, None],
    limit: int = PROBE_ERROR_LIMIT,
) -> str:
    """把探测失败原因压成单行短文本 (超长截断), 供 UI 状态标签使用。"""
    if isinstance(error, FfmpegCaps):
        text = error.probe_error or ""
    else:
        text = str(error or "")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)] + "…"


def available_key_encoders(caps: Optional["FfmpegCaps"]) -> FrozenSet[str]:
    """探测成功时, 返回 KEY_ENCODERS 中实际存在的子集; 失败/未探测为空集。"""
    if caps is None or caps.probe_error:
        return frozenset()
    return frozenset(name for name in KEY_ENCODERS if name in caps.encoders)


def nvenc_available(caps: Optional["FfmpegCaps"]) -> bool:
    """探测成功时是否有任一 NVENC 编码器; 失败/未探测返回 False。"""
    if caps is None or caps.probe_error:
        return False
    return bool(NVENC_ENCODERS & caps.encoders)


# ----------------------------------------------------------------
# 子进程探测
# ----------------------------------------------------------------

def _subprocess_kwargs() -> dict:
    """子进程参数: Windows 下隐藏控制台窗口 (不弹窗)。"""
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def failed_caps(error: str, ffmpeg_path: str = "") -> FfmpegCaps:
    """构造一个只带失败原因的空快照 (探测层/线程兜底复用)。"""
    return FfmpegCaps(
        ffmpeg_path=str(ffmpeg_path or ""),
        probe_error=str(error or "未知探测错误"),
        probed_at=time.monotonic(),
    )


def _run_flag(exe: str, flag: str, timeout: float) -> str:
    """执行一个 ffmpeg 查询参数并返回 stdout; 失败抛异常 (由上层收敛)。"""
    completed = subprocess.run(
        [exe, "-hide_banner", flag],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        **_subprocess_kwargs(),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{flag} 返回非零退出码 {completed.returncode}")
    return completed.stdout or ""


def probe_ffmpeg(
    path: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> FfmpegCaps:
    """探测 FFmpeg 能力; 任何异常/超时都不抛出, 统一写入 ``probe_error``。

    依次执行 ``-version`` / ``-encoders`` / ``-filters`` / ``-hwaccels``;
    单个查询失败不影响其余查询, 已拿到的部分结果会保留。只有
    ``FileNotFoundError`` (可执行文件不存在) 会提前终止后续查询。

    Args:
        path: ffmpeg 可执行文件路径; None 时用 :func:`src.utils.get_ffmpeg_path`。
        timeout: 单个查询子进程的超时秒数。

    Returns:
        不可变 :class:`FfmpegCaps` 快照。
    """
    try:
        return _probe_impl(path=path, timeout=timeout)
    except Exception as exc:  # pragma: no cover - 最终兜底, 由单测覆盖部分分支
        return failed_caps(
            f"能力探测异常: {type(exc).__name__}: {exc}",
            ffmpeg_path=str(path or ""),
        )


def _probe_impl(path: Optional[str], timeout: float) -> FfmpegCaps:
    if path is not None:
        exe = str(path).strip()
    else:
        try:
            exe = get_ffmpeg_path()
        except Exception:
            exe = "ffmpeg"

    if not exe:
        return failed_caps("未配置 FFmpeg 路径", ffmpeg_path="")

    outputs: Dict[str, str] = {}
    errors = []

    stages = (
        ("-version", "version"),
        ("-encoders", "encoders"),
        ("-filters", "filters"),
        ("-hwaccels", "hwaccels"),
    )
    for flag, key in stages:
        try:
            outputs[key] = _run_flag(exe, flag, timeout)
        except FileNotFoundError:
            errors.append(f"找不到 FFmpeg 可执行文件: {exe}")
            break
        except subprocess.TimeoutExpired:
            errors.append(f"{flag} 探测超时 ({timeout:g} 秒)")
        except Exception as exc:
            errors.append(f"{flag} 探测失败: {type(exc).__name__}: {exc}")

    if not errors and not outputs:
        errors.append("未能获取 FFmpeg 能力信息")

    return FfmpegCaps(
        ffmpeg_path=exe,
        version=parse_version(outputs.get("version", "")),
        encoders=parse_encoders(outputs.get("encoders", "")),
        filters=parse_filters(outputs.get("filters", "")),
        hwaccels=parse_hwaccels(outputs.get("hwaccels", "")),
        probe_error="; ".join(errors) if errors else None,
        probed_at=time.monotonic(),
    )


# ----------------------------------------------------------------
# 进程级单例
# ----------------------------------------------------------------

_caps: Optional[FfmpegCaps] = None
_caps_lock = threading.Lock()


def get_capabilities(
    refresh: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> FfmpegCaps:
    """读取进程级能力快照; 无缓存或 ``refresh=True`` 时执行探测。

    探测期间不长时间持锁, 避免 UI 读缓存被后台探测阻塞。
    """
    global _caps

    if not refresh:
        with _caps_lock:
            cached = _caps
        if cached is not None:
            return cached

    caps = probe_ffmpeg(timeout=timeout)
    with _caps_lock:
        if refresh or _caps is None:
            _caps = caps
        return _caps


def set_capabilities(caps: Optional[FfmpegCaps]) -> None:
    """直接写入/清空单例 (测试注入、探测线程回写)。"""
    global _caps
    with _caps_lock:
        _caps = caps


def caps_ready() -> bool:
    """是否已有可用快照 (不触发探测, 供 UI 判断「正在检测…」/已就绪)。"""
    return _caps is not None
