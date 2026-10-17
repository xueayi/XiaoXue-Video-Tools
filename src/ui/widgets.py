# -*- coding: utf-8 -*-
"""通用小控件 —— 目前包含带抗误滚轮与自绘箭头的下拉框。

背景: 原生 QComboBox 在页面里滚动时, 鼠标滚轮经过下拉框会误改选项;
且 QSS 用 border 三角绘制 ``::down-arrow`` 在部分平台/缩放比下会显示成
矩形。因此在本模块统一自绘:

- 未聚焦时忽略滚轮事件, 让页面滚动正常进行; 聚焦后才允许改值;
- ``paintEvent`` 用 QStylePainter 画下拉框本体与文本, 再用 QPolygonF
  画一个小三角, 下拉展开时旋转 180° (监听弹出列表的 Show/Hide 事件);
- 三角颜色取 palette 的文本色 (禁用态自动用 palette 的 disabled 组)。
"""

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QPainter, QPalette, QPolygonF
from PyQt6.QtWidgets import (
    QComboBox,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
)


class WheelGuardComboBox(QComboBox):
    """未聚焦时不响应滚轮、且自绘三角形箭头的下拉框。

    - ``WheelGuardComboBox(...)`` 用法与 QComboBox 一致;
    - 滚轮只在 ``hasFocus()`` 为真时改值, 否则 ``event.ignore()`` 让事件
      冒泡给外层滚动区域;
    - 箭头是抗锯齿小三角, 展开时旋转 180°, 颜色随 palette (禁用态 muted)。
    """

    #: 三角宽度/高度 (px)
    ARROW_WIDTH = 9
    ARROW_HEIGHT = 5
    #: 三角中心距控件右边缘的距离 (px), 与 QSS 的 drop-down 区域对齐
    ARROW_RIGHT_OFFSET = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._arrow_open = False
        view = self.view()
        if view is not None:
            # 弹出列表的 Show/Hide 即下拉展开/收起
            view.installEventFilter(self)

    # ----------------------------------------------------------------
    # 滚轮守卫
    # ----------------------------------------------------------------

    def wheelEvent(self, event):
        """未聚焦时忽略滚轮, 让事件冒泡给页面滚动区域。"""
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)

    # ----------------------------------------------------------------
    # 箭头展开态
    # ----------------------------------------------------------------

    def is_arrow_open(self) -> bool:
        """下拉当前是否展开 (展开时箭头旋转 180°)。"""
        return self._arrow_open

    def eventFilter(self, obj, event):
        if obj is self.view() and event.type() in (
                QEvent.Type.Show, QEvent.Type.Hide):
            self._arrow_open = event.type() == QEvent.Type.Show
            self.update()
        return super().eventFilter(obj, event)

    def arrow_polygon(self) -> QPolygonF:
        """当前箭头三角形 (控件坐标); 展开时以三角形中心旋转 180°。"""
        rect = self.rect()
        center_x = rect.right() - self.ARROW_RIGHT_OFFSET + 1
        center_y = rect.center().y() + 0.5
        half_w = self.ARROW_WIDTH / 2.0
        half_h = self.ARROW_HEIGHT / 2.0
        points = [
            QPointF(center_x - half_w, center_y - half_h),
            QPointF(center_x + half_w, center_y - half_h),
            QPointF(center_x, center_y + half_h),
        ]
        if self._arrow_open:
            points = [
                QPointF(2 * center_x - point.x(), 2 * center_y - point.y())
                for point in points
            ]
        return QPolygonF(points)

    def _arrow_color(self):
        """三角颜色: 正常态取 palette 文本色, 禁用态取 disabled 文本色。"""
        palette = self.palette()
        group = (QPalette.ColorGroup.Normal if self.isEnabled()
                 else QPalette.ColorGroup.Disabled)
        return palette.color(group, QPalette.ColorRole.Text)

    # ----------------------------------------------------------------
    # 绘制
    # ----------------------------------------------------------------

    def paintEvent(self, event):
        """画下拉框本体 + 文本, 再画自绘三角形箭头。"""
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._arrow_color())
        painter.drawPolygon(self.arrow_polygon())
        painter.end()
