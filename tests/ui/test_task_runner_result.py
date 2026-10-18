# -*- coding: utf-8 -*-
"""TaskRunner 结果桥接与取消测试 (M2.1/M2.3)。

结果归一化测试直接在主线程调用 ``runner.run()``（不启动真实 QThread）；
取消测试使用真实 QThread + cancel_and_wait。
"""

import threading
import time

from src.task.context import TaskCancelled, TaskContext, current_task
from src.task.result import TaskResult
from src.task.status import TaskStatus
from src.ui.task_runner import TaskRunner


def _make_runner(handler, command="任务", context=None):
    runner = TaskRunner(handler, None, command, context=context)
    results = []
    finished = []
    logs = []
    runner.result_signal.connect(results.append)
    runner.finished_signal.connect(lambda ok, name: finished.append((ok, name)))
    runner.log_signal.connect(logs.append)
    return runner, results, finished, logs


# ----------------------------------------------------------------
# 归一化规则
# ----------------------------------------------------------------

def test_task_result_passthrough():
    result = TaskResult.partial("成功 1 个, 失败 1 个")
    runner, results, finished, _ = _make_runner(lambda args: result)
    runner.run()
    assert results == [result]
    # PARTIAL 不是 SUCCESS: 旧 bool 信号必须为 False
    assert finished == [(False, "任务")]


def test_int_zero_is_success():
    runner, results, finished, _ = _make_runner(lambda args: 0)
    runner.run()
    assert results[0].status is TaskStatus.SUCCESS
    assert results[0].exit_code == 0
    assert finished == [(True, "任务")]


def test_int_nonzero_is_failed_with_exit_code():
    runner, results, finished, _ = _make_runner(lambda args: 3)
    runner.run()
    result = results[0]
    assert result.status is TaskStatus.FAILED
    assert result.exit_code == 3
    assert "3" in result.message
    assert finished == [(False, "任务")]


def test_none_is_failed():
    """M2.2 起收紧: executor 必须返回 TaskResult, None 不再视为成功。"""
    runner, results, finished, _ = _make_runner(lambda args: None)
    runner.run()
    result = results[0]
    assert result.status is TaskStatus.FAILED
    assert "未返回结果" in result.message
    assert "TaskResult" not in result.message  # 界面不出现内部类型名
    assert finished == [(False, "任务")]


def test_bool_return_is_normalized():
    runner, results, _, _ = _make_runner(lambda args: True)
    runner.run()
    assert results[0].status is TaskStatus.SUCCESS

    runner, results, _, _ = _make_runner(lambda args: False, command="c")
    runner.run()
    assert results[0].status is TaskStatus.FAILED


def test_unknown_return_type_is_failed():
    runner, results, _, _ = _make_runner(lambda args: object())
    runner.run()
    result = results[0]
    assert result.status is TaskStatus.FAILED
    assert "无法识别" in result.message
    assert "object" not in result.message  # 不暴露 Python 类型名


# ----------------------------------------------------------------
# 异常 / 取消
# ----------------------------------------------------------------

def test_exception_is_failed_with_traceback():
    def boom(args):
        raise RuntimeError("炸了")

    runner, results, finished, logs = _make_runner(boom)
    runner.run()
    result = results[0]
    assert result.status is TaskStatus.FAILED
    # 界面只显示友好文案, 原始异常进日志与 details
    assert "任务执行出错" in result.message
    assert "炸了" not in result.message
    assert "炸了" in result.details["error"]
    assert "RuntimeError" in result.details["traceback"]
    assert finished == [(False, "任务")]
    joined = "".join(logs)
    assert "炸了" in joined and "Traceback" in joined


def test_task_cancelled_maps_to_cancelled():
    def handler(args):
        raise TaskCancelled("用户点了停止")

    runner, results, finished, _ = _make_runner(handler)
    runner.run()
    result = results[0]
    assert result.status is TaskStatus.CANCELLED
    assert result.message == "用户点了停止"
    assert finished == [(False, "任务")]


