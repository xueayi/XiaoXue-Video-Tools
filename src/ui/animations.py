# -*- coding: utf-8 -*-
"""可复用动画工具集 —— 页面过渡、按钮脉冲、淡入效果。"""

from PyQt6.QtCore import (
    QPropertyAnimation, QEasingCurve, QPoint, QTimer, QParallelAnimationGroup,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget, QStackedWidget


def fade_in(widget: QWidget, duration: int = 220):
    """对 widget 做 opacity 0→1 淡入。返回 QPropertyAnimation 以延长生命周期。"""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


class AnimatedStackedWidget(QStackedWidget):
    """带页面切换动画的 QStackedWidget。

    切换时当前页面向左滑出 + 淡出，新页面从右滑入 + 淡入。
    """

    _DURATION = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim_group = None
        self._is_animating = False

    def slide_to(self, index: int):
        if index == self.currentIndex() or self._is_animating:
            return
        if index < 0 or index >= self.count():
            return

        going_right = index > self.currentIndex()

        current_w = self.currentWidget()
        next_w = self.widget(index)
        if not current_w or not next_w:
            self.setCurrentIndex(index)
            return

        width = self.width()
        offset = width if going_right else -width

        next_w.setGeometry(0, 0, width, self.height())
        next_w.move(QPoint(offset, 0))
        next_w.show()
        next_w.raise_()

        self._is_animating = True
        group = QParallelAnimationGroup(self)

        # current slides out
        anim_out = QPropertyAnimation(current_w, b"pos", self)
        anim_out.setStartValue(QPoint(0, 0))
        anim_out.setEndValue(QPoint(-offset, 0))
        anim_out.setDuration(self._DURATION)
        anim_out.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(anim_out)

        # next slides in
        anim_in = QPropertyAnimation(next_w, b"pos", self)
        anim_in.setStartValue(QPoint(offset, 0))
        anim_in.setEndValue(QPoint(0, 0))
        anim_in.setDuration(self._DURATION)
        anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(anim_in)

        # fade in next
        effect = QGraphicsOpacityEffect(next_w)
        next_w.setGraphicsEffect(effect)
        anim_fade = QPropertyAnimation(effect, b"opacity", self)
        anim_fade.setStartValue(0.4)
        anim_fade.setEndValue(1.0)
        anim_fade.setDuration(self._DURATION)
        group.addAnimation(anim_fade)

        def _on_finished():
            self._is_animating = False
            self.setCurrentIndex(index)
            current_w.move(QPoint(0, 0))
            next_w.move(QPoint(0, 0))
            next_w.setGraphicsEffect(None)

        group.finished.connect(_on_finished)
        self._anim_group = group
        group.start()


def button_press_anim(button: QWidget):
    """按钮按下时的微缩动画 (先缩小再弹回)。"""
    anim = QPropertyAnimation(button, b"geometry", button)
    geo = button.geometry()
    shrink = 2
    anim.setStartValue(geo)
    anim.setKeyValueAt(0.3, geo.adjusted(shrink, shrink, -shrink, -shrink))
    anim.setEndValue(geo)
    anim.setDuration(180)
    anim.setEasingCurve(QEasingCurve.Type.OutBack)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def status_flash(widget: QWidget, color: str = "#4caf50", duration: int = 1500):
    """状态栏颜色闪烁：短暂变色后恢复。"""
    original = widget.styleSheet()
    widget.setStyleSheet(
        f"QStatusBar {{ background-color: {color}; color: white; "
        f"border-top: 1px solid {color}; font-size: 12px; padding: 3px 10px; }}"
    )
    QTimer.singleShot(duration, lambda: widget.setStyleSheet(original))
