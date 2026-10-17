# -*- coding: utf-8 -*-
"""任务视图状态 —— 纯 Python 领域模型 (不 import Qt)。

PR-03 引入的通用组件 TaskCard / TaskArea 只消费本模块的 ``TaskViewState``，
与执行器、任务内核完全解耦；PR-06 接入主窗口时直接复用，不再改动组件内部。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    """任务状态的 6 种取值 (与 QSS 动态属性 status 一一对应)。"""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """是否终态：终态任务不能再推进进度或取消。"""
        return self not in (TaskStatus.QUEUED, TaskStatus.RUNNING)

    @property
    def is_active(self) -> bool:
        """是否正在等待/执行 (QUEUED/RUNNING)。"""
        return not self.is_terminal

    @property
    def is_ok(self) -> bool:
        """是否属于「有产出」的成功态 (SUCCESS / PARTIAL)。"""
        return self in (TaskStatus.SUCCESS, TaskStatus.PARTIAL)

    @property
    def can_cancel(self) -> bool:
        """取消按钮是否可用：仅 QUEUED / RUNNING。"""
        return self in (TaskStatus.QUEUED, TaskStatus.RUNNING)

    @property
    def label(self) -> str:
        """中文短标签 (状态胶囊文案)。"""
        return _STATUS_LABELS[self]

    @classmethod
    def coerce(cls, value) -> "TaskStatus":
        """把 str / None / TaskStatus 归一为 TaskStatus；无法识别时抛 ValueError。"""
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.QUEUED
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            raise ValueError(f"未知任务状态: {value!r}") from exc


# 中文标签 (避免散落在 UI 组件里重复定义)
_STATUS_LABELS = {
    TaskStatus.QUEUED: "排队中",
    TaskStatus.RUNNING: "执行中",
    TaskStatus.SUCCESS: "成功",
    TaskStatus.PARTIAL: "部分完成",
    TaskStatus.FAILED: "失败",
    TaskStatus.CANCELLED: "已取消",
}

# 全部状态 (按展示顺序)，供测试与外部遍历
ALL_STATUSES = tuple(TaskStatus)


def normalize_progress(value) -> Optional[float]:
    """归一进度值：None / NaN → None；其余夹到 [0, 100]。"""
    if value is None:
        return None
    try:
        progress = float(value)
    except (TypeError, ValueError):
        return None
    if progress != progress:  # NaN
        return None
    return max(0.0, min(100.0, progress))


def normalize_eta(value) -> Optional[float]:
    """归一剩余时间：None / NaN / 负数 → None。"""
    if value is None:
        return None
    try:
        eta = float(value)
    except (TypeError, ValueError):
        return None
    if eta != eta or eta < 0:  # NaN 或负数
        return None
    return eta


@dataclass
class TaskViewState:
    """单个任务卡片的视图数据。

    只描述「界面需要显示什么」，不携带任何执行器/线程引用；
    ``progress=None`` 表示进度未知 (界面渲染为不确定进度条)。
    """

    task_id: str
    title: str = ""
    status: TaskStatus = TaskStatus.QUEUED
    encoder: str = ""
    progress: Optional[float] = None      # 0–100；None = 不确定进度
    speed: float = 0.0                    # 编码速度 (倍速)
    eta_sec: Optional[float] = None       # 剩余秒数；None = 未知
    message: str = ""                     # 附加说明 (失败原因/部分完成等)
    elapsed_sec: float = 0.0              # 已耗时 (秒)
    output_path: str = ""                 # 输出文件路径

    def __post_init__(self):
        self.status = TaskStatus.coerce(self.status)
        self.progress = normalize_progress(self.progress)
        self.eta_sec = normalize_eta(self.eta_sec)

    @property
    def is_terminal(self) -> bool:
        """是否终态。"""
        return self.status.is_terminal

    @property
    def is_ok(self) -> bool:
        """是否成功 (SUCCESS / PARTIAL)。"""
        return self.status.is_ok

    @property
    def can_cancel(self) -> bool:
        """取消按钮是否可用。"""
        return self.status.can_cancel
