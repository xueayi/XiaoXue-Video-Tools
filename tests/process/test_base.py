# -*- coding: utf-8 -*-
"""src/process/base.py 测试: 结果模型、状态、异常层级、进程树强杀。"""

import os

import pytest

from src.process.base import (
    CompletedProcess,
    ExecutableMissingError,
    ProcessError,
    ProcessStartError,
    ProcessState,
    kill_process_tree,
)


def test_process_state_values():
    assert [state.value for state in ProcessState] == [
        "idle", "running", "cancelling", "finished", "failed",
    ]


def test_exception_hierarchy():
    assert issubclass(ExecutableMissingError, ProcessStartError)
    assert issubclass(ProcessStartError, ProcessError)
    assert issubclass(ProcessError, Exception)
    assert "找不到" in str(ExecutableMissingError("找不到可执行文件: ffmpeg"))


def test_completed_process_ok():
    assert CompletedProcess(exit_code=0).ok is True
    assert CompletedProcess(exit_code=0, cancelled=True).ok is False
    assert CompletedProcess(exit_code=1).ok is False
    assert CompletedProcess(exit_code=None).ok is False


def test_completed_process_defaults_and_frozen():
    completed = CompletedProcess(exit_code=0)
    assert completed.cancelled is False
    assert completed.stderr_tail == ()
    assert completed.stdout_tail == ()
    assert completed.argv == ()
    with pytest.raises(Exception):
        completed.exit_code = 1  # type: ignore[misc]


def test_kill_process_tree_ignores_invalid_pid(monkeypatch):
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: calls.append(a))
    kill_process_tree(0)
    kill_process_tree(-5)
    assert calls == []


@pytest.mark.skipif(os.name != "nt", reason="taskkill 仅 Windows")
def test_kill_process_tree_uses_taskkill_tree_on_windows(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))

    monkeypatch.setattr("subprocess.run", fake_run)
    kill_process_tree(4321, timeout=2.0)

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[:2] == ["taskkill", "/PID"]
    assert argv[2] == "4321"
    assert "/T" in argv and "/F" in argv
    assert kwargs["timeout"] == 2.0


@pytest.mark.skipif(os.name == "nt", reason="POSIX os.kill 分支")
def test_kill_process_tree_falls_back_to_os_kill(monkeypatch):
    signals = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: signals.append((pid, sig)))
    kill_process_tree(4321)
    assert signals and signals[0][0] == 4321
