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


def test_wheel_ignored_when_not_focused(combo, monkeypatch):
    monkeypatch.setattr(combo, "hasFocus", lambda: False)
    event = _wheel_event()
    combo.wheelEvent(event)
    assert event.isAccepted() is False
    assert combo.currentIndex() == 0  # 未改值


def test_wheel_changes_value_when_focused(combo, monkeypatch):
    monkeypatch.setattr(combo, "hasFocus", lambda: True)
    event = _wheel_event(-120)
    combo.wheelEvent(event)
    assert event.isAccepted() is True
    assert combo.currentIndex() == 1  # 向下滚动一格


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


def test_paint_smoke(combo, qapp):
    combo.show()
    qapp.processEvents()
    pixmap = combo.grab()
    assert not pixmap.isNull()
    combo.hide()
