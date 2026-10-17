# -*- coding: utf-8 -*-
"""能力探测后台线程 (M3.1)。

启动时由主窗口创建一个 :class:`CapabilityProbeWorker`, 在 QThread 中调用
:func:`src.capabilities.ffmpeg_probe.get_capabilities`, 完成后把结果写回
进程级单例并发出 ``finished_caps``, UI 只负责刷新展示。

不在 UI 线程探测的原因: ffmpeg / ffprobe 在部分机器 (杀软扫描、冷启动、
损坏的二进制) 上会卡数秒, 同步调用会让主窗口白屏。
"""

from PyQt6.QtCore import QThread, pyqtSignal

from .ffmpeg_probe import (
    FfmpegCaps,
    failed_caps,
    get_capabilities,
    set_capabilities,
)


class CapabilityProbeWorker(QThread):
    """在后台线程探测 FFmpeg 能力。

    探测层本身保证不抛异常; 这里再做一层兜底: 任何意外都转成带
    ``probe_error`` 的空快照, 绝不让线程异常冒泡, 也不会让 UI 永远停在
    「正在检测…」。

    Signals:
        finished_caps: 探测结束 (参数为 :class:`FfmpegCaps`, 成功失败都有值)。
    """

    finished_caps = pyqtSignal(object)  # FfmpegCaps

    def __init__(self, timeout: float = 15.0, refresh: bool = True,
                 parent=None):
        super().__init__(parent)
        self._timeout = float(timeout)
        self._refresh = bool(refresh)

    def run(self):
        try:
            caps = get_capabilities(
                refresh=self._refresh, timeout=self._timeout)
            if not isinstance(caps, FfmpegCaps):
                caps = failed_caps("能力探测返回了无效结果")
            set_capabilities(caps)
        except Exception as exc:  # pragma: no cover - 防御分支, 单测可覆盖
            caps = failed_caps(f"能力探测异常: {type(exc).__name__}: {exc}")
            set_capabilities(caps)
        self.finished_caps.emit(caps)


def start_capability_probe(parent=None, timeout: float = 15.0,
                           refresh: bool = True) -> CapabilityProbeWorker:
    """创建并启动后台探测线程, 返回 worker 供调用方持有/防并发/关闭等待。

    Qt 的 QThread 不能在被销毁时仍处于运行状态, 调用方必须保留返回值
    (主窗口存在 ``_caps_worker``), 并在窗口关闭时 ``wait``。
    """
    worker = CapabilityProbeWorker(timeout=timeout, refresh=refresh,
                                   parent=parent)
    worker.start()
    return worker
