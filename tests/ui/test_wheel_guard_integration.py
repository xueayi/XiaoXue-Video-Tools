# -*- coding: utf-8 -*-
"""集成守护: 应用内所有下拉框都必须是防误滚控件 (WheelGuardComboBox)。

背景: 用户反馈「滚动页面时鼠标经过下拉框会误改选项」。#3 修复后,
base_tab.add_combo 与 output_plan_card 都改用 WheelGuardComboBox;
本用例遍历真实 MainWindow 的全部 QComboBox, 防止后续新增页面时漏用。
"""

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox

from src.ui.main_window import MainWindow
from src.ui.widgets import (
    WheelGuardComboBox, WheelGuardDoubleSpinBox, WheelGuardSpinBox,
)


@pytest.fixture
def win(qapp):
    window = MainWindow()
    yield window
    window.close()


def _wheel_event(delta=-120):
    return QWheelEvent(
        QPointF(10, 10), QPointF(10, 10),
        QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


def test_every_combobox_is_wheel_guarded(win):
    """全应用不存在裸 QComboBox。"""
    combos = win.findChildren(QComboBox)
    assert combos, "主窗口应包含下拉框"
    plain = [type(c).__name__ for c in combos
             if not isinstance(c, WheelGuardComboBox)]
    assert not plain, f"发现未受保护的 QComboBox: {plain}"


def test_wheel_over_any_combobox_never_changes_selection(win, qapp):
    """对每个下拉框: 未展开时滚轮不改值 (聚焦与否都不改)。"""
    combos = win.findChildren(QComboBox)
    assert combos
    for combo in combos:
        if not combo.isEnabled() or combo.count() < 2:
            continue
        combo.setCurrentIndex(0)
        combo.setFocus()
        qapp.processEvents()
        combo.wheelEvent(_wheel_event())
        assert combo.currentIndex() == 0, (
            f"{combo.objectName() or type(combo).__name__} 被滚轮改值")


def test_every_spinbox_is_wheel_guarded(win):
    """全应用不存在裸 QSpinBox / QDoubleSpinBox。"""
    spins = win.findChildren(QSpinBox) + win.findChildren(QDoubleSpinBox)
    assert spins, "主窗口应包含数值微调框"
    plain = []
    for spin in spins:
        if isinstance(spin, WheelGuardSpinBox):
            continue
        if isinstance(spin, WheelGuardDoubleSpinBox):
            continue
        plain.append(type(spin).__name__)
    assert not plain, f"发现未受保护的微调框: {plain}"


def test_wheel_over_any_spinbox_never_changes_value(win, qapp):
    """对每个微调框: 滚轮不改数值。"""
    spins = win.findChildren(QSpinBox) + win.findChildren(QDoubleSpinBox)
    assert spins
    for spin in spins:
        if not spin.isEnabled():
            continue
        original = spin.value()
        spin.setFocus()
        qapp.processEvents()
        spin.wheelEvent(_wheel_event())
        assert spin.value() == original, (
            f"{spin.objectName() or type(spin).__name__} 被滚轮改值")
