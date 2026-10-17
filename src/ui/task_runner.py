# -*- coding: utf-8 -*-
"""异步任务执行器：在后台线程中运行 executor 函数。"""

import sys
import traceback

from PyQt6.QtCore import QThread, pyqtSignal

from ..task.context import (
    TaskCancelled,
    TaskContext,
    reset_current_task,
    set_current_task,
)
from ..task.result import TaskResult

#: 过渡期 None 返回值产生的警告（M2.2 收紧为 FAILED 后删除）
_NONE_RETURN_WARNING = "executor 未返回 TaskResult（过渡兼容）"


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
    """在工作线程中运行指定的 handler(args)，并通过信号反馈日志和任务结果。

    结果通道：
        * ``result_signal(TaskResult)`` —— 新主路径；
        * ``finished_signal(bool, str)`` —— 兼容旧 UI 的薄通道（仅 SUCCESS 为 True）。

    取消：
        ``request_cancel()`` 目前只置 ``TaskContext.cancelled`` 标志
        （M2.3 再接入子进程 terminate/kill）。
    """

    log_signal = pyqtSignal(str)
    result_signal = pyqtSignal(object)  # TaskResult
    finished_signal = pyqtSignal(bool, str)  # (legacy_success, command_name)

    def __init__(self, handler, args, command_name, parent=None, context=None):
        super().__init__(parent)
        self.handler = handler
        self.args = args
        self.command_name = command_name
        self.context = context if context is not None else TaskContext()

    # ----------------------------------------------------------------
    # 取消
    # ----------------------------------------------------------------

    def request_cancel(self) -> None:
        """请求协作式取消（只置标志，M2.3 再接进程终止）。"""
        self.context.cancel()

    # ----------------------------------------------------------------
    # 结果归一化
    # ----------------------------------------------------------------

    @classmethod
    def _normalize(cls, ret) -> TaskResult:
        """把 handler 返回值归一为 TaskResult。

        过渡兼容规则（M2.1）：
            * TaskResult 原样返回；
            * int: 0 -> SUCCESS；非 0 -> FAILED(exit_code=ret)；
            * None -> SUCCESS + 过渡警告（TODO(M2.2) 收紧为 FAILED）；
            * 其它类型 -> FAILED。
        """
        if isinstance(ret, TaskResult):
            return ret
        if isinstance(ret, bool):
            # bool 是 int 子类，先显式处理，避免 True/False 被当成 1/0 语义
            return TaskResult.ok() if ret else TaskResult.failed("executor 返回失败")
        if isinstance(ret, int):
            if ret == 0:
                return TaskResult.ok()
            return TaskResult.failed(f"任务失败 (exit_code={ret})", exit_code=ret)
        if ret is None:
            return TaskResult.ok(warnings=(_NONE_RETURN_WARNING,))
        return TaskResult.failed(
            f"executor 返回未知类型: {type(ret).__name__}")

    def _build_result(self) -> TaskResult:
        """在任务 ContextVar 内执行 handler 并归一结果。"""
        token = set_current_task(self.context)
        try:
            return self._normalize(self.handler(self.args))
        except TaskCancelled as exc:
            return TaskResult.cancelled(str(exc) or "任务已取消")
        finally:
            reset_current_task(token)

    # ----------------------------------------------------------------
    # 线程体
    # ----------------------------------------------------------------

    def run(self):
        redirect = _StreamRedirect(self.log_signal)
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = redirect
        sys.stderr = redirect
        try:
            result = self._build_result()
        except Exception as exc:
            traceback_text = traceback.format_exc()
            self.log_signal.emit(f"\n{'=' * 50}\n")
            self.log_signal.emit(f"错误: {exc}\n")
            self.log_signal.emit(traceback_text)
            result = TaskResult.failed(
                str(exc), details={"traceback": traceback_text})
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        self.result_signal.emit(result)
        # 兼容旧 bool 槽：仅 SUCCESS 为 True（PARTIAL / CANCELLED 不算成功）
        self.finished_signal.emit(result.legacy_success, self.command_name)
