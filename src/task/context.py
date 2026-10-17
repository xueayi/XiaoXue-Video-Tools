# -*- coding: utf-8 -*-
"""任务上下文 —— 协作式取消标志、runner 工厂与子进程句柄注册。

M2.3 起：
    * ``TaskRunner`` 在工作线程中 ``set_current_task(ctx)``，``cancel()`` 置标志；
    * :meth:`TaskContext.register` 把活跃的 ``ProcessRunner`` 绑到取消回调，
      ``cancel()`` 触发回调（异常吞掉、幂等），回调内的 ``runner.cancel()``
      只置线程安全事件，真正的 terminate/kill 时序由 runner 的 wait() 推进；
    * 工厂解析：实例注入 > 模块级默认 > ``SubprocessRunner``；GUI 侧
      TaskRunner 注入 QProcess 后端，纯后端测试可注入 fake；
    * ``progress_callback``（M2.4）：GUI 侧 TaskRunner 设置的 stdout 进度行
      回调（ffmpeg ``-progress`` 的 ``key=value``），由 core 消费后转发到
      UI 解析器；非 GUI 场景保持 None。
"""

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Callable, List, Optional

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查
    from ..process.base import ProcessRunner, RunnerFactory

__all__ = [
    "TaskCancelled",
    "TaskContext",
    "current_task",
    "get_runner_factory",
    "reset_current_task",
    "set_current_task",
    "set_runner_factory",
]


class TaskCancelled(Exception):
    """协作式取消信号：executor/runner 捕获后映射为 TaskStatus.CANCELLED。"""

    def __init__(self, message: str = "任务已取消") -> None:
        super().__init__(message)


# ----------------------------------------------------------------
# runner 工厂解析（模块级默认，可被 TaskContext 实例覆盖）
# ----------------------------------------------------------------

_default_runner_factory: Optional[Callable[[], object]] = None


def set_runner_factory(factory: Optional[Callable[[], object]]) -> None:
    """设置模块级默认 runner 工厂；None 表示恢复为 SubprocessRunner。"""
    global _default_runner_factory
    _default_runner_factory = factory


def get_runner_factory() -> Callable[[], object]:
    """解析默认 runner 工厂（未显式设置时使用 subprocess 后端）。"""
    if _default_runner_factory is not None:
        return _default_runner_factory
    from ..process.subprocess_runner import SubprocessRunner

    return SubprocessRunner


def _make_handle_cancel(handle: object) -> Callable[[], None]:
    """把 runner 句柄包装成取消回调（优先 cancel，其次 terminate）。"""

    def _cancel_handle() -> None:
        cancel = getattr(handle, "cancel", None)
        if callable(cancel):
            cancel()
            return
        terminate = getattr(handle, "terminate", None)
        if callable(terminate):
            terminate()

    return _cancel_handle


class TaskContext:
    """单个任务的运行上下文。"""

    def __init__(
        self,
        runner_factory: Optional[Callable[[], object]] = None,
    ) -> None:
        self._cancelled: bool = False
        self._handles: List[object] = []
        self._request_cancel_callbacks: List[Callable[[], None]] = []
        self._handle_cancel_callbacks: dict = {}
        self._runner_factory = runner_factory
        #: stdout 进度行回调 (M2.4); GUI 由 TaskRunner 设置, 非 GUI 保持 None
        self.progress_callback: Optional[Callable[[str], None]] = None

    # ----------------------------------------------------------------
    # runner 工厂
    # ----------------------------------------------------------------

    @property
    def factory(self) -> Callable[[], object]:
        """解析后的 runner 工厂：实例注入 > 模块级默认 > SubprocessRunner。"""
        return self._runner_factory or get_runner_factory()

    def set_runner_factory(
        self, factory: Optional[Callable[[], object]]
    ) -> None:
        """覆盖本任务的 runner 工厂（None 表示回退到模块级默认）。"""
        self._runner_factory = factory

    def create_runner(self) -> "ProcessRunner":
        """创建一个新的 runner 实例（由 core 在执行每条命令前调用）。"""
        factory = self.factory
        return factory()

    # ----------------------------------------------------------------
    # 取消
    # ----------------------------------------------------------------

    @property
    def cancelled(self) -> bool:
        """是否已请求取消。"""
        return self._cancelled

    @property
    def request_cancel_callbacks(self):
        """已登记的取消回调（tuple，含句柄取消回调，供测试/调试查看）。"""
        return tuple(self._request_cancel_callbacks)

    def add_cancel_callback(self, callback: Callable[[], None]) -> None:
        """登记取消回调（如额外清理动作）。"""
        self._request_cancel_callbacks.append(callback)

    def cancel(self) -> None:
        """请求取消：置标志并触发全部回调（幂等，回调异常不向外抛）。"""
        if self._cancelled:
            return
        self._cancelled = True
        for callback in tuple(self._request_cancel_callbacks):
            try:
                callback()
            except Exception:  # noqa: BLE001 - 取消回调不得影响主流程
                pass

    def raise_if_cancelled(self) -> None:
        """已请求取消时抛 TaskCancelled，供长循环主动退出。"""
        if self._cancelled:
            raise TaskCancelled("任务已取消")

    # ----------------------------------------------------------------
    # 子进程句柄注册（真正绑定到 cancel 回调）
    # ----------------------------------------------------------------

    @property
    def handles(self):
        """已登记的活动句柄（tuple）。"""
        return tuple(self._handles)

    def register(self, handle: object) -> None:
        """登记活动 runner 句柄：cancel() 时调用其 cancel()。

        若登记时任务已请求取消，则立即取消该句柄（覆盖「取消先于启动」竞态）。
        """
        if any(existing is handle for existing in self._handles):
            return
        self._handles.append(handle)
        callback = _make_handle_cancel(handle)
        self._handle_cancel_callbacks[id(handle)] = callback
        self._request_cancel_callbacks.append(callback)
        if self._cancelled:
            try:
                callback()
            except Exception:  # noqa: BLE001
                pass

    def unregister(self, handle: object) -> None:
        """注销句柄（按对象身份匹配，重复注销无副作用）。"""
        for index, existing in enumerate(self._handles):
            if existing is handle:
                del self._handles[index]
                break
        callback = self._handle_cancel_callbacks.pop(id(handle), None)
        if callback is not None:
            for index, existing in enumerate(self._request_cancel_callbacks):
                if existing is callback:
                    del self._request_cancel_callbacks[index]
                    break


# ----------------------------------------------------------------
# ContextVar 传递（TaskRunner.run 中 set/reset）
# ----------------------------------------------------------------

_current_task: ContextVar[Optional[TaskContext]] = ContextVar(
    "xiaoxue_current_task", default=None)


def current_task() -> Optional[TaskContext]:
    """当前线程/上下文中运行的任务上下文；不在任务中时为 None。"""
    return _current_task.get()


def set_current_task(context: Optional[TaskContext]) -> Token:
    """把 task context 设为当前上下文，返回用于恢复的 token。"""
    return _current_task.set(context)


def reset_current_task(token: Token) -> None:
    """恢复 set_current_task 之前的上下文。"""
    _current_task.reset(token)
