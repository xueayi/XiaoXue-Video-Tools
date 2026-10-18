# -*- coding: utf-8 -*-
"""异步任务执行器：在后台线程中运行 executor 函数。"""

import os
import sys
import traceback
from dataclasses import replace

from PyQt6.QtCore import QThread, pyqtSignal

from ..task.context import (
    TaskCancelled,
    TaskContext,
    reset_current_task,
    set_current_task,
)
from ..task.result import TaskResult
from ..task.status import TaskStatus


def _default_runner_factory():
    """解析 GUI 默认 runner 工厂。

    GUI 环境（存在 QApplication）使用 QProcess 后端，使 UI 取消可通过
    TaskContext 触达真实进程；纯后端测试（无 QApplication）退回 subprocess。
    """
    from PyQt6.QtWidgets import QApplication

    if QApplication.instance() is None:
        from ..process.subprocess_runner import SubprocessRunner

        return SubprocessRunner()
    from ..process.qprocess_runner import QProcessRunner

    return QProcessRunner()


def default_duration_probe(input_path: str):
    """worker 线程内的时长预取：ffprobe (media_probe 已带超时与取消检查)。

    Returns:
        总时长（秒，float）或 None（探测失败/无时长）。异常由调用方吞掉。
    """
    from ..media_probe import probe_detailed

    info = probe_detailed(input_path)
    if info is None:
        return None
    return getattr(info, "duration_sec", 0.0) or None


#: 各页面 build_args() 中可能承载「主输入媒体」的属性名（按优先级）
_INPUT_PATH_ATTRS = ("input", "video_input", "extract_input", "remux_input")


