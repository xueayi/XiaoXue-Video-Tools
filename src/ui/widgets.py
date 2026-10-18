# -*- coding: utf-8 -*-
"""通用小控件 —— 目前包含带抗误滚轮与自绘箭头的下拉框。

背景: 原生 QComboBox 在页面里滚动时, 鼠标滚轮经过下拉框会误改选项;
且 QSS 用 border 三角绘制 ``::down-arrow`` 在部分平台/缩放比下会显示成
矩形。因此在本模块统一自绘:

- **下拉列表未展开时滚轮一律不改选项**, 并把滚轮事件转发给外层滚动区域,
  保证页面仍能正常滚动 (列表展开时才允许滚轮滚动列表本身);
- ``paintEvent`` 用 QStylePainter 画下拉框本体与文本, 再用 QPolygonF
  画一个小三角, 下拉展开时旋转 180° (监听弹出列表的 Show/Hide 事件);
- 三角颜色取 palette 的文本色 (禁用态自动用 palette 的 disabled 组)。
"""

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QPainter, QPalette, QPolygonF
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QSpinBox,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
)


def make_form_layout(parent=None) -> QFormLayout:
    """创建全平台排版一致的表单布局。

    背景: ``QFormLayout`` 的字段增长策略默认值随样式而变 —— QMacStyle 是
    ``FieldsStayAtSizeHint``, 字段按 sizeHint 定宽、剩余空间两侧均分, 于是
    macOS 上整块表单看起来「被居中了」, 与 Windows 的撑满宽度不一致。
    这里显式统一为 ``AllNonFixedFieldsGrow`` 并固定标签/行策略。

    Args:
        parent: 传给 QFormLayout 的父对象 (可为 None, 之后由 addLayout 接管)。
    """
    form = QFormLayout(parent)
    form.setFieldGrowthPolicy(
        QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setFormAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    form.setLabelAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
    form.setHorizontalSpacing(14)
    form.setVerticalSpacing(10)
    return form


class _WheelForwardMixin:
    """把滚轮事件转交给外层滚动区域, 自身不改值。"""

    def _forward_to_scroll_area(self, event) -> bool:
        """转交给最近的外层 QAbstractScrollArea（存在则返回 True）。"""
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                QApplication.sendEvent(parent.viewport(), event)
                return True
            parent = parent.parentWidget()
        return False


class WheelGuardComboBox(_WheelForwardMixin, QComboBox):
    """滚轮永不误改选项、且自绘三角形箭头的下拉框。

    - ``WheelGuardComboBox(...)`` 用法与 QComboBox 一致;
    - 下拉列表**未展开**时: 滚轮事件改投外层滚动区域 (页面正常滚动),
      当前选项保持不变 (无论控件是否有焦点);
    - 下拉列表**已展开**时: 滚轮交给基类, 用于滚动选项列表;
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

    def popup_visible(self) -> bool:
        """下拉列表当前是否展开。"""
        view = self.view()
        return bool(self._arrow_open or (view is not None and view.isVisible()))

    def wheelEvent(self, event):
        """未展开下拉时滚轮不改选项, 而是转交给外层滚动区域。"""
        if self.popup_visible():
            super().wheelEvent(event)
            return
        self._forward_to_scroll_area(event)
        # 不在滚动区域内时也直接吞掉, 避免落到基类改值
        event.accept()

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


class WheelGuardSpinBox(_WheelForwardMixin, QSpinBox):
    """滚轮不误改数值的整数微调框 (滚动页面时数值保持不变)。"""

    def wheelEvent(self, event):
        self._forward_to_scroll_area(event)
        event.accept()


class WheelGuardDoubleSpinBox(_WheelForwardMixin, QDoubleSpinBox):
    """滚轮不误改数值的浮点微调框。"""

    def wheelEvent(self, event):
        self._forward_to_scroll_area(event)
        event.accept()
