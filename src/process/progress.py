# -*- coding: utf-8 -*-
"""FFmpeg 结构化进度解析与 ``-progress`` 注入（M2.4）。

数据通道：
    ``ffmpeg -progress pipe:1 -nostats -stats_period 0.5`` 会把进度以
    ``key=value`` 逐行写入 **stdout**（stderr 仍保留日志/错误信息）。
    本模块提供：

    * :class:`ProgressEvent` —— 不可变进度快照（percent / ETA 由 ffprobe 时长推导）；
    * :class:`FFmpegProgressParser` —— 纯 Python 解析器，``feed_line`` 返回事件；
    * :func:`inject_progress` —— 在输出路径前注入进度参数（幂等、仅 ffmpeg）。

约定：
    * ffmpeg 的 ``out_time_ms`` 字段实际单位是**微秒**（历史遗留命名，与
      ``out_time_us`` 数值相同），因此按微秒解析；同时兼容 ``out_time_us``
      与 ``out_time``（``HH:MM:SS.xxxxxx``）。
    * 一个进度块以 ``progress=continue|end`` 结束；解析器只在块结束时返回事件，
      其余行返回 ``None``（``N/A``、未知键、乱行均忽略）。
    * duration 未知时不计算 ``percent`` / ``eta_seconds``（返回 ``None``）；
      ``progress=end`` 时 percent 固定 100。
"""

import os
from dataclasses import dataclass
from typing import Optional, Sequence

#: 注入 ffmpeg 的进度参数（放在输出路径前）
PROGRESS_ARGS = ("-progress", "pipe:1", "-nostats", "-stats_period", "0.5")

#: 进度块结束标记
PROGRESS_CONTINUE = "continue"
PROGRESS_END = "end"

#: 已知但无需处理的键（避免误判为未知行）
_IGNORED_KEYS = frozenset({
    "stream_0_0_q", "dup_frames", "drop_frames",
})

_KNOWN_KEYS = frozenset({
    "frame", "fps", "out_time_ms", "out_time_us", "out_time",
    "speed", "bitrate", "total_size", "progress",
})

_MICROSECONDS_PER_SECOND = 1_000_000


@dataclass(frozen=True)
class ProgressEvent:
    """一次完整的 FFmpeg 进度块快照。"""

    frame: int = 0
    fps: float = 0.0
    #: 已编码时长。字段名沿用 ffmpeg 的 ``out_time_ms``，但**单位是微秒**
    #: （与 ``out_time_us`` 等值），见模块文档。
    out_time_ms: int = 0
    speed: float = 0.0
    #: 原始码率字符串（如 ``"1234.5kbits/s"``；N/A 时为空串）
    bitrate: str = ""
    total_size: int = 0
    #: "continue" / "end" / ""（原始 progress 值）
    progress: str = ""
    #: 0-100；duration 未知且未结束时为 None
    percent: Optional[float] = None
    #: 剩余秒数；duration 未知或 speed<=0 时为 None
    eta_seconds: Optional[float] = None


def _parse_int(value: str) -> Optional[int]:
    """解析整数值；``N/A`` 或非法内容返回 None。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: str) -> Optional[float]:
    """解析浮点值；``N/A`` 或非法内容返回 None。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time_to_us(value: str) -> Optional[int]:
    """``HH:MM:SS.ffffff`` -> 微秒；非法内容返回 None。"""
    parts = value.split(":")
    if len(parts) != 3:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    except (TypeError, ValueError):
        return None
    total_sec = hours * 3600 + minutes * 60 + seconds
    return int(round(total_sec * _MICROSECONDS_PER_SECOND))


