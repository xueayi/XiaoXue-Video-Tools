# -*- coding: utf-8 -*-
"""任务卡片与任务区域 —— 底部执行区的通用组件。

``TaskCard`` 渲染单个 :class:`TaskViewState` (6 态)：标题、状态胶囊、
编码器/速度/剩余时间/耗时/输出路径、进度条、消息行。取消按钮仅在
QUEUED / RUNNING 可用，且只发信号不直接操作线程 (真实取消由 PR-09 接入)。

``TaskArea`` 管理一组卡片 (set_tasks / update_task / clear)，并内置一组
兼容旧 ``ProgressDashboard`` 的适配方法 (show_indeterminate / update_metrics /
finish / reset)，供 PR-06 平滑替换主窗口底部的仪表盘。

颜色一律来自 ``theme`` 令牌 (QSS 动态属性 + :func:`status_color`)，不硬编码色值。
"""

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .base_tab import repolish
from .formatting import fmt_duration, fmt_eta, fmt_percent, fmt_speed
from .task_state import TaskStatus, TaskViewState

# 旧 ProgressDashboard 适配时使用的固定任务 id
CURRENT_TASK_ID = "__current__"

# 状态 → 主题令牌 (代码侧取色用；QSS 中按动态属性 status 匹配同名令牌)
_STATUS_COLOR_TOKENS = {
    TaskStatus.QUEUED: "text_tertiary",
    TaskStatus.RUNNING: "accent",
    TaskStatus.SUCCESS: "success",
    TaskStatus.PARTIAL: "warning",
    TaskStatus.FAILED: "danger",
    TaskStatus.CANCELLED: "text_secondary",
}


def status_color(status: TaskStatus) -> str:
    """返回状态对应的主题色 (代码侧取色，供外部指示器复用)。"""
    return theme.color(_STATUS_COLOR_TOKENS[TaskStatus.coerce(status)])


