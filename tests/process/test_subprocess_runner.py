# -*- coding: utf-8 -*-
"""SubprocessRunner 测试: 注入 fake Popen, 不启动真实进程。

覆盖: exit 0/非 0、exe missing、stdout/stderr 分流、stderr tail、
取消时序 q -> terminate -> kill、grace 超时、取消中途、wait 超时、run()。
"""

import threading
import time

import pytest

from src.process.base import (
    CompletedProcess,
    ExecutableMissingError,
    ProcessStartError,
)
from src.process.subprocess_runner import SubprocessRunner, run


class FakeStream:
    def __init__(self, lines):
        self._lines = list(lines)
        self.closed = False

    def readline(self):
        if self._lines:
            return self._lines.pop(0)
        return ""

    def close(self):
        self.closed = True


class FakeStdin:
    def __init__(self, owner):
        self.owner = owner
        self.closed = False

    def write(self, text):
        self.owner.on_stdin(text)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakePopen:
    """最小 Popen 替身：可控退出时机与方式，记录调用顺序。"""

    def __init__(
        self,
        *,
        stdout_lines=(),
        stderr_lines=(),
        returncode=0,
        immediate=False,
        quit_on_q=True,
        exit_on_terminate=True,
        exit_on_kill=True,
        pid=4321,
    ):
        self.stdout = FakeStream(stdout_lines)
        self.stderr = FakeStream(stderr_lines)
        self.stdin = FakeStdin(self)
        self.pid = pid
        self.calls = []
        self.returncode = returncode if immediate else None
        self._final_returncode = returncode
        self._quit_on_q = quit_on_q
        self._exit_on_terminate = exit_on_terminate
        self._exit_on_kill = exit_on_kill

    # Popen 接口
    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.calls.append("terminate")
        if self._exit_on_terminate:
            self._exit(-15)

    def kill(self):
        self.calls.append("kill")
        if self._exit_on_kill:
            self._exit(-9)

    # FakeStdin 回调
    def on_stdin(self, text):
        if "q" in text:
            self.calls.append("q")
            if self._quit_on_q:
                self._exit(0)

    def _exit(self, code):
        if self.returncode is None:
            self.returncode = code


def _runner(process, **kwargs):
    kwargs.setdefault("poll_interval", 0.001)
    kwargs.setdefault("graceful_seconds", 0.01)
    kwargs.setdefault("terminate_wait_seconds", 0.01)
    kwargs.setdefault("kill_wait_seconds", 0.01)
    kwargs.setdefault("reader_join_timeout", 1.0)
    kwargs.setdefault("kill_tree", lambda pid: None)
    return SubprocessRunner(popen_factory=lambda argv, **kw: process, **kwargs)


# ----------------------------------------------------------------
# 正常结束
# ----------------------------------------------------------------

def test_exit_zero_and_streams_split():
    process = FakePopen(
        stdout_lines=["out1\n", "out2\n"],
        stderr_lines=["err1\n"],
        returncode=0,
        immediate=True,
    )
    runner = _runner(process)
    stdout, stderr = [], []
    runner.on_stdout = stdout.append
    runner.on_stderr = stderr.append

    completed = run(["ffmpeg", "-i", "in.mp4"], runner=runner)

    assert isinstance(completed, CompletedProcess)
    assert completed.exit_code == 0
    assert completed.cancelled is False
    assert completed.ok is True
    assert stdout == ["out1\n", "out2\n"]
    assert stderr == ["err1\n"]
    assert completed.argv == ("ffmpeg", "-i", "in.mp4")


def test_nonzero_exit_code():
    process = FakePopen(stderr_lines=["boom\n"], returncode=3, immediate=True)
    runner = _runner(process)
    runner.start(["ffmpeg"])
    completed = runner.wait()
    assert completed.exit_code == 3
    assert completed.ok is False