def resolve_input_path(args) -> str:
    """从页面 args 中解析用于时长预取的单个输入媒体路径。

    兼容各页面 build_args() 的不同属性名；批量输入（``; `` 分隔字符串或
    列表多项）返回空串 —— 逐文件时长不同，用单一时长算 percent 会误导用户。
    """
    if args is None:
        return ""
    for attribute in _INPUT_PATH_ATTRS:
        value = getattr(args, attribute, "")
        if isinstance(value, (list, tuple)):
            if len(value) != 1:
                continue
            value = value[0]
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text:
            continue
        if ";" in text:
            return ""  # 批量输入: 不预取单文件时长
        return text
    return ""


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
    """在工作线程中运行指定的 handler(args)，并通过信号反馈日志、进度和任务结果。

    结果通道：
        * ``result_signal(TaskResult)`` —— 新主路径；
        * ``finished_signal(bool, str)`` —— 兼容旧 UI 的薄通道（仅 SUCCESS 为 True）。

    进度通道 (M2.4)：
        * ``progress_signal(str)`` —— ffmpeg ``-progress`` 的 stdout 原始行
          （经 ``TaskContext.progress_callback`` 从 core 转发，主窗口解析成
          percent/ETA 后驱动任务卡）；
        * ``duration_signal(float)`` —— 任务开始前在工作线程用 ffprobe
          (带超时) 预取的总时长，主窗口据此设置进度解析器时长；
          预取失败不发信号（进度条退化为不确定态）。

    取消：
        ``request_cancel()`` 置 ``TaskContext.cancelled`` 并触发已注册子进程
        runner 的 ``cancel()``；具体 terminate/kill 时序由 runner 的 wait()
        在工作线程内推进，UI 线程不被阻塞。

    错误归因 (M2.5)：
        ``core.run_ffmpeg_streaming`` 把 stderr 尾部写入 ``TaskContext``；
        runner 在发送结果前补齐 FAILED 结果的
        ``details['stderr_tail'] / details['exit_code'] / details['cancelled']``，
        UI 据此生成 ``UserFacingError`` 并展示错误卡片。
    """

    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str)    # ffmpeg -progress 的 stdout 行
    duration_signal = pyqtSignal(float)  # ffprobe 预取的总时长 (秒)
    result_signal = pyqtSignal(object)  # TaskResult
    finished_signal = pyqtSignal(bool, str)  # (legacy_success, command_name)

    def __init__(self, handler, args, command_name, parent=None, context=None,
                 duration_probe=None):
        super().__init__(parent)
        self.handler = handler
        self.args = args
        self.command_name = command_name
        self.context = (
            context if context is not None
            else TaskContext(runner_factory=_default_runner_factory)
        )
        # 时长探测函数 (input_path -> seconds|None)；测试可注入 fake
        self._duration_probe = (
            duration_probe if duration_probe is not None
            else default_duration_probe
        )
        self._duration_probed = False

    # ----------------------------------------------------------------
    # 取消
    # ----------------------------------------------------------------

    def request_cancel(self) -> None:
        """请求取消：置标志并触发已登记 runner.cancel()（立即返回）。"""
        self.context.cancel()

    def cancel_and_wait(self, timeout_ms: int = 5000) -> bool:
        """请求取消并有限等待工作线程结束（closeEvent 使用）。"""
        self.request_cancel()
        return self.wait(timeout_ms)

    # ----------------------------------------------------------------
    # 时长预取 / 进度转发 (worker 线程)
    # ----------------------------------------------------------------

    def _probe_duration(self):
        """在 worker 线程用 ffprobe 预取输入时长；只尝试一次，失败返回 None。"""
        if self._duration_probed:
            return None
        self._duration_probed = True
        plan = getattr(self.args, "clip_plan", None)
        if plan is not None:
            try:
                plan.validate()
            except ValueError:
                return None
            return plan.total_duration_us / 1_000_000
        input_path = resolve_input_path(self.args)
        if not input_path or not os.path.isfile(input_path):
            return None
        try:
            seconds = self._duration_probe(input_path)
        except TaskCancelled:
            raise
        except Exception:  # noqa: BLE001 - 预取失败不得影响任务执行
            return None
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            return None
        return seconds if seconds > 0 else None

    def _emit_progress(self, line) -> None:
        """进度通道：stdout 进度行 -> Qt 信号（任意线程 emit 安全）。"""
        if isinstance(line, str) and line:
            self.progress_signal.emit(line)

    # ----------------------------------------------------------------
    # 结果归一化
    # ----------------------------------------------------------------

    @classmethod
    def _normalize(cls, ret) -> TaskResult:
        """把 handler 返回值归一为 TaskResult。

        规则（M2.2 起收紧）：
            * TaskResult 原样返回；
            * None -> FAILED（executor 必须返回 TaskResult）；
            * int: 0 -> SUCCESS；非 0 -> FAILED(exit_code=ret)（兜底兼容）；
            * bool: True -> SUCCESS；False -> FAILED（int 子类，先显式处理）；
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
            return TaskResult.failed("executor 未返回 TaskResult")
        return TaskResult.failed(
            f"executor 返回未知类型: {type(ret).__name__}")

    def _build_result(self) -> TaskResult:
        """在任务 ContextVar 内预取时长、执行 handler 并归一结果。"""
        token = set_current_task(self.context)
        try:
            duration = self._probe_duration()
            if duration is not None:
                self.duration_signal.emit(duration)
            return self._normalize(self.handler(self.args))
        except TaskCancelled as exc:
            return TaskResult.cancelled(str(exc) or "任务已取消")
        finally:
            reset_current_task(token)

    def _enrich_result(self, result: TaskResult) -> TaskResult:
        """用 TaskContext 补齐失败结果的错误归因字段 (M2.5)。

        * FAILED: ``details['stderr_tail']``（core 写入的最近 stderr）、
          ``details['exit_code']``、``details['cancelled'] = False``；
        * CANCELLED: ``details['cancelled'] = True``，供错误分类优先判定取消。

        executor 已经显式写入的 details 优先，不覆盖。
        """
        if not isinstance(result, TaskResult):
            return result
        details = dict(result.details)
        if result.status is TaskStatus.FAILED:
            stderr_tail = self.context.stderr_text
            if stderr_tail and not details.get("stderr_tail"):
                details["stderr_tail"] = stderr_tail
            if result.exit_code is not None:
                details.setdefault("exit_code", result.exit_code)
            details.setdefault("cancelled", False)
        elif result.status is TaskStatus.CANCELLED:
            details.setdefault("cancelled", True)
        else:
            return result
        if details == dict(result.details):
            return result
        return replace(result, details=details)

    # ----------------------------------------------------------------
    # 线程体
    # ----------------------------------------------------------------

    def run(self):
        redirect = _StreamRedirect(self.log_signal)
        old_stdout, old_stderr = sys.stdout, sys.stderr
        old_progress_callback = self.context.progress_callback
        sys.stdout = redirect
        sys.stderr = redirect
        self.context.progress_callback = self._emit_progress
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
            self.context.progress_callback = old_progress_callback
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        result = self._enrich_result(result)
        self.result_signal.emit(result)
        # 兼容旧 bool 槽：仅 SUCCESS 为 True（PARTIAL / CANCELLED 不算成功）
        self.finished_signal.emit(result.legacy_success, self.command_name)
