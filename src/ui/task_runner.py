# -*- coding: utf-8 -*-
"""异步任务执行器：在后台线程中运行 executor 函数。"""

import sys
import traceback

from PyQt6.QtCore import QThread, pyqtSignal


class _StreamRedirect:
    """将 write() 调用转发为 Qt 信号，用于捕获 print 输出。"""

    def __init__(self, signal):
        self._signal = signal

    def write(self, text):
        if text:
            self._signal.emit(str(text))

    def flush(self):
        pass


class TaskRunner(QThread):
    """在工作线程中运行指定的 handler(args)，并通过信号反馈日志和完成状态。"""

    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)  # (success, command_name)

    def __init__(self, handler, args, command_name, parent=None):
        super().__init__(parent)
        self.handler = handler
        self.args = args
        self.command_name = command_name

    def run(self):
        redirect = _StreamRedirect(self.log_signal)
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = redirect
        sys.stderr = redirect
        try:
            self.handler(self.args)
            self.finished_signal.emit(True, self.command_name)
        except Exception as e:
            self.log_signal.emit(f"\n{'=' * 50}\n")
            self.log_signal.emit(f"错误: {e}\n")
            self.log_signal.emit(traceback.format_exc())
            self.finished_signal.emit(False, self.command_name)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
