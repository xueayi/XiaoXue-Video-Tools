# -*- coding: utf-8 -*-
"""TaskContext 取消注册 + runner 工厂解析 + core 集成测试。"""

import pytest

import src.core as core
import src.task.context as task_context
from src.process.base import CompletedProcess
from src.process.subprocess_runner import SubprocessRunner
from src.task.context import (
    TaskCancelled,
    TaskContext,
    current_task,
    reset_current_task,
    set_current_task,
    set_runner_factory,
)


class FakeHandle:
    def __init__(self):
        self.cancel_calls = 0
        self.terminate_calls = 0

    def cancel(self):
        self.cancel_calls += 1

    def terminate(self):
        self.terminate_calls += 1


class TerminateOnlyHandle:
    def __init__(self):
        self.terminate_calls = 0

    def terminate(self):
        self.terminate_calls += 1


# ----------------------------------------------------------------
# 句柄注册 -> 取消绑定
# ----------------------------------------------------------------

def test_register_binds_cancel_and_is_idempotent():
    context = TaskContext()
    handle = FakeHandle()
    context.register(handle)
    assert context.handles == (handle,)
    assert len(context.request_cancel_callbacks) == 1

    context.cancel()
    context.cancel()  # 幂等
    assert handle.cancel_calls == 1


def test_unregister_removes_cancel_binding():
    context = TaskContext()
    handle = FakeHandle()
    context.register(handle)
    context.unregister(handle)
    assert context.handles == ()
    assert context.request_cancel_callbacks == ()

    context.cancel()
    assert handle.cancel_calls == 0


def test_register_after_cancel_cancels_immediately():
    context = TaskContext()
    context.cancel()
    handle = FakeHandle()
    context.register(handle)
    assert handle.cancel_calls == 1


def test_register_same_handle_twice_only_once():
    context = TaskContext()
    handle = FakeHandle()
    context.register(handle)
    context.register(handle)
    assert context.handles == (handle,)
    context.cancel()
    assert handle.cancel_calls == 1


def test_handle_without_cancel_falls_back_to_terminate():
    context = TaskContext()
    handle = TerminateOnlyHandle()
    context.register(handle)
    context.cancel()
    assert handle.terminate_calls == 1


def test_handle_cancel_exception_swallowed():
    class BoomHandle:
        def cancel(self):
            raise RuntimeError("cancel 炸了")

    context = TaskContext()
    context.register(BoomHandle())
    called = []
    context.add_cancel_callback(lambda: called.append(True))
    context.cancel()  # 不向外抛
    assert called == [True]
    assert context.cancelled is True


# ----------------------------------------------------------------
# runner 工厂解析
# ----------------------------------------------------------------

def test_instance_factory_wins():
    sentinel = object()
    context = TaskContext(runner_factory=lambda: sentinel)
    assert context.create_runner() is sentinel

    another = object()
    context.set_runner_factory(lambda: another)
    assert context.create_runner() is another


def test_default_factory_is_subprocess_runner(monkeypatch):
    monkeypatch.setattr(task_context, "_default_runner_factory", None)
    context = TaskContext()
    assert isinstance(context.create_runner(), SubprocessRunner)


def test_module_level_factory_override(monkeypatch):
    monkeypatch.setattr(task_context, "_default_runner_factory", None)
    sentinel = object()
    try:
        set_runner_factory(lambda: sentinel)
        assert task_context.get_runner_factory()() is sentinel
        context = TaskContext()
        assert context.create_runner() is sentinel
    finally:
        set_runner_factory(None)
    assert task_context.get_runner_factory() is SubprocessRunner


# ----------------------------------------------------------------
# core 集成: 执行时注册句柄, 取消时触达 runner, cancelled 映射 TaskCancelled
# ----------------------------------------------------------------

class FakeRunner:
    def __init__(self, *, cancelled=False, exit_code=0):
        self.on_stdout = None
        self.on_stderr = None
        self.started = None
        self.waited = False
        self.cancel_calls = 0
        self._cancelled = cancelled
        self._exit_code = exit_code

    def start(self, cmd, *, cwd=None, env=None, stdin_pipe=False):
        self.started = list(cmd)

    def wait(self, timeout=None):
        self.waited = True
        return CompletedProcess(
            exit_code=self._exit_code, cancelled=self._cancelled)

    def cancel(self):
        self.cancel_calls += 1

    def is_running(self):
        return False

    @property
    def exit_code(self):
        return self._exit_code


def _with_context(context):
    token = set_current_task(context)
    return token


def test_core_registers_and_unregisters_runner():
    runner = FakeRunner(exit_code=0)
    context = TaskContext(runner_factory=lambda: runner)
    token = _with_context(context)
    try:
        rc = core.run_ffmpeg_command(["ffmpeg", "-i", "in.mp4"])
    finally:
        reset_current_task(token)

    assert rc == 0
    assert runner.started == ["ffmpeg", "-i", "in.mp4"]
    assert runner.waited is True
    assert context.handles == ()  # wait 结束后已注销


def test_core_cancel_reaches_registered_runner():
    runner = FakeRunner(cancelled=True)
    context = TaskContext(runner_factory=lambda: runner)
    token = _with_context(context)
    try:
        with pytest.raises(TaskCancelled):
            core.run_ffmpeg_command(["ffmpeg"])
    finally:
        reset_current_task(token)

    assert runner.waited is True
    assert runner.cancel_calls == 0  # 未显式点停止时不应乱取消

    # 显式取消: 仅注册期间有句柄, 之后无句柄不报错
    context.cancel()
    assert context.cancelled is True


def test_core_cancel_before_start_raises_without_starting():
    runner = FakeRunner()
    context = TaskContext(runner_factory=lambda: runner)
    context.cancel()
    token = _with_context(context)
    try:
        with pytest.raises(TaskCancelled):
            core.run_ffmpeg_command(["ffmpeg"])
    finally:
        reset_current_task(token)
    assert runner.started is None


def test_current_task_none_uses_subprocess_backend(monkeypatch):
    used = {}

    def fake_run(cmd, *, runner=None, **kwargs):
        used["runner"] = runner
        return CompletedProcess(exit_code=0)

    monkeypatch.setattr(core, "run_process", fake_run)
    rc = core.run_ffmpeg_command(["ffmpeg"])
    assert rc == 0
    assert isinstance(used["runner"], SubprocessRunner)
    assert current_task() is None
