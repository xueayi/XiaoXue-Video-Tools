# -*- coding: utf-8 -*-
"""进程执行抽象层（M2.3）。

导出:
    * :class:`ProcessRunner` / :class:`ProcessState` / :class:`CompletedProcess`
      —— 统一协议与结果模型；
    * :class:`SubprocessRunner` —— Popen 后端（测试/无 Qt 场景默认）；
    * :class:`QProcessRunner` —— QProcess 后端（GUI 经 TaskContext 注入）；
    * :func:`resolve_runner` —— 按当前 TaskContext 解析后端实例；
    * :func:`run` —— 阻塞式执行并返回 ``CompletedProcess``；
    * :class:`ExecutableMissingError` / :class:`ProcessStartError`。
"""

from typing import TYPE_CHECKING, Optional

from .base import (
    CompletedProcess,
    ExecutableMissingError,
    FinishedCallback,
    OutputCallback,
    ProcessError,
    ProcessRunner,
    ProcessStartError,
    ProcessState,
    RunnerFactory,
    kill_process_tree,
)

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查
    from ..task.context import TaskContext

__all__ = [
    "CompletedProcess",
    "ExecutableMissingError",
    "FinishedCallback",
    "OutputCallback",
    "ProcessError",
    "ProcessRunner",
    "ProcessStartError",
    "ProcessState",
    "RunnerFactory",
    "SubprocessRunner",
    "QProcessRunner",
    "kill_process_tree",
    "resolve_runner",
    "run",
]


def resolve_runner(context: "Optional[TaskContext]" = None) -> ProcessRunner:
    """按当前 TaskContext 解析 runner 实例。

    - ``context`` 未传时取当前线程的 ``current_task()``；
    - 有 context 时使用其注入的工厂（GUI=QProcess，测试=fake）；
    - 无 context（CLI/单元测试）时退回 :class:`SubprocessRunner`。
    """
    if context is None:
        from ..task.context import current_task

        context = current_task()
    if context is not None:
        return context.create_runner()
    from .subprocess_runner import SubprocessRunner

    return SubprocessRunner()


from .qprocess_runner import QProcessRunner  # noqa: E402  (导出便利, Qt 已随 GUI 依赖)
from .subprocess_runner import SubprocessRunner, run  # noqa: E402
