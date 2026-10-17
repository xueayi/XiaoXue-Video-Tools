# -*- coding: utf-8 -*-
"""任务结果模型 —— 执行层与 UI 之间唯一的结果数据源。

约定（M2 重构）：
    * ``execute_*`` 返回 ``TaskResult``，不再用「return None / 只 print」表达状态；
    * FFmpeg 非零退出必须进入 ``exit_code`` 且状态为 FAILED；
    * 用户取消是 CANCELLED，不是 FAILED；
    * 批量任务部分失败是 PARTIAL（见 :mod:`src.task.report`）。
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Tuple

from .status import TaskStatus


def _as_tuple(value) -> Tuple[Any, ...]:
    """把 None / 单个字符串 / 可迭代对象归一为 tuple。"""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


@dataclass(frozen=True)
class TaskResult:
    """一次任务的执行结果。

    Attributes:
        status: 结果状态。
        exit_code: 子进程退出码（无子进程或未知时为 None）。
        message: 面向用户的说明（失败原因 / 部分完成汇总等）。
        warnings: 不阻断成功但需要提示的问题（构造时自动归一为 tuple）。
        outputs: 产出的文件路径（失败时保留已产出的文件）。
        details: 附加结构化信息（dry_run、mode、traceback 等）。
    """

    status: TaskStatus
    exit_code: Optional[int] = None
    message: str = ""
    warnings: Tuple[str, ...] = ()
    outputs: Tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", TaskStatus.coerce(self.status))
        object.__setattr__(self, "warnings", _as_tuple(self.warnings))
        object.__setattr__(self, "outputs", _as_tuple(self.outputs))
        object.__setattr__(self, "details", dict(self.details or {}))

    @property
    def is_ok(self) -> bool:
        """是否有产出（SUCCESS / PARTIAL）。"""
        return self.status.is_ok

    @property
    def legacy_success(self) -> bool:
        """兼容旧 bool 信号：仅 SUCCESS 为 True（PARTIAL 不算成功）。"""
        return self.status is TaskStatus.SUCCESS

    @classmethod
    def ok(
        cls,
        message: str = "",
        *,
        outputs: Iterable[str] = (),
        warnings: Iterable[str] = (),
        exit_code: int = 0,
        details: Optional[Mapping[str, Any]] = None,
    ) -> "TaskResult":
        """构造成功结果。"""
        return cls(
            TaskStatus.SUCCESS,
            exit_code=exit_code,
            message=message,
            warnings=warnings,
            outputs=outputs,
            details=details or {},
        )

    @classmethod
    def failed(
        cls,
        message: str = "",
        *,
        exit_code: Optional[int] = None,
        warnings: Iterable[str] = (),
        outputs: Iterable[str] = (),
        details: Optional[Mapping[str, Any]] = None,
    ) -> "TaskResult":
        """构造失败结果（message 应可直接展示给用户）。"""
        return cls(
            TaskStatus.FAILED,
            exit_code=exit_code,
            message=message,
            warnings=warnings,
            outputs=outputs,
            details=details or {},
        )

    @classmethod
    def cancelled(
        cls,
        message: str = "用户取消",
        *,
        exit_code: Optional[int] = None,
        warnings: Iterable[str] = (),
        outputs: Iterable[str] = (),
        details: Optional[Mapping[str, Any]] = None,
    ) -> "TaskResult":
        """构造取消结果。"""
        return cls(
            TaskStatus.CANCELLED,
            exit_code=exit_code,
            message=message,
            warnings=warnings,
            outputs=outputs,
            details=details or {},
        )

    @classmethod
    def partial(
        cls,
        message: str = "",
        *,
        exit_code: int = 0,
        warnings: Iterable[str] = (),
        outputs: Iterable[str] = (),
        details: Optional[Mapping[str, Any]] = None,
    ) -> "TaskResult":
        """构造部分完成结果（有成功也有失败）。"""
        return cls(
            TaskStatus.PARTIAL,
            exit_code=exit_code,
            message=message,
            warnings=warnings,
            outputs=outputs,
            details=details or {},
        )
