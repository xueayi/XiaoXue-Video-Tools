# -*- coding: utf-8 -*-
"""FFmpeg 输出进度解析器 —— 从 stderr 行中提取 frame/fps/time/speed 等指标。"""

import re
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class ProgressInfo:
    """FFmpeg 进度快照。"""
    frame: int = 0
    fps: float = 0.0
    size_kb: int = 0
    time_sec: float = 0.0
    bitrate_kbps: float = 0.0
    speed: float = 0.0
    total_duration: float = 0.0
    percent: float = 0.0
    eta_sec: float = -1.0


_DURATION_RE = re.compile(r'Duration:\s*(\d{2}):(\d{2}):(\d{2})\.(\d+)')
_TIME_RE = re.compile(r'time=\s*(\d{2}):(\d{2}):(\d{2})\.(\d+)')
_FRAME_RE = re.compile(r'frame=\s*(\d+)')
_FPS_RE = re.compile(r'fps=\s*([\d.]+)')
_SIZE_RE = re.compile(r'size=\s*(\d+)\s*kB')
_BITRATE_RE = re.compile(r'bitrate=\s*([\d.]+)\s*kbits/s')
_SPEED_RE = re.compile(r'speed=\s*([\d.]+)x')


def _hms_to_sec(h: str, m: str, s: str, frac: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(frac) / (10 ** len(frac))


class FFmpegProgressParser(QObject):
    """实时解析 FFmpeg 输出行，发出结构化进度信号。

    用法：
        parser = FFmpegProgressParser()
        parser.set_duration(120.0)  # 可选，若已知总时长
        log_signal.connect(parser.feed_line)
        parser.progress_updated.connect(dashboard.update_metrics)
    """

    progress_updated = pyqtSignal(object)  # ProgressInfo

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info = ProgressInfo()

    def set_duration(self, seconds: float):
        self._info.total_duration = seconds

    def reset(self):
        self._info = ProgressInfo()

    def feed_line(self, line: str):
        """喂入一行 FFmpeg 输出，解析并按需发信号。"""
        if not line:
            return

        # 尝试从 FFmpeg 的 header 行解析 Duration
        if self._info.total_duration <= 0:
            dm = _DURATION_RE.search(line)
            if dm:
                self._info.total_duration = _hms_to_sec(*dm.groups())

        updated = False

        tm = _TIME_RE.search(line)
        if tm:
            self._info.time_sec = _hms_to_sec(*tm.groups())
            updated = True

        fm = _FRAME_RE.search(line)
        if fm:
            self._info.frame = int(fm.group(1))

        fpsr = _FPS_RE.search(line)
        if fpsr:
            try:
                self._info.fps = float(fpsr.group(1))
            except ValueError:
                pass

        sm = _SIZE_RE.search(line)
        if sm:
            self._info.size_kb = int(sm.group(1))

        bm = _BITRATE_RE.search(line)
        if bm:
            try:
                self._info.bitrate_kbps = float(bm.group(1))
            except ValueError:
                pass

        spm = _SPEED_RE.search(line)
        if spm:
            try:
                self._info.speed = float(spm.group(1))
            except ValueError:
                pass

        if updated:
            self._calc_derived()
            self.progress_updated.emit(self._info)

    def _calc_derived(self):
        info = self._info
        if info.total_duration > 0 and info.time_sec >= 0:
            info.percent = min(info.time_sec / info.total_duration * 100, 100.0)
        else:
            info.percent = 0.0

        if info.speed > 0 and info.total_duration > 0:
            remaining = info.total_duration - info.time_sec
            info.eta_sec = max(remaining / info.speed, 0.0)
        else:
            info.eta_sec = -1.0
