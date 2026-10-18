# -*- coding: utf-8 -*-
"""任务详情对话框 —— 展示单条任务记录并提供「打开文件夹」。

背景: 首页/执行区的任务卡「详情」按钮此前没有接收方(点击无效)。
本对话框消费 :class:`src.ui.task_state.TaskViewState`, 只读展示, 不接触执行层。
"""

import os

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout,
)

from . import icons
from .widgets import make_form_layout
from .task_state import TaskStatus, TaskViewState


def open_path_in_file_manager(path: str) -> bool:
    """在系统文件管理器中打开目录 (或定位到文件所在目录)。"""
    text = str(path or "").strip()
    if not text:
        return False
    target = text if os.path.isdir(text) else os.path.dirname(text)
    if not target or not os.path.isdir(target):
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(target))


class TaskDetailsDialog(QDialog):
    """只读的任务详情 + 产出定位。"""

    def __init__(self, state: TaskViewState = None, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("任务详情")
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        form = make_form_layout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        title_label = QLabel(state.title if state else "")
        title_label.setObjectName("strong_label")
        title_label.setWordWrap(True)
        form.addRow("任务", title_label)

        status_label = QLabel(self._status_text(state))
        status_label.setObjectName("muted_label")
        form.addRow("状态", status_label)

        message = (state.message if state else "") or "—"
        message_label = QLabel(message)
        message_label.setObjectName("muted_label")
        message_label.setWordWrap(True)
        form.addRow("说明", message_label)

        output = (state.output_path if state else "") or "—"
        self._output_label = QLabel(output)
        self._output_label.setObjectName("muted_label")
        self._output_label.setWordWrap(True)
        self._output_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("产出文件", self._output_label)

        root.addLayout(form)
        root.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._folder_btn = QPushButton("打开文件夹")
        self._folder_btn.setIcon(icons.secondary("ri.folder-open-line"))
        self._folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._folder_btn.setEnabled(bool(state and state.output_path))
        self._folder_btn.clicked.connect(self._open_folder)
        buttons.addWidget(self._folder_btn)
        buttons.addStretch(1)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        box.accepted.connect(self.accept)
        buttons.addWidget(box)
        root.addLayout(buttons)

    # ----------------------------------------------------------------

    @staticmethod
    def _status_text(state) -> str:
        if state is None:
            return "—"
        status = TaskStatus.coerce(state.status)
        return status.label

    def _open_folder(self):
        if self.state is not None:
            open_path_in_file_manager(self.state.output_path)