class TaskCard(QFrame):
    """单个任务卡片：set_state(TaskViewState) 一次性驱动全部显示。"""

    #: 用户点击「取消」(参数: task_id)
    cancel_requested = pyqtSignal(str)
    #: 用户点击「详情」(参数: task_id)
    details_requested = pyqtSignal(str)

    def __init__(self, state: TaskViewState = None, parent=None):
        super().__init__(parent)
        self.setObjectName("task_card")
        self._state = None
        self._build_ui()
        if state is not None:
            self.set_state(state)

    # ----------------------------------------------------------------
    # 公开 API
    # ----------------------------------------------------------------

    @property
    def state(self):
        """当前视图状态 (TaskViewState 或 None)。"""
        return self._state

    @property
    def task_id(self) -> str:
        """当前任务 id (未设置状态时为空串)。"""
        return self._state.task_id if self._state is not None else ""

    def set_state(self, state: TaskViewState):
        """按新的 TaskViewState 刷新卡片。"""
        if not isinstance(state, TaskViewState):
            raise TypeError(
                f"TaskCard.set_state 需要 TaskViewState，收到 {type(state).__name__}"
            )
        self._state = state
        status = state.status

        # 卡片与状态胶囊都挂动态属性 status，由 QSS 按主题令牌着色
        self.setProperty("status", status.value)
        repolish(self)

        self._title_label.setText(state.title or "（未命名任务）")
        self._status_label.setText(status.label)
        self._status_label.setProperty("status", status.value)
        repolish(self._status_label)

        self._render_meta(state)
        self._render_message(state)
        self._render_progress(state)

        # 取消按钮只在 QUEUED / RUNNING 可用 (终态直接隐藏)
        can_cancel = status.can_cancel
        self._cancel_btn.setEnabled(can_cancel)
        self._cancel_btn.setVisible(can_cancel)

    # ----------------------------------------------------------------
    # 构建
    # ----------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(4)

        # 标题行: 标题 + 状态胶囊 + 详情/取消按钮
        header = QHBoxLayout()
        header.setSpacing(8)
        self._title_label = QLabel()
        self._title_label.setObjectName("task_card_title")
        header.addWidget(self._title_label, 1)

        self._status_label = QLabel()
        self._status_label.setObjectName("task_status")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._status_label, 0)

        self._details_btn = QToolButton()
        self._details_btn.setObjectName("task_details_btn")
        self._details_btn.setText("详情")
        self._details_btn.setToolTip("查看任务详情")
        self._details_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._details_btn.clicked.connect(self._emit_details)
        header.addWidget(self._details_btn, 0)

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setObjectName("task_cancel_btn")
        self._cancel_btn.setToolTip("取消任务 (只发送请求，实际取消由执行层完成)")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self._emit_cancel)
        self._cancel_btn.hide()  # 未 set_state 前不显示取消按钮
        header.addWidget(self._cancel_btn, 0)
        root.addLayout(header)

        # 元信息行: 编码器 · 速度 · 剩余 · 耗时 · 输出
        self._meta_label = QLabel()
        self._meta_label.setObjectName("task_card_meta")
        root.addWidget(self._meta_label)

        # 消息行 (失败原因 / 部分完成说明)
        self._message_label = QLabel()
        self._message_label.setObjectName("task_card_message")
        self._message_label.setWordWrap(True)
        root.addWidget(self._message_label)

        # 进度行: 进度条 + 百分比
        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)
        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("dashboard_progress")
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        progress_row.addWidget(self._progress_bar, 1)

        self._percent_label = QLabel()
        self._percent_label.setObjectName("task_percent")
        self._percent_label.setMinimumWidth(44)
        self._percent_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        progress_row.addWidget(self._percent_label, 0)
        root.addLayout(progress_row)

    # ----------------------------------------------------------------
    # 渲染
    # ----------------------------------------------------------------

    def _render_meta(self, state: TaskViewState):
        parts = []
        if state.encoder:
            parts.append(state.encoder)
        if state.status == TaskStatus.RUNNING and state.speed > 0:
            parts.append(fmt_speed(state.speed))
        if state.status == TaskStatus.RUNNING and state.eta_sec is not None:
            parts.append(f"剩余 {fmt_eta(state.eta_sec)}")
        if state.elapsed_sec > 0:
            parts.append(f"耗时 {fmt_duration(state.elapsed_sec)}")
        if state.output_path:
            parts.append(f"输出 {os.path.basename(state.output_path) or state.output_path}")
        text = "  ·  ".join(parts)
        self._meta_label.setText(text)
        self._meta_label.setVisible(bool(text))
        self._meta_label.setToolTip(state.output_path or "")

    def _render_message(self, state: TaskViewState):
        self._message_label.setText(state.message)
        self._message_label.setVisible(bool(state.message))
        self._message_label.setProperty("status", state.status.value)
        repolish(self._message_label)

    def _render_progress(self, state: TaskViewState):
        if state.progress is None:
            if state.status.is_terminal:
                # 终态且没有进度数据时不再显示进度条
                self._progress_bar.hide()
                self._percent_label.hide()
                return
            # 不确定进度 (忙碌态)
            self._progress_bar.show()
            self._progress_bar.setRange(0, 0)
            self._percent_label.setText("--")
            self._percent_label.show()
            return

        self._progress_bar.show()
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(int(round(state.progress * 10)))
        self._percent_label.setText(fmt_percent(state.progress))
        self._percent_label.show()

    # ----------------------------------------------------------------
    # 信号
    # ----------------------------------------------------------------

    def _emit_cancel(self):
        if self._state is not None and self._state.status.can_cancel:
            self.cancel_requested.emit(self._state.task_id)

    def _emit_details(self):
        if self._state is not None:
            self.details_requested.emit(self._state.task_id)


