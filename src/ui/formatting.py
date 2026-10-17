# -*- coding: utf-8 -*-
"""纯 Python 格式化辅助 —— 时长 / 剩余时间 / 文件大小 / 速度 / 百分比。

本模块无 Qt 依赖，也不 import 既有 UI 实现：
格式化口径参考 ``encode_tab._fmt_dur`` 与 ``progress_dashboard._fmt_eta``，
但作为唯一实现集中在这里，供任务卡、执行摘要、首页等复用。
"""

import math
from typing import Optional

_DASH = "--"
_DURATION_DASH = "--:--:--"

# 文件大小单位 (1024 进制)
_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def _as_seconds(seconds) -> Optional[float]:
    """把输入归一为非负秒数；None / NaN / 负数 → None。"""
    if seconds is None:
        return None
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or value < 0:
        return None
    return value


def fmt_duration(seconds) -> str:
    """秒数 → ``"HH:MM:SS"`` (小时不截断)；未知/非法 → ``"--:--:--"``。"""
    value = _as_seconds(seconds)
    if value is None:
        return _DURATION_DASH
    total = int(value)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def fmt_eta(seconds: Optional[float]) -> str:
    """剩余时间 (紧凑格式)：不足 1 小时 → ``"MM:SS"``，否则 ``"H:MM:SS"``。

    未知/非法 (None / NaN / 负数) → ``"--"``，与旧仪表盘口径一致。
    """
    value = _as_seconds(seconds)
    if value is None:
        return _DASH
    total = int(value)
    if total >= 3600:
        hours, rest = divmod(total, 3600)
        minutes, secs = divmod(rest, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def fmt_size(num_bytes) -> str:
    """字节数 → 人类可读大小 (1024 进制，保留 1 位小数)；未知/负数 → ``"--"``。

    例: ``0 → "0 B"``, ``1536 → "1.5 KB"``, ``1073741824 → "1.0 GB"``。
    """
    if num_bytes is None:
        return _DASH
    try:
        value = float(num_bytes)
    except (TypeError, ValueError):
        return _DASH
    if math.isnan(value) or value < 0:
        return _DASH
    if value < 1024:
        return f"{int(value)} B"
    for unit in _SIZE_UNITS[1:]:
        value /= 1024
        if value < 1024 or unit == _SIZE_UNITS[-1]:
            return f"{value:.1f} {unit}"
    return _DASH  # pragma: no cover - 循环必然 return


def fmt_speed(speed) -> str:
    """编码速度 → ``"1.85x"``；未知/非正数 → ``"--"``。"""
    if speed is None:
        return _DASH
    try:
        value = float(speed)
    except (TypeError, ValueError):
        return _DASH
    if math.isnan(value) or value <= 0:
        return _DASH
    return f"{value:.2f}x"


def fmt_percent(progress) -> str:
    """进度 (0–100) → ``"42.5%"``；未知 → ``"--"``。"""
    if progress is None:
        return _DASH
    try:
        value = float(progress)
    except (TypeError, ValueError):
        return _DASH
    if math.isnan(value):
        return _DASH
    return f"{value:.1f}%"
