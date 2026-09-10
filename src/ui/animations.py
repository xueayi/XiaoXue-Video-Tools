# -*- coding: utf-8 -*-
"""可复用动画工具集 —— 页面过渡、按钮脉冲、状态栏闪烁。"""

from PyQt6.QtCore import (
    QPropertyAnimation, QEasingCurve, QPoint, QTimer, QParallelAnimationGroup,
)
from PyQt6.QtWidgets import QWidget, QStackedWidget

from . import theme


class AnimatedStackedWidget(QStackedWidget):
    """带页面切换动画的 QStackedWidget。

    切换时当前页面向左滑出，新页面从右滑入 (纯位移, 不做整页透明度,
    避免复杂页面在 Windows 上掉帧)。开启「减少动画」时立即切换。
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

        if theme.reduced_motion():
            self.setCurrentIndex(index)
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

        def _on_finished():
            self._is_animating = False
            self.setCurrentIndex(index)
            current_w.move(QPoint(0, 0))
            next_w.move(QPoint(0, 0))

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
    if theme.reduced_motion():
        return anim
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def status_flash(widget: QWidget, color: str = "#0f7b0f", duration: int = 1500):
    """状态栏颜色闪烁：短暂变色后恢复。"""
    original = widget.styleSheet()
    widget.setStyleSheet(
        f"QStatusBar {{ background-color: {color}; color: #ffffff; "
        f"border-top: 1px solid {color}; font-size: 12px; padding: 3px 10px; }}"
    )
    QTimer.singleShot(duration, lambda: widget.setStyleSheet(original))
