# -*- coding: utf-8 -*-
"""错误卡片 —— 把失败信息归类为用户可读的原因与建议操作 (展示层)。

M2.5 起错误分类迁至 :mod:`src.ffmpeg.errors` (纯 Python 领域模型)，本模块只负责:

    * :class:`ErrorInfo` / :class:`ErrorCard` —— Qt 展示模型与卡片控件；
    * :func:`error_info_from_user` —— ``UserFacingError`` -> ``ErrorInfo`` 转换；
    * :func:`classify_log_text` —— 兼容旧 UI 调用的日志文本入口，内部委托
      :func:`src.ffmpeg.errors.classify`。

``ErrorCategory`` 从新模块重新导出，``from src.ui.error_card import
ErrorCategory`` 的旧调用与既有测试继续可用。
"""

from dataclasses import dataclass, field
from typing import List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..ffmpeg.errors import ErrorCategory, UserFacingError, classify

__all__ = [
    "ErrorCard",
    "ErrorCategory",
    "ErrorInfo",
    "classify_log_text",
    "error_info_from_user",
]


@dataclass
class ErrorInfo:
    """错误卡片的展示数据 (原因用 hint 样式，动作为按钮)。"""

    title: str
    causes: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    log_tail: str = ""
    category: ErrorCategory = ErrorCategory.UNKNOWN_FFMPEG_ERROR


def error_info_from_user(error: UserFacingError) -> ErrorInfo:
    """把领域模型 UserFacingError 转为 Qt 卡片展示数据 ErrorInfo。"""
    return ErrorInfo(
        title=error.title,
        causes=list(error.causes),
        actions=list(error.actions),
        log_tail=error.log_tail,
        category=error.category,
    )


def classify_log_text(text: str) -> ErrorInfo:
    """兼容 API: 归类一段日志文本 (内部委托 src.ffmpeg.errors.classify)。"""
    return error_info_from_user(classify(text or ""))


class ErrorCard(QFrame):
    """错误卡片：标题 + 可能原因 (hint 样式) + 建议操作按钮。"""

    #: 用户点击某个建议操作 (参数: 操作文案)
    action_requested = pyqtSignal(str)
    #: 用户点击「查看完整日志」
    log_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("error_card")
        self._error = None
        self._action_buttons = []
        self._build_ui()
        self.hide()

    # ----------------------------------------------------------------
    # 公开 API
    # ----------------------------------------------------------------

    @property
    def error(self):
        """当前展示的 ErrorInfo (未展示时 None)。"""
        return self._error

    def show(self, error: ErrorInfo):
        """展示一个 ErrorInfo (替代 QWidget.show 的无参形式)。"""
        if not isinstance(error, ErrorInfo):
            raise TypeError(f"ErrorCard.show 需要 ErrorInfo，收到 {type(error).__name__}")
        self._error = error
        self._title_label.setText(error.title)
        self._render_causes(error.causes)
        self._render_actions(error.actions)
        self._log_btn.setVisible(True)
        self._log_btn.setToolTip(
            "查看完整日志" if error.log_tail else "暂无更多日志，可查看运行日志面板"
        )
        self.setVisible(True)

    # ----------------------------------------------------------------
    # 构建
    # ----------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        self._title_label = QLabel()
        self._title_label.setObjectName("error_title")
        self._title_label.setWordWrap(True)
        root.addWidget(self._title_label)

        self._cause_header = QLabel("可能的原因")
        self._cause_header.setObjectName("muted_label")
        root.addWidget(self._cause_header)

        self._causes_layout = QVBoxLayout()
        self._causes_layout.setContentsMargins(0, 0, 0, 0)
        self._causes_layout.setSpacing(2)
        root.addLayout(self._causes_layout)

        self._action_header = QLabel("建议操作")
        self._action_header.setObjectName("muted_label")
        root.addWidget(self._action_header)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        self._actions_layout = QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(8)
        actions_row.addLayout(self._actions_layout, 1)

        self._log_btn = QPushButton("查看完整日志")
        self._log_btn.setObjectName("error_log_btn")
        self._log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_btn.clicked.connect(self.log_requested.emit)
        actions_row.addWidget(self._log_btn, 0)
        root.addLayout(actions_row)

    # ----------------------------------------------------------------
    # 渲染
    # ----------------------------------------------------------------

    def _render_causes(self, causes):
        _clear_layout(self._causes_layout)
        self._cause_header.setVisible(bool(causes))
        for cause in causes:
            label = QLabel(f"•  {cause}")
            label.setObjectName("hint_info")  # 复用主题里的 hint 次要文本样式
            label.setWordWrap(True)
            self._causes_layout.addWidget(label)

    def _render_actions(self, actions):
        _clear_layout(self._actions_layout)
        self._action_buttons = []
        self._action_header.setVisible(bool(actions))
        for action in actions:
            btn = QPushButton(action)
            btn.setObjectName("error_action_btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda _checked=False, text=action: self.action_requested.emit(text)
            )
            self._actions_layout.addWidget(btn)
            self._action_buttons.append(btn)
        self._actions_layout.addStretch(1)


def _clear_layout(layout):
    """移除布局内全部控件 (延迟销毁，避免跨测试悬挂对象)。"""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
