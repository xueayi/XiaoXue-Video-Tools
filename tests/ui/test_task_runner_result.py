# -*- coding: utf-8 -*-
"""TaskRunner 结果桥接测试 (M2.1)。

全部直接在主线程调用 ``runner.run()``，不启动真实 QThread、不依赖事件循环：
signal 为同线程直连，收集列表同步即可断言。
"""

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


def test_none_is_success_with_transition_warning():
    runner, results, finished, _ = _make_runner(lambda args: None)
    runner.run()
    result = results[0]
    assert result.status is TaskStatus.SUCCESS
    assert any("过渡兼容" in warning for warning in result.warnings)
    assert finished == [(True, "任务")]


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
    assert "未知" in result.message


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
    assert "炸了" in result.message
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
    assert TaskRunner._normalize(None).status is TaskStatus.SUCCESS
    assert TaskRunner._normalize("x").status is TaskStatus.FAILED
