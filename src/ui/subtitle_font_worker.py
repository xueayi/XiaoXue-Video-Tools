"""字体检查/快照的串行队列：新请求取消旧请求，仅接收最新代次。"""
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ..task.context import TaskContext, TaskCancelled, set_current_task, reset_current_task


_RUNNING_WORKERS = set()


class _Worker(QThread):
    result = pyqtSignal(int, object)

    def __init__(self, generation, work):
        super().__init__()  # No widget parent may destroy a running QThread.
        self.generation, self.work = generation, work
        self.context = TaskContext()

    def run(self):
        token = set_current_task(self.context)
        try:
            self.context.raise_if_cancelled()
            result = self.work()
        except TaskCancelled:
            return
        except Exception as exc:
            result = exc
        finally:
            reset_current_task(token)
        self.result.emit(self.generation, result)


class SubtitleJobQueue(QObject):
    completed = pyqtSignal(int, object)
    idle = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._active = None
        self._pending = None
        self._latest = None
        self._closed = False

    @property
    def busy(self):
        return self._active is not None

    def submit(self, generation, work):
        if self._closed:
            return
        self._latest = generation
        self._pending = generation, work
        if self._active:
            self._active.context.cancel()
        else:
            self._start()

    def _start(self):
        if self._closed or not self._pending:
            return
        generation, work = self._pending
        self._pending = None
        worker = _Worker(generation, work)
        self._active = worker
        _RUNNING_WORKERS.add(worker)
        worker.result.connect(self._receive)
        worker.finished.connect(lambda: self._finished(worker))
        worker.start()

    def _receive(self, generation, result):
        if not self._closed and generation == self._latest:
            self.completed.emit(generation, result)

    def _finished(self, worker):
        self._active = None
        _RUNNING_WORKERS.discard(worker)
        worker.deleteLater()
        if self._pending and not self._closed:
            self._start()
        else:
            self.idle.emit()

    def cancel(self):
        self._latest = None
        self._pending = None
        if self._active:
            self._active.context.cancel()

    def release(self):
        self._closed = True
        self.cancel()
