# -*- coding: utf-8 -*-
"""侧边栏导航组件 —— 带药丸形选中指示器和平滑动画。"""

from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QWidget
from PyQt6.QtCore import (
    Qt, QSize, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect,
)
from PyQt6.QtGui import QPainter, QColor


class _PillIndicator(QWidget):
    """侧边栏选中项的药丸形指示器 (3px 宽蓝色圆角条)。"""

    _COLOR = QColor(0, 95, 184)  # #005fb8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(3)
        self.setFixedHeight(20)
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._COLOR)
        p.drawRoundedRect(self.rect(), 1.5, 1.5)
        p.end()

    def slide_to(self, target_rect: QRect):
        """平滑滑动到目标位置。"""
        if self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target_rect)
        self._anim.start()


class Sidebar(QListWidget):
    """侧边栏导航列表。通过 tab_changed 信号通知页面切换。"""

    tab_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(180)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._pill = _PillIndicator(self.viewport())
        self._pill.hide()

        self.currentRowChanged.connect(self._on_row_changed)

    def add_item(self, text: str):
        """添加一个导航项。"""
        item = QListWidgetItem(text)
        item.setSizeHint(QSize(160, 40))
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self.addItem(item)

    def _on_row_changed(self, row: int):
        self._move_pill(row)
        self.tab_changed.emit(row)

    def _move_pill(self, row: int):
        if row < 0:
            self._pill.hide()
            return

        rect = self.visualItemRect(self.item(row))
        pill_h = 20
        y = rect.y() + (rect.height() - pill_h) // 2
        target = QRect(2, y, 3, pill_h)

        if not self._pill.isVisible():
            self._pill.setGeometry(target)
            self._pill.show()
        else:
            self._pill.slide_to(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        row = self.currentRow()
        if row >= 0:
            self._move_pill(row)
