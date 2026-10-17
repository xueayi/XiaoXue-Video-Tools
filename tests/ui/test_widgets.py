# -*- coding: utf-8 -*-
"""widgets.py 测试: 抗误滚轮下拉框 + 自绘三角箭头 (展开旋转 180°)。"""

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QComboBox

from src.ui import theme
from src.ui.widgets import WheelGuardComboBox


@pytest.fixture
def combo(qapp):
    widget = WheelGuardComboBox()
    widget.addItems(["A", "B", "C"])
    widget.resize(200, 32)
    yield widget
    widget.deleteLater()


def _wheel_event(delta=120):
    return QWheelEvent(
        QPointF(10, 10), QPointF(10, 10),
        QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


def test_combo_is_a_combobox_with_strong_focus(combo):
    assert isinstance(combo, QComboBox)
    assert combo.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_wheel_never_changes_value_when_popup_closed(combo, monkeypatch):
    """下拉未展开时, 无论有无焦点, 滚轮都不改选项。"""
    for focused in (False, True):
        monkeypatch.setattr(combo, "hasFocus", lambda value=focused: value)
        combo.setCurrentIndex(0)
        event = _wheel_event(-120)
        combo.wheelEvent(event)
        assert combo.currentIndex() == 0
    assert combo.popup_visible() is False


def test_wheel_allowed_only_when_popup_open(combo, qapp):
    """下拉展开时, 滚轮交给基类用于滚动选项列表。"""
    qapp.sendEvent(combo.view(), QEvent(QEvent.Type.Show))
    assert combo.popup_visible() is True
    combo.setCurrentIndex(0)
    event = _wheel_event(-120)
    combo.wheelEvent(event)
    assert combo.currentIndex() == 1

    qapp.sendEvent(combo.view(), QEvent(QEvent.Type.Hide))
    assert combo.popup_visible() is False
    combo.setCurrentIndex(0)
    combo.wheelEvent(_wheel_event(-120))
    assert combo.currentIndex() == 0


def test_wheel_forwards_to_enclosing_scroll_area(qapp):
    """下拉未展开时, 滚轮应滚动外层页面而不是改选项。"""
    from PyQt6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

    area = QScrollArea()
    content = QWidget()
    layout = QVBoxLayout(content)
    inner = WheelGuardComboBox()
    inner.addItems(["A", "B", "C"])
    layout.addWidget(inner)
    for index in range(30):
        layout.addWidget(QLabel(f"row {index}"))
    area.setWidget(content)
    area.resize(300, 200)
    area.show()
    qapp.processEvents()

    bar = area.verticalScrollBar()
    assert bar.maximum() > 0, "滚动区域内容应可滚动"
    bar.setValue(0)
    inner.setCurrentIndex(0)

    qapp.sendEvent(inner, _wheel_event(-120))
    assert inner.currentIndex() == 0, "滚轮不得改变选项"
    assert bar.value() > 0, "滚轮应滚动外层页面"

    area.hide()
    area.deleteLater()


def test_arrow_rotates_when_popup_opens(combo, qapp):
    closed = combo.arrow_polygon()
    assert closed.count() == 3
    # 收起: 三角尖端朝下
    assert closed.at(2).y() > closed.at(0).y()
    assert combo.is_arrow_open() is False

    qapp.sendEvent(combo.view(), QEvent(QEvent.Type.Show))
    assert combo.is_arrow_open() is True
    opened = combo.arrow_polygon()
    # 展开: 旋转 180°, 尖端朝上
    assert opened.at(2).y() < opened.at(0).y()

    qapp.sendEvent(combo.view(), QEvent(QEvent.Type.Hide))
    assert combo.is_arrow_open() is False


def test_arrow_color_follows_palette_and_disabled_state(combo, qapp):
    from PyQt6.QtWidgets import QApplication

    theme.apply_theme(QApplication.instance(), "light")

    combo.setEnabled(True)
    normal = combo._arrow_color()
    combo.setEnabled(False)
    disabled = combo._arrow_color()
    theme.apply_theme(QApplication.instance(), "light")

    assert normal.isValid() and disabled.isValid()
    assert normal.name() != disabled.name()


def test_arrow_polygon_stays_inside_combo(combo):
    rect = combo.rect()
    for point in combo.arrow_polygon():
        assert rect.left() <= point.x() <= rect.right()
        assert rect.top() <= point.y() <= rect.bottom()
    # 箭头位于控件右侧 drop-down 区域附近
    rightmost = max(point.x() for point in combo.arrow_polygon())
    assert rightmost > rect.width() * 0.7


def test_arrow_open_flag_resets_after_hide(combo, qapp):
    qapp.sendEvent(combo.view(), QEvent(QEvent.Type.Show))
    assert combo.is_arrow_open() is True
    qapp.sendEvent(combo.view(), QEvent(QEvent.Type.Hide))
    assert combo.is_arrow_open() is False
    # 收起后箭头恢复朝下
    polygon = combo.arrow_polygon()
    assert polygon.at(2).y() > polygon.at(0).y()


def test_spinbox_wheel_does_not_change_value(qapp):
    """数值微调框: 滚轮在未聚焦时也不改值, 且转交外层滚动区域。"""
    from PyQt6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

    from src.ui.widgets import WheelGuardSpinBox

    area = QScrollArea()
    content = QWidget()
    layout = QVBoxLayout(content)
    spin = WheelGuardSpinBox()
    spin.setRange(0, 100)
    spin.setValue(23)
    layout.addWidget(spin)
    for index in range(30):
        layout.addWidget(QLabel(f"row {index}"))
    area.setWidget(content)
    area.resize(300, 200)
    area.show()
    qapp.processEvents()

    bar = area.verticalScrollBar()
    bar.setValue(0)
    spin.setFocus()
    qapp.processEvents()

    qapp.sendEvent(spin, _wheel_event(-120))
    assert spin.value() == 23, "滚轮不得改变数值"
    assert bar.value() > 0, "滚轮应滚动外层页面"

    area.hide()
    area.deleteLater()


def test_paint_smoke(combo, qapp):
    combo.show()
    qapp.processEvents()
    pixmap = combo.grab()
    assert not pixmap.isNull()
    combo.hide()
