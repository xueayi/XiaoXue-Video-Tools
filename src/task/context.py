# -*- coding: utf-8 -*-
"""任务上下文 —— 协作式取消标志 + 子进程句柄注册占位。

M2.1 只提供数据结构和 ContextVar 传递：
    * ``TaskRunner.run()`` 在工作线程中 ``set_current_task(ctx)``；
    * ``request_cancel()`` 置 ``ctx.cancelled``，executor 可主动检查；
    * M2.3 将把 ``terminate/kill`` 接到 ``cancel()`` 与 ``register()/unregister()``，
      本模块的接口先固定下来，避免后续改 executor 签名。
"""

from contextvars import ContextVar, Token
from typing import Callable, List, Optional

__all__ = [
    "TaskCancelled",
    "TaskContext",
    "current_task",
    "set_current_task",
    "reset_current_task",
]


class TaskCancelled(Exception):
    """协作式取消信号：executor/runner 捕获后映射为 TaskStatus.CANCELLED。"""

    def __init__(self, message: str = "任务已取消") -> None:
        super().__init__(message)


class TaskContext:
    """单个任务的运行上下文。"""

    def __init__(self) -> None:
        self._cancelled: bool = False
        self._handles: List[object] = []
        self._request_cancel_callbacks: List[Callable[[], None]] = []

    # ----------------------------------------------------------------
    # 取消
    # ----------------------------------------------------------------

    @property
    def cancelled(self) -> bool:
        """是否已请求取消。"""
        return self._cancelled

    @property
    def request_cancel_callbacks(self):
        """已登记的取消回调（tuple，供测试/调试查看）。"""
        return tuple(self._request_cancel_callbacks)

    def add_cancel_callback(self, callback: Callable[[], None]) -> None:
        """登记取消回调（M2.3 用于终止活跃子进程）。"""
        self._request_cancel_callbacks.append(callback)

    def cancel(self) -> None:
        """请求取消：置标志并触发已登记回调（幂等，回调异常不向外抛）。"""
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
    # 子进程句柄注册（M2.3 接入 terminate/kill 的占位）
    # ----------------------------------------------------------------

    @property
    def handles(self):
        """已登记的活动句柄（tuple）。"""
        return tuple(self._handles)

    def register(self, handle: object) -> None:
        """登记一个可取消的活动句柄（占位，M2.3 将在 cancel() 中终止它）。"""
        self._handles.append(handle)

    def unregister(self, handle: object) -> None:
        """注销句柄（按对象身份匹配，重复注销无副作用）。"""
        for index, existing in enumerate(self._handles):
            if existing is handle:
                del self._handles[index]
                return


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
