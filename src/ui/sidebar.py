# -*- coding: utf-8 -*-
"""侧边栏导航组件。"""

from PyQt6.QtWidgets import QListWidget, QListWidgetItem
from PyQt6.QtCore import Qt, QSize, pyqtSignal


class Sidebar(QListWidget):
    """侧边栏导航列表。通过 tab_changed 信号通知页面切换。"""

    tab_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(160)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.currentRowChanged.connect(self.tab_changed.emit)

    def add_item(self, text):
        """添加一个导航项。"""
        item = QListWidgetItem(text)
        item.setSizeHint(QSize(140, 44))
        item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.addItem(item)
