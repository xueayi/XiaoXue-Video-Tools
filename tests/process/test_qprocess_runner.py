# -*- coding: utf-8 -*-
"""QProcessRunner 测试: 真实短命令 (python -c), 离屏 QApplication。"""

import sys
import threading
import time

import pytest

from src.process.base import ExecutableMissingError
from src.process.qprocess_runner import QProcessRunner


def _short_runner(**kwargs):
    kwargs.setdefault("poll_interval_ms", 10)
    kwargs.setdefault("start_timeout_ms", 5000)
    kwargs.setdefault("graceful_seconds", 0.05)
    kwargs.setdefault("terminate_wait_seconds", 0.05)
    kwargs.setdefault("kill_wait_seconds", 0.05)
    return QProcessRunner(**kwargs)


def test_qprocess_runs_short_command(qapp):
    stdout, stderr = [], []
    runner = _short_runner()
    runner.on_stdout = stdout.append
    runner.on_stderr = stderr.append

    runner.start([sys.executable, "-c", "print('hello-qprocess')"])
    completed = runner.wait()

    assert completed.exit_code == 0
    assert completed.cancelled is False
    assert runner.is_running() is False
    assert runner.state.value == "finished"
    assert "hello-qprocess" in "".join(stdout)
    assert completed.stdout_tail and not completed.cancelled
    assert runner.exit_code == 0


def test_qprocess_separates_stdout_and_stderr(qapp):
    stdout, stderr = [], []
    runner = _short_runner()
    runner.on_stdout = stdout.append
    runner.on_stderr = stderr.append
    code = "import sys; print('OUT'); print('ERR', file=sys.stderr)"

    runner.start([sys.executable, "-c", code])
    completed = runner.wait()

    assert completed.exit_code == 0
    assert "OUT" in "".join(stdout)
    assert "ERR" in "".join(stderr)
    assert any("ERR" in line for line in completed.stderr_tail)


def test_qprocess_nonzero_exit(qapp):
    runner = _short_runner()
    runner.start([sys.executable, "-c", "raise SystemExit(7)"])
    completed = runner.wait()
    assert completed.exit_code == 7
    assert completed.ok is False


def test_qprocess_missing_executable(qapp, tmp_path):
    runner = _short_runner()
    with pytest.raises(ExecutableMissingError):
        runner.start([str(tmp_path / "no-such-binary")])
    assert runner.state.value == "failed"


def test_qprocess_cancel_kills_long_running_process(qapp):
    order = []
    runner = _short_runner(kill_tree=lambda pid: order.append(("kill_tree", pid)))
    runner.start([sys.executable, "-c", "import time; time.sleep(30)"])

    def _cancel():
        time.sleep(0.15)
        runner.cancel()

    thread = threading.Thread(target=_cancel)
    thread.start()
    started = time.monotonic()
    completed = runner.wait()
    elapsed = time.monotonic() - started
    thread.join(timeout=5)

    assert completed.cancelled is True
    assert runner.is_running() is False
    assert elapsed < 10.0
    # POSIX terminate 可正常结束进程，无需升级到强杀。
    assert completed.exit_code != 0


def test_qprocess_cancel_before_start_is_honoured(qapp):
    order = []
    runner = _short_runner(kill_tree=lambda pid: order.append(pid))
    runner.cancel()  # 尚未 start
    runner.start([sys.executable, "-c", "import time; time.sleep(30)"])
    completed = runner.wait()
    assert completed.cancelled is True
    assert runner.is_running() is False
