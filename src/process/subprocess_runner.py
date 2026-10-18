# -*- coding: utf-8 -*-
"""基于 subprocess.Popen 的 ProcessRunner 实现。

用途:
    * 非 GUI 路径（CLI / 测试）的默认后端；
    * 取消时序的参考实现：stdin 写 ``q``（FFmpeg 优雅退出）→ grace 等待 →
      terminate → 等待 → kill（Windows 杀进程树）→ 确认退出。

线程模型:
    ``start()`` 后为 stdout/stderr 各起一个 daemon 读取线程，逐行回调；
    ``wait()`` 在调用线程（通常是 TaskRunner 工作线程）轮询进程状态并推进
    取消时序；``cancel()`` 只置 ``threading.Event``，可在任意线程调用。
"""

import collections
import os
import subprocess
import threading
import time
from typing import Deque, List, Optional, Sequence

from .base import (
    CompletedProcess,
    ExecutableMissingError,
    OutputCallback,
    ProcessStartError,
    ProcessState,
    kill_process_tree,
)

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class SubprocessRunner:
    """Popen 后端：逐行读取输出，支持协作式取消。"""

    def __init__(
        self,
        *,
        popen_factory=None,
        stderr_tail_lines: int = 200,
        stdout_tail_lines: int = 200,
        poll_interval: float = 0.02,
        graceful_seconds: float = 2.5,
        terminate_wait_seconds: float = 1.0,
        kill_wait_seconds: float = 2.0,
        reader_join_timeout: float = 2.0,
        kill_tree=kill_process_tree,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        self._popen_factory = popen_factory or subprocess.Popen
        self._stderr_tail: Deque[str] = collections.deque(maxlen=stderr_tail_lines)
        self._stdout_tail: Deque[str] = collections.deque(maxlen=stdout_tail_lines)
        self._poll_interval = poll_interval
        self._graceful_seconds = graceful_seconds
        self._terminate_wait_seconds = terminate_wait_seconds
        self._kill_wait_seconds = kill_wait_seconds
        self._reader_join_timeout = reader_join_timeout
        self._kill_tree = kill_tree
        self._clock = clock
        self._sleep = sleep

        self.on_stdout: Optional[OutputCallback] = None
        self.on_stderr: Optional[OutputCallback] = None
        self.on_finished = None

        self._process = None
        self._argv: List[str] = []
        self._readers: List[threading.Thread] = []
        self._cancel_event = threading.Event()
        self._cancel_lock = threading.Lock()
        self._stdin_lock = threading.Lock()
        self._graceful_sent = False
        self._terminate_sent = False
        self._kill_sent = False
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
        try:
            return self._process.poll()
        except Exception:  # noqa: BLE001 - 假进程实现可能不完整
            return self._exit_code

    @property
    def pid(self) -> Optional[int]:
        if self._process is None:
            return None
        return getattr(self._process, "pid", None)

    def is_running(self) -> bool:
        if self._process is None:
            return False
        try:
            return self._process.poll() is None
        except Exception:  # noqa: BLE001
            return False

    # ----------------------------------------------------------------
    # 启动 / 读取
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
            raise RuntimeError("SubprocessRunner 只能启动一次")

        argv = [str(part) for part in cmd]
        self._argv = argv
        popen_kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if stdin_pipe else subprocess.DEVNULL,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=cwd,
            env=env,
            creationflags=_CREATE_NO_WINDOW,
        )
        try:
            self._process = self._popen_factory(argv, **popen_kwargs)
        except FileNotFoundError as exc:
            self._state = ProcessState.FAILED
            raise ExecutableMissingError(
                f"找不到可执行文件: {argv[0]}") from exc
        except OSError as exc:
            self._state = ProcessState.FAILED
            raise ProcessStartError(f"启动进程失败: {exc}") from exc

        self._state = (
            ProcessState.CANCELLING
            if self._cancel_event.is_set() else ProcessState.RUNNING
        )
        stdout = getattr(self._process, "stdout", None)
        if stdout is not None:
            self._spawn_reader(stdout, self._stdout_tail, self._dispatch_stdout)
        stderr = getattr(self._process, "stderr", None)
        if stderr is not None:
            self._spawn_reader(stderr, self._stderr_tail, self._dispatch_stderr)
        if self._cancel_event.is_set():
            # 取消先于启动: 立刻补发优雅退出 (wait() 会继续推进后续时序)
            self._write_graceful_quit()

    def _spawn_reader(self, stream, tail, dispatch) -> None:
        def _read():
            try:
                while True:
                    line = stream.readline()
                    if not line:
                        break
                    tail.append(line)
                    dispatch(line)
            except (ValueError, OSError):
                pass
            finally:
                try:
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass

        thread = threading.Thread(
            target=_read, daemon=True, name="xiaoxue-process-reader")
        thread.start()
        self._readers.append(thread)

    def _dispatch_stdout(self, line: str) -> None:
        callback = self.on_stdout
        if callback is not None:
            try:
                callback(line)
            except Exception:  # noqa: BLE001 - 回调异常不影响读取
                pass

    def _dispatch_stderr(self, line: str) -> None:
        callback = self.on_stderr
        if callback is not None:
            try:
                callback(line)
            except Exception:  # noqa: BLE001
                pass

    # ----------------------------------------------------------------
    # 取消
    # ----------------------------------------------------------------

    def cancel(self) -> None:
        """请求取消：置事件并尝试写 ``q`` 让 FFmpeg 优雅退出，立即返回。"""
        with self._cancel_lock:
            if self._state in (ProcessState.FINISHED, ProcessState.FAILED):
                return
            if self._cancel_event.is_set():
                return
            self._cancel_event.set()
            self._state = ProcessState.CANCELLING
            if self._process is None:
                # 尚未 start: 标志位保留, start() 后 wait() 会立刻进入取消时序
                return
            self._write_graceful_quit()

    def _write_graceful_quit(self) -> None:
        stdin = getattr(self._process, "stdin", None)
        if stdin is None:
            return
        try:
            with self._stdin_lock:
                if getattr(stdin, "closed", False):
                    return
                stdin.write("q\n")
                stdin.flush()
            self._graceful_sent = True
        except (ValueError, OSError):
            pass

    # ----------------------------------------------------------------
    # 等待 / 取消时序推进
    # ----------------------------------------------------------------

    def wait(self, timeout: Optional[float] = None) -> CompletedProcess:
        if self._process is None:
            raise RuntimeError("wait() 前必须先 start()")

        started = self._clock()
        deadline = None if timeout is None else started + timeout
        graceful_deadline: Optional[float] = None
        terminated_at: Optional[float] = None
        kill_deadline: Optional[float] = None
        force_kill_done = False

        while True:
            if self._process.poll() is not None:
                break
            now = self._clock()

            if self._cancel_event.is_set():
                if graceful_deadline is None:
                    # 阶段 1: 已写 q, 等待优雅退出 grace 窗口 (默认 2.5s)
                    graceful_deadline = now + self._graceful_seconds
                elif (not self._terminate_sent
                      and now >= graceful_deadline):
                    # 阶段 2: terminate
                    self._call_process("terminate")
                    self._terminate_sent = True
                    terminated_at = now
                elif (self._terminate_sent and not self._kill_sent
                      and now - terminated_at >= self._terminate_wait_seconds):
                    # 阶段 3: 杀进程树 (Windows taskkill /T /F, POSIX SIGKILL)
                    self._kill_tree_now()
                    self._kill_sent = True
                    kill_deadline = now + self._kill_wait_seconds
                elif (self._kill_sent and not force_kill_done
                      and now >= kill_deadline):
                    # 阶段 4: 兜底强杀
                    self._call_process("kill")
                    force_kill_done = True

            if deadline is not None and now >= deadline:
                self._call_process("kill")
                try:
                    self._process.wait(timeout=1)
                except Exception:  # noqa: BLE001
                    pass
                raise TimeoutError(f"进程未在 {timeout} 秒内结束")

            self._sleep(self._poll_interval)

        self._join_readers()
        self._exit_code = self._process.poll()
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

    def _call_process(self, method: str) -> None:
        func = getattr(self._process, method, None)
        if callable(func):
            try:
                func()
            except Exception:  # noqa: BLE001 - 进程可能已退出
                pass

    def _kill_tree_now(self) -> None:
        pid = self.pid
        if pid:
            try:
                self._kill_tree(int(pid))
            except Exception:  # noqa: BLE001
                pass
        if self.is_running():
            self._call_process("kill")

    def _join_readers(self) -> None:
        for thread in self._readers:
            thread.join(timeout=self._reader_join_timeout)


def run(
    cmd: Sequence[str],
    *,
    runner: Optional[object] = None,
    on_stdout: Optional[OutputCallback] = None,
    on_stderr: Optional[OutputCallback] = None,
    stdin_pipe: bool = True,
    env: Optional[dict] = None,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
) -> CompletedProcess:
    """阻塞式执行命令，返回 :class:`CompletedProcess`。

    ``runner`` 可由调用方传入（core 通过 TaskContext 注入的后端实例），
    不传时使用 :class:`SubprocessRunner`。
    """
    active = runner if runner is not None else SubprocessRunner()
    if on_stdout is not None:
        active.on_stdout = on_stdout
    if on_stderr is not None:
        active.on_stderr = on_stderr
    active.start(cmd, cwd=cwd, env=env, stdin_pipe=stdin_pipe)
    return active.wait(timeout=timeout) if timeout is not None else active.wait()