class TaskArea(QWidget):
    """任务区域：管理一组 TaskCard，并兼容旧进度仪表盘 API。"""

    #: 任意卡片触发的取消请求 (参数: task_id)
    cancel_requested = pyqtSignal(str)
    #: 任意卡片触发的详情请求 (参数: task_id)
    details_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("task_area")
        self._cards = {}
        self._states = {}

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(6)

        self._placeholder = QLabel("暂无执行中的任务")
        self._placeholder.setObjectName("task_area_placeholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.addWidget(self._placeholder)

        # 旧仪表盘初始为隐藏状态，这里保持一致
        self.hide()

    # ----------------------------------------------------------------
    # 主 API
    # ----------------------------------------------------------------

    def set_tasks(self, states):
        """整体替换任务列表并显示任务区。"""
        self.clear()
        for state in states:
            self._add_card(state)
        self._placeholder.setVisible(not self._cards)
        self.show()

    def update_task(self, state: TaskViewState):
        """新增或刷新单个任务卡片，返回对应 TaskCard。"""
        card = self._cards.get(state.task_id)
        if card is None:
            card = self._add_card(state)
        else:
            card.set_state(state)
            self._states[state.task_id] = state
        self._placeholder.setVisible(False)
        self.show()
        return card

    def clear(self):
        """移除全部卡片 (不改变自身可见性；reset() 会额外隐藏)。"""
        for card in self._cards.values():
            self._root.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._states.clear()
        self._placeholder.setVisible(True)

    @property
    def task_ids(self):
        """当前卡片 id 列表 (按加入顺序)。"""
        return list(self._cards.keys())

    # ----------------------------------------------------------------
    # 旧 ProgressDashboard 适配 (PR-06 平滑替换用)
    # ----------------------------------------------------------------

    def show_indeterminate(self, title: str = "执行中", encoder: str = ""):
        """兼容旧 ProgressDashboard.show_indeterminate()。"""
        state = TaskViewState(
            task_id=CURRENT_TASK_ID,
            title=title,
            status=TaskStatus.RUNNING,
            encoder=encoder,
            progress=None,
        )
        self.update_task(state)

    def update_metrics(self, info):
        """兼容旧 ProgressDashboard.update_metrics(ProgressInfo)。"""
        current = self._states.get(CURRENT_TASK_ID)
        if current is None:
            current = TaskViewState(task_id=CURRENT_TASK_ID, title="执行中")
        state = TaskViewState(
            task_id=CURRENT_TASK_ID,
            title=current.title,
            status=TaskStatus.RUNNING,
            encoder=current.encoder,
            progress=getattr(info, "percent", None),
            speed=getattr(info, "speed", 0.0) or 0.0,
            eta_sec=getattr(info, "eta_sec", None),
            message=current.message,
            elapsed_sec=current.elapsed_sec,
            output_path=current.output_path,
        )
        self.update_task(state)

    def finish(self, success: bool):
        """兼容旧 ProgressDashboard.finish(success: bool)。"""
        current = self._states.get(CURRENT_TASK_ID)
        if current is None:
            current = TaskViewState(task_id=CURRENT_TASK_ID, title="执行中")
        status = TaskStatus.SUCCESS if success else TaskStatus.FAILED
        state = TaskViewState(
            task_id=CURRENT_TASK_ID,
            title=current.title,
            status=status,
            encoder=current.encoder,
            progress=100.0,
            speed=current.speed,
            eta_sec=0.0,
            message="任务完成" if success else "任务失败",
            elapsed_sec=current.elapsed_sec,
            output_path=current.output_path,
        )
        self.update_task(state)

    def reset(self):
        """兼容旧 ProgressDashboard.reset()：清空并隐藏任务区。"""
        self.clear()
        self.hide()

    # ----------------------------------------------------------------
    # 内部
    # ----------------------------------------------------------------

    def _add_card(self, state: TaskViewState) -> TaskCard:
        card = TaskCard(state)
        card.cancel_requested.connect(self.cancel_requested.emit)
        card.details_requested.connect(self.details_requested.emit)
        self._root.addWidget(card)
        self._cards[state.task_id] = card
        self._states[state.task_id] = state
        return card
