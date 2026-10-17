# -*- coding: utf-8 -*-
"""任务结果状态 —— 执行层唯一的终态枚举。

与 ``src/ui/task_state.py`` 的 6 态视图枚举（QUEUED/RUNNING/SUCCESS/...）
刻意分离：执行层只关心「任务最终是什么结果」，UI 需要额外表达排队/执行中。
两者在 UI 接线处做一次映射（见 ``main_window._RESULT_TO_VIEW_STATUS``），
不合并成一个枚举。
"""

from enum import Enum


class TaskStatus(str, Enum):
    """任务结果状态（4 种，全部为终态）。"""

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"

    @property
    def is_terminal(self) -> bool:
        """结果状态都是终态（执行层不出现排队/执行中）。"""
        return True

    @property
    def is_ok(self) -> bool:
        """是否有产出：SUCCESS / PARTIAL。"""
        return self in (TaskStatus.SUCCESS, TaskStatus.PARTIAL)

    @property
    def label(self) -> str:
        """中文短标签（任务卡/日志使用）。"""
        return _STATUS_LABELS[self]

    @classmethod
    def coerce(cls, value: object) -> "TaskStatus":
        """把 TaskStatus / 状态字符串（值或枚举名）归一为 TaskStatus。

        None、空串、无法识别的值一律抛 ``ValueError``（结果层不接受默认态）。
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("任务结果状态不能为空字符串")
            lowered = text.lower()
            for status in cls:
                if status.value == lowered:
                    return status
            upper = text.upper()
            if upper in cls.__members__:
                return cls.__members__[upper]
        raise ValueError(f"未知任务结果状态: {value!r}")


_STATUS_LABELS = {
    TaskStatus.SUCCESS: "成功",
    TaskStatus.FAILED: "失败",
    TaskStatus.CANCELLED: "已取消",
    TaskStatus.PARTIAL: "部分完成",
}

#: 全部结果状态（按展示顺序）
ALL_STATUSES = tuple(TaskStatus)
