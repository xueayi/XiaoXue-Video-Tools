"""在后台运行有超时的 ffprobe，结果由主线程按输入代次接收。"""
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from ..media_probe import DetailedMediaInfo


class _Signals(QObject):
    finished = pyqtSignal(object)


class _Probe(QRunnable):
    def __init__(self, path, generation, callback, probe):
        super().__init__()
        self.path, self.generation, self.probe = path, generation, probe
        self.signals = _Signals()
        self.signals.finished.connect(callback)

    def run(self):
        try:
            info = self.probe(self.path)
        except Exception as exc:
            info = DetailedMediaInfo(self.path, errors=[str(exc)])
        self.signals.finished.emit((self.path, self.generation, info))


def start_media_probe(path, generation, callback, probe):
    QThreadPool.globalInstance().start(_Probe(path, generation, callback, probe))
