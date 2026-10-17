# -*- coding: utf-8 -*-
"""任务结果基础层（M2.1）。

导出：
    * :class:`TaskStatus` —— 4 种终态结果状态；
    * :class:`TaskResult` —— 执行层唯一结果模型；
    * :class:`TaskReport` —— 批量任务结果累积器；
    * :class:`TaskContext` / :class:`TaskCancelled` —— 协作式取消上下文。

注意：UI 侧 ``src/ui/task_state.py`` 另有 6 态视图枚举（含 QUEUED/RUNNING），
两者不合并，只在 UI 接线处做一次 result -> view 映射。
"""

from .context import (
    TaskCancelled,
    TaskContext,
    current_task,
    reset_current_task,
    set_current_task,
)
from .report import TaskReport
from .result import TaskResult
from .status import ALL_STATUSES, TaskStatus

__all__ = [
    "ALL_STATUSES",
    "TaskCancelled",
    "TaskContext",
    "TaskReport",
    "TaskResult",
    "TaskStatus",
    "current_task",
    "reset_current_task",
    "set_current_task",
]