class FFmpegProgressParser:
    """解析 ffmpeg ``-progress pipe:1`` 输出行，生成 :class:`ProgressEvent`。

    用法::

        parser = FFmpegProgressParser()
        parser.set_duration(120.0)          # 可选：ffprobe 预取的时长
        for line in progress_lines():
            event = parser.feed_line(line)  # 块结束时返回事件
            if event is not None:
                update_ui(event.percent, event.speed, event.eta_seconds)
    """

    def __init__(self) -> None:
        self._duration: Optional[float] = None
        self._frame = 0
        self._fps = 0.0
        self._out_time_us = 0
        self._speed = 0.0
        self._bitrate = ""
        self._total_size = 0
        self._progress = ""

    # ----------------------------------------------------------------
    # 配置 / 重置
    # ----------------------------------------------------------------

    @property
    def duration(self) -> Optional[float]:
        """当前已知的总时长（秒）；未知为 None。"""
        return self._duration

    def set_duration(self, seconds) -> None:
        """设置总时长（秒）；非正数/非法值视为未知（None）。"""
        value = _parse_float(seconds)
        self._duration = value if value is not None and value > 0 else None

    def reset(self) -> None:
        """清空累加状态与时长（用于开始下一个任务）。"""
        self._duration = None
        self._frame = 0
        self._fps = 0.0
        self._out_time_us = 0
        self._speed = 0.0
        self._bitrate = ""
        self._total_size = 0
        self._progress = ""

    # ----------------------------------------------------------------
    # 解析
    # ----------------------------------------------------------------

    def feed_line(self, line: str) -> Optional[ProgressEvent]:
        """喂入一行输出；仅在一个进度块结束时返回 :class:`ProgressEvent`。

        非 ``key=value`` 行、未知键、``N/A``、乱行均返回 None。
        """
        if not line:
            return None
        text = line.strip()
        if not text or "=" not in text:
            return None
        key, _, raw_value = text.partition("=")
        key = key.strip().lower()
        value = raw_value.strip()

        if key in _IGNORED_KEYS:
            return None
        if key not in _KNOWN_KEYS:
            return None
        if not value or value.upper() == "N/A":
            return None

        if key == "frame":
            parsed = _parse_int(value)
            if parsed is not None:
                self._frame = parsed
        elif key == "fps":
            parsed = _parse_float(value)
            if parsed is not None:
                self._fps = parsed
        elif key in ("out_time_ms", "out_time_us"):
            parsed = _parse_int(value)
            if parsed is not None:
                self._out_time_us = parsed
        elif key == "out_time":
            parsed = _parse_time_to_us(value)
            if parsed is not None:
                self._out_time_us = parsed
        elif key == "speed":
            parsed = _parse_float(value.rstrip("xX"))
            if parsed is not None:
                self._speed = parsed
        elif key == "bitrate":
            self._bitrate = value
        elif key == "total_size":
            parsed = _parse_int(value)
            if parsed is not None:
                self._total_size = parsed
        elif key == "progress":
            return self._build_event(value)
        return None

    # ----------------------------------------------------------------
    # 事件推导
    # ----------------------------------------------------------------

    def _build_event(self, progress_value: str) -> ProgressEvent:
        self._progress = progress_value
        out_time_sec = self._out_time_us / _MICROSECONDS_PER_SECOND
        percent: Optional[float] = None
        eta: Optional[float] = None
        if self._duration is not None:
            percent = min(out_time_sec / self._duration * 100.0, 100.0)
            if self._speed > 0:
                remaining = max(self._duration - out_time_sec, 0.0)
                eta = remaining / self._speed
        if progress_value == PROGRESS_END:
            percent = 100.0
            eta = 0.0
        return ProgressEvent(
            frame=self._frame,
            fps=self._fps,
            out_time_ms=self._out_time_us,
            speed=self._speed,
            bitrate=self._bitrate,
            total_size=self._total_size,
            progress=progress_value,
            percent=percent,
            eta_seconds=eta,
        )


def _looks_like_ffmpeg(cmd: Sequence[str]) -> bool:
    """命令是否指向 ffmpeg 本体（支持 ffmpeg.exe / 绝对路径）。"""
    if not cmd:
        return False
    executable = os.path.basename(str(cmd[0])).lower()
    if executable.endswith(".exe"):
        executable = executable[:-4]
    return executable == "ffmpeg"


def inject_progress(cmd: Sequence[str]) -> list:
    """在 ffmpeg 命令的输出路径前注入 ``-progress pipe:1 -nostats -stats_period 0.5``。

    规则：
        * 仅 ffmpeg 命令注入（非 ffmpeg 原样返回）；
        * 已包含 ``-progress`` 时原样返回（幂等，不重复注入）；
        * 输出路径按约定是最后一个参数，参数插到它前面。

    Args:
        cmd: 命令列表（不会被原地修改）。

    Returns:
        新的命令列表。
    """
    result = [str(part) for part in cmd]
    if not _looks_like_ffmpeg(result):
        return result
    if "-progress" in result:
        return result
    if len(result) < 2:
        return result
    return result[:-1] + list(PROGRESS_ARGS) + result[-1:]
