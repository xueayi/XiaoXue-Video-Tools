# -*- coding: utf-8 -*-
"""进度仪表盘 —— 显示 FFmpeg 编码的实时指标卡片和进度条。"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QProgressBar,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve


class _MetricCard(QFrame):
    """单个指标卡片：大号数值 + 小号标签。"""

    def __init__(self, label_text: str, initial: str = "--", parent=None):
        super().__init__(parent)
        self.setObjectName("metric_card")
        self.setFixedHeight(68)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._value_label = QLabel(initial)
        self._value_label.setObjectName("metric_value")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._value_label)

        self._desc_label = QLabel(label_text)
        self._desc_label.setObjectName("metric_label")
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._desc_label)

    def set_value(self, text: str):
        if self._value_label.text() != text:
            self._value_label.setText(text)


class ProgressDashboard(QWidget):
    """进度仪表盘：4 个指标卡片 + 进度条，任务未运行时隐藏。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("progress_dashboard")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 4)
        root.setSpacing(6)

        # 指标卡片行
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        self._card_progress = _MetricCard("进度")
        self._card_speed = _MetricCard("速度")
        self._card_frame = _MetricCard("帧")
        self._card_eta = _MetricCard("剩余时间")
        for c in (self._card_progress, self._card_speed,
                  self._card_frame, self._card_eta):
            cards_row.addWidget(c)
        root.addLayout(cards_row)

        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("dashboard_progress")
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        root.addWidget(self._progress_bar)

        self.hide()

    def show_indeterminate(self):
        """显示为不确定进度 (任务开始但无 FFmpeg 进度数据时)。"""
        self._reset_cards()
        self._progress_bar.setRange(0, 0)
        self.show()

    def update_metrics(self, info):
        """接收 ProgressInfo 对象并更新卡片和进度条。"""
        if self._progress_bar.maximum() == 0 and info.percent > 0:
            self._progress_bar.setRange(0, 1000)

        self._card_progress.set_value(f"{info.percent:.1f}%")

        if info.speed > 0:
            self._card_speed.set_value(f"{info.speed:.2f}x")
        else:
            self._card_speed.set_value("--")

        if info.frame > 0:
            self._card_frame.set_value(str(info.frame))

        if info.eta_sec >= 0:
            self._card_eta.set_value(self._fmt_eta(info.eta_sec))
        else:
            self._card_eta.set_value("--")

        self._progress_bar.setValue(int(info.percent * 10))
        self.show()

    def finish(self, success: bool):
        """任务完成时将进度条填满并短暂显示。"""
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(1000)
        if success:
            self._card_progress.set_value("100%")
            self._card_eta.set_value("完成")
        else:
            self._card_progress.set_value("失败")
            self._card_eta.set_value("--")

    def reset(self):
        """隐藏仪表盘并重置数据。"""
        self._reset_cards()
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(0)
        self.hide()

    def _reset_cards(self):
        self._card_progress.set_value("--")
        self._card_speed.set_value("--")
        self._card_frame.set_value("--")
        self._card_eta.set_value("--")

    @staticmethod
    def _fmt_eta(seconds: float) -> str:
        if seconds < 0:
            return "--"
        s = int(seconds)
        if s >= 3600:
            return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
        return f"{s // 60:02d}:{s % 60:02d}"
