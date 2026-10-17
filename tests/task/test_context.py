# -*- coding: utf-8 -*-
"""TaskContext 测试：取消标志、回调、句柄占位、ContextVar 帮助函数。"""

import pytest

from src.task.context import (
    TaskCancelled,
    TaskContext,
    current_task,
    reset_current_task,
    set_current_task,
)


def test_context_starts_uncancelled():
    context = TaskContext()
    assert context.cancelled is False
    assert context.request_cancel_callbacks == ()
    assert context.handles == ()


def test_cancel_sets_flag_and_is_idempotent():
    context = TaskContext()
    context.cancel()
    assert context.cancelled is True
    context.cancel()  # 重复取消无副作用
    assert context.cancelled is True


def test_cancel_callbacks_run_once():
    context = TaskContext()
    calls = []
    context.add_cancel_callback(lambda: calls.append("a"))
    context.add_cancel_callback(lambda: calls.append("b"))

    assert len(context.request_cancel_callbacks) == 2
    context.cancel()
    context.cancel()
    assert calls == ["a", "b"]


def test_cancel_callback_exception_is_swallowed():
    context = TaskContext()

    def boom():
        raise RuntimeError("回调炸了")

    called = []
    context.add_cancel_callback(boom)
    context.add_cancel_callback(lambda: called.append(True))
    context.cancel()  # 不向外抛
    assert called == [True]
    assert context.cancelled is True


def test_raise_if_cancelled():
    context = TaskContext()
    context.raise_if_cancelled()  # 未取消 -> 不抛

    context.cancel()
    with pytest.raises(TaskCancelled) as excinfo:
        context.raise_if_cancelled()
    assert "取消" in str(excinfo.value)


def test_task_cancelled_is_exception():
    assert issubclass(TaskCancelled, Exception)
    assert "取消" in str(TaskCancelled())


def test_register_unregister_by_identity():
    context = TaskContext()
    first, second = object(), object()
    context.register(first)
    context.register(second)
    assert context.handles == (first, second)

    context.unregister(first)
    assert context.handles == (second,)
    context.unregister(first)  # 重复注销无副作用
    context.unregister(object())  # 未登记对象无副作用
    assert context.handles == (second,)


def test_current_task_contextvar_roundtrip():
    assert current_task() is None
    context = TaskContext()
    token = set_current_task(context)
    try:
        assert current_task() is context
        nested = TaskContext()
        nested_token = set_current_task(nested)
        assert current_task() is nested
        reset_current_task(nested_token)
        assert current_task() is context
    finally:
        reset_current_task(token)
    assert current_task() is None


# ----------------------------------------------------------------
# stderr 尾部缓冲 (M2.5 错误归因)
# ----------------------------------------------------------------

def test_stderr_buffer_starts_empty():
    context = TaskContext()
    assert context.stderr_lines == ()
    assert context.stderr_text == ""


def test_stderr_buffer_append_and_text():
    context = TaskContext()
    context.append_stderr("[h264_nvenc @ 0] No NVENC capable devices found\n")
    context.append_stderr("Conversion failed!\n")
    assert context.stderr_lines == (
        "[h264_nvenc @ 0] No NVENC capable devices found\n",
        "Conversion failed!\n",
    )
    assert "[h264_nvenc" in context.stderr_text
    assert context.stderr_text.endswith("Conversion failed!\n")


def test_stderr_buffer_ignores_empty_lines():
    context = TaskContext()
    context.append_stderr("")
    context.append_stderr(None)
    assert context.stderr_lines == ()


def test_stderr_buffer_is_ring_buffer():
    context = TaskContext(stderr_tail_lines=3)
    context.extend_stderr(f"line{i}\n" for i in range(5))
    assert context.stderr_lines == ("line2\n", "line3\n", "line4\n")


def test_stderr_buffer_extend_none_and_empty_are_noops():
    context = TaskContext()
    context.extend_stderr(None)
    context.extend_stderr([])
    assert context.stderr_lines == ()