def test_request_cancel_sets_context_flag():
    context = TaskContext()
    runner = TaskRunner(lambda args: None, None, "c", context=context)
    assert runner.context is context
    runner.request_cancel()
    assert context.cancelled is True


def test_handler_sees_cancelled_context_and_can_abort():
    context = TaskContext()
    context.cancel()

    def handler(args):
        assert current_task() is context
        assert current_task().cancelled is True
        raise TaskCancelled()

    runner, results, _, _ = _make_runner(handler, context=context)
    runner.run()
    assert results[0].status is TaskStatus.CANCELLED


def test_default_context_is_created():
    runner = TaskRunner(lambda args: None, None, "c")
    assert isinstance(runner.context, TaskContext)


# ----------------------------------------------------------------
# ContextVar 生命周期
# ----------------------------------------------------------------

def test_current_task_reset_after_run():
    runner, _, _, _ = _make_runner(lambda args: current_task())
    # handler 内部能拿到 context（返回给 runner 后按未知类型归一为 FAILED）
    runner.run()
    assert current_task() is None


def test_current_task_reset_after_exception():
    def boom(args):
        assert current_task() is not None
        raise ValueError("x")

    runner, _, _, _ = _make_runner(boom)
    runner.run()
    assert current_task() is None


# ----------------------------------------------------------------
# 旧行为兼容
# ----------------------------------------------------------------

def test_log_signal_still_captures_print():
    runner, _, _, logs = _make_runner(lambda args: print("working"))
    runner.run()
    assert any("working" in chunk for chunk in logs)


def test_stream_redirect_restored_after_run():
    import sys

    before_out, before_err = sys.stdout, sys.stderr
    runner, _, _, _ = _make_runner(lambda args: 0)
    runner.run()
    assert sys.stdout is before_out
    assert sys.stderr is before_err


def test_normalize_direct_cases():
    assert TaskRunner._normalize(TaskResult.ok()).status is TaskStatus.SUCCESS
    failed = TaskRunner._normalize(7)
    assert failed.status is TaskStatus.FAILED and failed.exit_code == 7
    assert TaskRunner._normalize(None).status is TaskStatus.FAILED
    assert TaskRunner._normalize("x").status is TaskStatus.FAILED
    assert TaskRunner._normalize("x").status is TaskStatus.FAILED


# ----------------------------------------------------------------
# M2.3 取消链路
# ----------------------------------------------------------------

def test_request_cancel_triggers_registered_runner_cancel():
    class FakeHandle:
        def __init__(self):
            self.cancel_calls = 0

        def cancel(self):
            self.cancel_calls += 1

    context = TaskContext()
    handle = FakeHandle()
    context.register(handle)
    runner = TaskRunner(lambda args: None, None, "c", context=context)

    runner.request_cancel()

    assert context.cancelled is True
    assert handle.cancel_calls == 1


def test_cancel_and_wait_joins_thread(qapp):
    entered = threading.Event()

    def handler(args):
        entered.set()
        time.sleep(0.05)
        return 0

    runner = TaskRunner(handler, None, "c")
    runner.start()
    assert entered.wait(2.0)

    ok = runner.cancel_and_wait(5000)
    assert ok is True
    assert runner.isRunning() is False
    assert runner.context.cancelled is True


def test_default_context_uses_qprocess_runner_in_gui(qapp):
    from src.process.qprocess_runner import QProcessRunner

    runner = TaskRunner(lambda args: None, None, "c")
    created = runner.context.create_runner()
    assert isinstance(created, QProcessRunner)


def test_runner_uses_subprocess_backend_without_qapplication():
    """无 QApplication 时 (纯后端测试) 默认工厂退回 subprocess 后端。"""
    from src.process.subprocess_runner import SubprocessRunner
    from src.ui.task_runner import _default_runner_factory

    created = _default_runner_factory()
    # 测试进程存在 QApplication 时该断言不成立, 因此仅在无 app 时校验
    from PyQt6.QtWidgets import QApplication
    if QApplication.instance() is None:
        assert isinstance(created, SubprocessRunner)
    else:
        assert created is not None


