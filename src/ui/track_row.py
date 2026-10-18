# -*- coding: utf-8 -*-
"""轨道行控件 —— 把「音轨/字幕轨」渲染成有框线的轨道条目。

设计:
- 左侧复选框 (勾选表示保留) + 主标题 (如 ``#0  aac``) + 右侧次要信息 (声道/语言/标题);
- ``QFrame#track_row`` 由主题 QSS 提供卡片式边框, 勾选态用强调色边框,
  比裸 QCheckBox 更有「轨道」感;
- 对外暴露 ``isChecked/setChecked/isEnabled/setEnabled`` 等代理方法,
  既有 ``(checkbox, index)`` 结构可无缝替换。
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QSizePolicy,
)

from .base_tab import repolish


class TrackRow(QFrame):
    """单条轨道 (音频或字幕) 的卡片式勾选行。"""

    toggled = pyqtSignal(bool)

    def __init__(self, title: str, detail: str = "", checked: bool = False,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("track_row")
        self.setProperty("checked", bool(checked))
        # 轨道行保持紧凑高度, 不被父布局拉伸成大块
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(10)

        self.checkbox = QCheckBox(title)
        self.checkbox.setChecked(bool(checked))
        layout.addWidget(self.checkbox, 1)

        self.detail_label = QLabel(detail or "")
        self.detail_label.setObjectName("muted_label")
        self.detail_label.setWordWrap(False)
        self.detail_label.setToolTip(detail or "")
        if not detail:
            self.detail_label.setVisible(False)
        layout.addWidget(self.detail_label, 2)

        self.checkbox.toggled.connect(self._on_toggled)

    # ----------------------------------------------------------------
    # 状态代理 (兼容旧的 (QCheckBox, index) 用法)
    # ----------------------------------------------------------------

    def _on_toggled(self, checked: bool) -> None:
        self.setProperty("checked", bool(checked))
        repolish(self)
        self.toggled.emit(bool(checked))

    def isChecked(self) -> bool:  # noqa: N802 - 与 QCheckBox 保持一致
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        self.checkbox.setChecked(bool(checked))

    def isEnabled(self) -> bool:  # noqa: N802
        return self.checkbox.isEnabled()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        self.checkbox.setEnabled(bool(enabled))
        super().setEnabled(bool(enabled))
