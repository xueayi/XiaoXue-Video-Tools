# -*- coding: utf-8 -*-
"""进程执行抽象层 —— 统一的结果模型、状态、错误与取消协议。

设计约定 (M2.3):
    * 取消是「请求 + 由等待线程推进时序」：UI/主线程只调用 ``cancel()``
      置线程安全事件，真正的 graceful -> terminate -> kill 时序由阻塞在
      ``wait()`` 里的工作线程推进，避免阻塞 GUI 线程，也避免跨线程操作
      QProcess 等非线程安全对象；
    * ``on_stdout`` / ``on_stderr`` 回调在读取线程(或等待线程)中被调用，
      参数为一行文本（通常带结尾换行符）；
    * 进程结束后返回 :class:`CompletedProcess`；主动取消通过 ``cancelled``
      标记表达，由 executor/runner 映射为 TaskStatus.CANCELLED。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Protocol, Sequence, Tuple

#: 输出行回调
OutputCallback = Callable[[str], None]
#: 进程结束后回调（可选，暂未使用；保留协议扩展位）
FinishedCallback = Callable[["CompletedProcess"], None]


class ProcessState(str, Enum):
    """进程生命周期状态。"""

    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"
    FINISHED = "finished"
    FAILED = "failed"


class ProcessError(Exception):
    """进程执行层异常基类。"""


class ProcessStartError(ProcessError):
    """进程启动失败（非「可执行文件缺失」的启动错误）。"""


class ExecutableMissingError(ProcessStartError):
    """可执行文件不存在（找不到 ffmpeg / ffprobe 等）。"""


@dataclass(frozen=True)
class CompletedProcess:
    """一次进程执行的终态快照。"""

    exit_code: Optional[int]
    cancelled: bool = False
    stderr_tail: Tuple[str, ...] = ()
    stdout_tail: Tuple[str, ...] = ()
    argv: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """正常退出且未被取消。"""
        return not self.cancelled and self.exit_code == 0


class ProcessRunner(Protocol):
    """可取消子进程执行器的统一接口（subprocess / QProcess 两种后端）。"""

    on_stdout: Optional[OutputCallback]
    on_stderr: Optional[OutputCallback]
    on_finished: Optional[FinishedCallback]

    def start(
        self,
        cmd: Sequence[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        stdin_pipe: bool = False,
    ) -> None:
        """启动进程。可执行文件缺失抛 :class:`ExecutableMissingError`。"""

    def wait(self, timeout: Optional[float] = None) -> CompletedProcess:
        """阻塞等待进程结束，并在此期间推进取消时序。"""

    def cancel(self) -> None:
        """请求取消（线程安全、幂等、立即返回）。"""

    def is_running(self) -> bool:
        """进程是否仍在运行。"""

    @property
    def exit_code(self) -> Optional[int]:
        """已结束进程的退出码；未结束时为 None。"""

    @property
    def state(self) -> ProcessState:
        """当前生命周期状态。"""


#: runner 工厂类型：TaskContext 用它注入 GUI(QProcess) / 测试(fake) 后端
RunnerFactory = Callable[[], ProcessRunner]


def kill_process_tree(pid: int, *, timeout: float = 5.0) -> None:
    """强杀进程树。

    Windows 使用 ``taskkill /PID <pid> /T /F``（连同子进程）；其他平台
    使用 SIGKILL。任何失败都静默吞掉（调用方还有 ``process.kill()`` 兜底）。
    """
    if not pid or pid <= 0:
        return

    import os
    import signal
    import subprocess

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return
        except Exception:  # noqa: BLE001 - 兜底继续尝试 os.kill
            pass

    try:
        os.kill(int(pid), getattr(signal, "SIGKILL", signal.SIGTERM))
    except Exception:  # noqa: BLE001 - 进程可能已退出
        pass