# ----------------------------------------------------------------
# M2.5: 失败结果补齐 stderr_tail / exit_code / cancelled
# ----------------------------------------------------------------

NVENC_STDERR = (
    "[h264_nvenc @ 000001f4] No NVENC capable devices found\n",
    "Conversion failed!\n",
)


def test_failed_result_gets_stderr_tail_from_context():
    def handler(args):
        assert current_task() is not None
        current_task().extend_stderr(NVENC_STDERR)
        return TaskResult.failed("FFmpeg 退出码 1", exit_code=1)

    runner, results, _, _ = _make_runner(handler)
    runner.run()

    result = results[0]
    assert result.status is TaskStatus.FAILED
    assert result.details["exit_code"] == 1
    assert result.details["cancelled"] is False
    assert result.details["stderr_tail"] == "".join(NVENC_STDERR)


def test_explicit_stderr_tail_is_not_overwritten():
    explicit = "explicit stderr"

    def handler(args):
        current_task().append_stderr("context stderr\n")
        return TaskResult.failed(
            "失败", exit_code=2, details={"stderr_tail": explicit})

    runner, results, _, _ = _make_runner(handler)
    runner.run()
    assert results[0].details["stderr_tail"] == explicit


def test_cancelled_result_marks_cancelled_flag():
    def handler(args):
        raise TaskCancelled("用户点了停止")

    runner, results, _, _ = _make_runner(handler)
    runner.run()
    result = results[0]
    assert result.status is TaskStatus.CANCELLED
    assert result.details["cancelled"] is True


def test_success_result_details_untouched():
    runner, results, _, _ = _make_runner(lambda args: TaskResult.ok())
    runner.run()
    assert results[0].details == {}


def test_exception_result_gets_stderr_tail():
    def handler(args):
        current_task().extend_stderr(NVENC_STDERR)
        raise RuntimeError("boom")

    runner, results, _, _ = _make_runner(handler)
    runner.run()
    result = results[0]
    assert result.status is TaskStatus.FAILED
    assert "No NVENC capable devices found" in result.details["stderr_tail"]


def test_core_streaming_stderr_flows_to_result():
    """端到端: core.run_ffmpeg_streaming -> TaskContext -> TaskResult.details。"""
    import src.core as core
    from src.process import CompletedProcess
    from src.ffmpeg.errors import ErrorCategory, classify

    class FakeRunner:
        def __init__(self):
            self.on_stdout = None
            self.on_stderr = None
            self.on_finished = None

        def start(self, cmd, *, cwd=None, env=None, stdin_pipe=False):
            for line in NVENC_STDERR:
                if self.on_stderr is not None:
                    self.on_stderr(line)

        def wait(self, timeout=None):
            return CompletedProcess(exit_code=1)

        def cancel(self):
            pass

        def is_running(self):
            return False

        @property
        def exit_code(self):
            return 1

    class FakeEncodingTabArgs:
        input = ""

    def handler(args):
        completed = core.run_ffmpeg_streaming(
            ["ffmpeg", "-i", "in.mp4", "out.mp4"],
            on_log=lambda _line: None,
        )
        return TaskResult.failed(
            f"FFmpeg 退出码 {completed.exit_code}",
            exit_code=completed.exit_code,
        )

    context = TaskContext(runner_factory=FakeRunner)
    runner = TaskRunner(handler, None, "视频压制", context=context)
    results = []
    runner.result_signal.connect(results.append)
    runner.run()

    result = results[0]
    classified = classify(result.details["stderr_tail"], result.exit_code)
    assert classified.category is ErrorCategory.ENCODER_UNAVAILABLE
    assert result.exit_code == 1
