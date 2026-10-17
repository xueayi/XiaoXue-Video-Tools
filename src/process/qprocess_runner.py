# -*- coding: utf-8 -*-
"""基于 QProcess 的 ProcessRunner 实现（GUI 主路径）。

使用方式：由 ``TaskContext(runner_factory=...)`` 注入，在 TaskRunner 工作线程
内创建并阻塞等待；不使用 Qt 事件循环，因此可以安全地放在 QThread.run() 中。

线程安全约定（与 :class:`~src.process.subprocess_runner.SubprocessRunner` 一致）：
    * ``cancel()`` 可在任意线程调用，只置 ``threading.Event``，不直接操作
      QProcess（QProcess 非线程安全）；
    * ``wait()`` 在 QProcess 所属线程（TaskRunner 工作线程）中轮询状态，
      发现取消事件后由本线程按 graceful(q) -> terminate -> kill 时序推进。
"""

import threading
import time
from collections import deque
from typing import Deque, List, Optional, Sequence

from PyQt6.QtCore import QProcess, QProcessEnvironment

from .base import (
    CompletedProcess,
    ExecutableMissingError,
    OutputCallback,
    ProcessState,
    kill_process_tree,
)


class QProcessRunner:
    """QProcess 后端：waitForReadyRead / waitForFinished 阻塞式读取。"""

    def __init__(
        self,
        *,
        process_factory=None,
        stderr_tail_lines: int = 200,
        stdout_tail_lines: int = 200,
        poll_interval_ms: int = 50,
        start_timeout_ms: int = 5000,
        graceful_seconds: float = 2.5,
        terminate_wait_seconds: float = 1.0,
        kill_wait_seconds: float = 2.0,
        kill_tree=kill_process_tree,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        self._process_factory = process_factory or QProcess
        self._stderr_tail: Deque[str] = deque(maxlen=stderr_tail_lines)
        self._stdout_tail: Deque[str] = deque(maxlen=stdout_tail_lines)
        self._poll_interval_ms = poll_interval_ms
        self._start_timeout_ms = start_timeout_ms
        self._graceful_seconds = graceful_seconds
        self._terminate_wait_seconds = terminate_wait_seconds
        self._kill_wait_seconds = kill_wait_seconds
        self._kill_tree = kill_tree
        self._clock = clock
        self._sleep = sleep

        self.on_stdout: Optional[OutputCallback] = None
        self.on_stderr: Optional[OutputCallback] = None
        self.on_finished = None

        self._process = None
        self._argv: List[str] = []
        self._stdin_pipe = False
        self._cancel_event = threading.Event()
        self._cancel_lock = threading.Lock()
        self._stdout_buf = ""
        self._stderr_buf = ""
        self._exit_code: Optional[int] = None
        self._state = ProcessState.IDLE

    # ----------------------------------------------------------------
    # 属性
    # ----------------------------------------------------------------

    @property
    def state(self) -> ProcessState:
        return self._state

    @property
    def exit_code(self) -> Optional[int]:
        if self._process is None:
            return None
        if self._process.state() == QProcess.ProcessState.NotRunning:
            return self._process.exitCode()
        return None

    @property
    def pid(self) -> Optional[int]:
        if self._process is None:
            return None
        try:
            return int(self._process.processId())
        except Exception:  # noqa: BLE001
            return None

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.state() != QProcess.ProcessState.NotRunning

    # ----------------------------------------------------------------
    # 启动
    # ----------------------------------------------------------------

    def start(
        self,
        cmd: Sequence[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        stdin_pipe: bool = False,
    ) -> None:
        if self._process is not None:
            raise RuntimeError("QProcessRunner 只能启动一次")

        argv = [str(part) for part in cmd]
        self._argv = argv
        self._stdin_pipe = stdin_pipe

        process = self._process_factory()
        self._process = process
        process.setProgram(argv[0])
        process.setArguments(argv[1:])
        process.setProcessChannelMode(
            QProcess.ProcessChannelMode.SeparateChannels)
        if cwd is not None:
            process.setWorkingDirectory(str(cwd))
        if env is not None:
            process.setProcessEnvironment(self._build_environment(env))

        process.start()
        if not process.waitForStarted(self._start_timeout_ms):
            detail = process.errorString()
            self._state = ProcessState.FAILED
            raise ExecutableMissingError(
                f"无法启动进程 {argv[0]}: {detail}")

        self._state = (
            ProcessState.CANCELLING
            if self._cancel_event.is_set() else ProcessState.RUNNING
        )

    @staticmethod
    def _build_environment(env: dict) -> QProcessEnvironment:
        qenv = QProcessEnvironment()
        for key, value in env.items():
            qenv.insert(str(key), str(value))
        return qenv

    # ----------------------------------------------------------------
    # 取消（只置事件，不跨线程操作 QProcess）
    # ----------------------------------------------------------------

    def cancel(self) -> None:
        with self._cancel_lock:
            if self._state in (ProcessState.FINISHED, ProcessState.FAILED):
                return
            if self._cancel_event.is_set():
                return
            self._cancel_event.set()
            self._state = ProcessState.CANCELLING

    # ----------------------------------------------------------------
    # 等待 / 取消时序推进
    # ----------------------------------------------------------------

    def wait(self, timeout: Optional[float] = None) -> CompletedProcess:
        if self._process is None:
            raise RuntimeError("wait() 前必须先 start()")

        process = self._process
        started = self._clock()
        deadline = None if timeout is None else started + timeout
        graceful_deadline: Optional[float] = None
        terminated_at: Optional[float] = None
        kill_deadline: Optional[float] = None
        terminate_sent = False
        kill_sent = False
        force_kill_done = False

        while process.state() != QProcess.ProcessState.NotRunning:
            self._drain()
            now = self._clock()

            if self._cancel_event.is_set():
                if graceful_deadline is None:
                    # 阶段 1: 写 q 让 FFmpeg 优雅退出, 进入 grace 窗口
                    if self._stdin_pipe:
                        try:
                            process.write(b"q\n")
                        except Exception:  # noqa: BLE001
                            pass
                    self._state = ProcessState.CANCELLING
                    graceful_deadline = now + self._graceful_seconds
                elif not terminate_sent and now >= graceful_deadline:
                    # 阶段 2: terminate
                    try:
                        process.terminate()
                    except Exception:  # noqa: BLE001
                        pass
                    terminate_sent = True
                    terminated_at = now
                elif (terminate_sent and not kill_sent
                      and now - terminated_at >= self._terminate_wait_seconds):
                    # 阶段 3: 杀进程树
                    self._kill_tree_now(process)
                    kill_sent = True
                    kill_deadline = now + self._kill_wait_seconds
                elif (kill_sent and not force_kill_done
                      and now >= kill_deadline):
                    # 阶段 4: 兜底强杀
                    try:
                        process.kill()
                    except Exception:  # noqa: BLE001
                        pass
                    force_kill_done = True

            if deadline is not None and now >= deadline:
                try:
                    process.kill()
                except Exception:  # noqa: BLE001
                    pass
                process.waitForFinished(1000)
                self._drain(final=True)
                self._state = ProcessState.FINISHED
                raise TimeoutError(f"进程未在 {timeout} 秒内结束")

            # 阻塞至多 poll_interval_ms, 有输出则读取; 无输出也定期检查取消/状态
            if process.waitForReadyRead(self._poll_interval_ms):
                self._drain()
            else:
                self._drain()

        self._drain(final=True)
        normal_exit = (
            process.exitStatus() == QProcess.ExitStatus.NormalExit)
        self._exit_code = process.exitCode() if normal_exit else -1
        self._state = ProcessState.FINISHED
        completed = CompletedProcess(
            exit_code=self._exit_code,
            cancelled=self._cancel_event.is_set(),
            stderr_tail=tuple(self._stderr_tail),
            stdout_tail=tuple(self._stdout_tail),
            argv=tuple(self._argv),
        )
        callback = self.on_finished
        if callback is not None:
            try:
                callback(completed)
            except Exception:  # noqa: BLE001
                pass
        return completed

    def _kill_tree_now(self, process) -> None:
        pid = 0
        try:
            pid = int(process.processId())
        except Exception:  # noqa: BLE001
            pid = 0
        if pid > 0:
            try:
                self._kill_tree(pid)
            except Exception:  # noqa: BLE001
                pass
        if process.state() != QProcess.ProcessState.NotRunning:
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                pass

    # ----------------------------------------------------------------
    # 输出读取
    # ----------------------------------------------------------------

    def _drain(self, *, final: bool = False) -> None:
        if self._process is None:
            return
        try:
            stdout = bytes(self._process.readAllStandardOutput())
            stderr = bytes(self._process.readAllStandardError())
        except Exception:  # noqa: BLE001
            return
        if stdout:
            self._feed(stdout, is_stdout=True)
        if stderr:
            self._feed(stderr, is_stdout=False)
        if final:
            self._flush_buffer(is_stdout=True)
            self._flush_buffer(is_stdout=False)

    def _feed(self, data: bytes, *, is_stdout: bool) -> None:
        text = data.decode("utf-8", errors="replace")
        if is_stdout:
            buffer = self._stdout_buf + text
        else:
            buffer = self._stderr_buf + text
        lines = buffer.split("\n")
        remainder = lines.pop()  # 末尾不完整行留到下次
        for raw in lines:
            self._emit_line(raw.rstrip("\r") + "\n", is_stdout=is_stdout)
        if is_stdout:
            self._stdout_buf = remainder
        else:
            self._stderr_buf = remainder

    def _flush_buffer(self, *, is_stdout: bool) -> None:
        buffer = self._stdout_buf if is_stdout else self._stderr_buf
        if not buffer:
            return
        self._emit_line(buffer.rstrip("\r") + "\n", is_stdout=is_stdout)
        if is_stdout:
            self._stdout_buf = ""
        else:
            self._stderr_buf = ""

    def _emit_line(self, line: str, *, is_stdout: bool) -> None:
        if is_stdout:
            self._stdout_tail.append(line)
            callback = self.on_stdout
        else:
            self._stderr_tail.append(line)
            callback = self.on_stderr
        if callback is not None:
            try:
                callback(line)
            except Exception:  # noqa: BLE001 - 回调异常不影响读取
                pass