def test_stderr_tail_keeps_last_lines():
    process = FakePopen(
        stderr_lines=["e1\n", "e2\n", "e3\n"], returncode=0, immediate=True)
    runner = _runner(process, stderr_tail_lines=2)
    runner.start(["ffmpeg"], stdin_pipe=True)
    completed = runner.wait()
    assert completed.stderr_tail == ("e2\n", "e3\n")
    assert runner.state.value == "finished"


# ----------------------------------------------------------------
# 启动失败
# ----------------------------------------------------------------

def test_executable_missing_maps_to_error():
    def missing(argv, **kwargs):
        raise FileNotFoundError(2, "No such file", argv[0])

    runner = SubprocessRunner(popen_factory=missing)
    with pytest.raises(ExecutableMissingError):
        runner.start(["Z:/no/ffmpeg.exe"])
    assert runner.state.value == "failed"


def test_generic_start_error_maps_to_process_start_error():
    def broken(argv, **kwargs):
        raise OSError("permission denied")

    runner = SubprocessRunner(popen_factory=broken)
    with pytest.raises(ProcessStartError):
        runner.start(["ffmpeg"])


# ----------------------------------------------------------------
# 取消时序
# ----------------------------------------------------------------

def test_cancel_graceful_quit_uses_stdin_q():
    process = FakePopen(quit_on_q=True)
    runner = _runner(process)
    runner.start(["ffmpeg"], stdin_pipe=True)

    runner.cancel()
    completed = runner.wait()

    assert completed.cancelled is True
    assert "q" in process.calls
    assert "terminate" not in process.calls
    assert "kill" not in process.calls


def test_cancel_then_terminate_then_kill_order():
    process = FakePopen(
        quit_on_q=False, exit_on_terminate=False, exit_on_kill=True)
    runner = _runner(process)
    runner.start(["ffmpeg"], stdin_pipe=True)

    runner.cancel()
    completed = runner.wait()

    assert completed.cancelled is True
    # 顺序: q -> terminate -> (taskkill 之后兜底) kill
    assert process.calls[0] == "q"
    assert process.calls.index("terminate") < process.calls.index("kill")
    assert completed.exit_code is not None


def test_cancel_grace_timeout_kills_even_if_terminate_ignored():
    process = FakePopen(
        quit_on_q=False, exit_on_terminate=False, exit_on_kill=True)
    runner = _runner(process)
    runner.start(["ffmpeg"], stdin_pipe=True)

    started = time.monotonic()
    runner.cancel()
    completed = runner.wait()
    elapsed = time.monotonic() - started

    assert completed.cancelled is True
    assert runner.is_running() is False
    # 时序使用注入的短 grace, 不应卡满默认 2.5s
    assert elapsed < 2.0


def test_cancel_midway_from_other_thread():
    process = FakePopen(quit_on_q=True)
    runner = _runner(process)
    runner.start(["ffmpeg"], stdin_pipe=True)

    def _cancel():
        time.sleep(0.02)
        runner.cancel()

    thread = threading.Thread(target=_cancel)
    thread.start()
    completed = runner.wait()
    thread.join(timeout=2)

    assert completed.cancelled is True
    assert "q" in process.calls


def test_cancel_before_start_is_honoured():
    process = FakePopen(quit_on_q=True)
    runner = _runner(process)
    runner.cancel()  # 尚未 start
    runner.start(["ffmpeg"], stdin_pipe=True)
    completed = runner.wait()
    assert completed.cancelled is True
    assert "q" in process.calls


def test_cancel_after_finish_is_noop():
    process = FakePopen(returncode=0, immediate=True)
    runner = _runner(process)
    runner.start(["ffmpeg"])
    runner.wait()
    runner.cancel()
    assert process.calls == []


def test_wait_timeout_raises():
    process = FakePopen(quit_on_q=False, exit_on_terminate=False,
                        exit_on_kill=True)
    runner = _runner(process)
    runner.start(["ffmpeg"], stdin_pipe=True)
    with pytest.raises(TimeoutError):
        runner.wait(timeout=0.05)
