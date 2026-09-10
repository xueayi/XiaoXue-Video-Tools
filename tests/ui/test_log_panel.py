# -*- coding: utf-8 -*-
"""log_panel.py 测试: ANSI 渲染、过滤、工具条、复制、缩放。"""

from PyQt6.QtCore import QPointF, QPoint, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QLineEdit, QPushButton

from src.ui.log_panel import LogPanel, _ansi_to_html, _LogView


def test_ansi_to_html_plain():
    assert _ansi_to_html("hello\nworld") == "hello<br/>world"


def test_ansi_to_html_escape():
    assert "&lt;b&gt;" in _ansi_to_html("<b>")


def test_ansi_to_html_colors_and_bold():
    out = _ansi_to_html("\033[1;31merr\033[0m done")
    assert "font-weight:bold" in out
    assert "#f44747" in out
    assert "err" in out
    assert out.count("<span") == out.count("</span>")


def test_ansi_bold_then_color_replaces_span():
    out = _ansi_to_html("\033[1mbold\033[32mgreen")
    assert "bold" in out and "green" in out


def test_log_panel_append_and_placeholder(qapp):
    panel = LogPanel()
    assert "任务日志" in panel._view.placeholderText()
    panel.append_log("hello")
    assert "hello" in panel._view.toPlainText()


def test_log_panel_clear(qapp):
    panel = LogPanel()
    panel.append_log("hello")
    panel.clear_log()
    assert panel._view.toPlainText() == ""
    assert panel._chunks == []


def test_log_panel_filter(qapp):
    panel = LogPanel()
    panel.append_log("apple pie\n")
    panel.append_log("banana split\n")
    panel._filter_edit.setText("apple")
    text = panel._view.toPlainText()
    assert "apple" in text and "banana" not in text
    panel._filter_edit.setText("  ")
    assert "banana" in panel._view.toPlainText()
    panel._filter_edit.setText("")
    assert "banana" in panel._view.toPlainText()


def test_log_panel_filter_mixed_case(qapp):
    panel = LogPanel()
    panel.append_log("ENCODER DONE\n")
    panel.append_log("other\n")
    panel._filter_edit.setText("encoder")
    assert "DONE" in panel._view.toPlainText()
    assert "other" not in panel._view.toPlainText()


def test_log_panel_copy(qapp):
    panel = LogPanel()
    panel.append_log("copy me")
    panel._copy_all()
    from PyQt6.QtWidgets import QApplication
    clip = QApplication.clipboard()
    assert clip.text() == "copy me"


def test_log_panel_wrap_toggle(qapp):
    from PyQt6.QtGui import QTextOption
    panel = LogPanel()
    panel._wrap_btn.setChecked(False)
    assert panel._view.wordWrapMode() == QTextOption.WrapMode.NoWrap
    panel._wrap_btn.setChecked(True)
    assert panel._view.wordWrapMode() == QTextOption.WrapMode.WordWrap


def test_log_panel_tool_buttons_registry(qapp):
    panel = LogPanel()
    btns = panel._view.parent().findChildren(QPushButton)
    iconed = [b for b in btns if b in panel._tool_icon_names]
    assert len(iconed) == 4
    assert all(b.objectName() == "icon_btn" for b in iconed)


def test_log_panel_autoscroll_toggle(qapp):
    panel = LogPanel()
    panel.append_log("\n".join(f"line {i}" for i in range(500)) + "\n")
    bar = panel._view.verticalScrollBar()
    bar.setValue(0)
    panel._autoscroll_btn.setChecked(False)
    panel.append_log("more\n")
    assert bar.value() == 0 or bar.value() < bar.maximum()
    panel._autoscroll_btn.setChecked(True)
    panel._scroll_to_bottom()
    assert bar.value() == bar.maximum()


def test_log_panel_smooth_scroll(qapp, pump_fn):
    panel = LogPanel()
    panel.append_log("\n".join(f"line {i}" for i in range(800)) + "\n")
    pump_fn(300)
    bar = panel._view.verticalScrollBar()
    assert bar.value() == bar.maximum()


def test_log_view_ctrl_wheel_zoom(qapp):
    view = _LogView()
    before = view.font().pointSize()
    ev = QWheelEvent(
        QPointF(0, 0), QPointF(0, 0), QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    view.wheelEvent(ev)
    assert view.font().pointSize() > before
    ev2 = QWheelEvent(
        QPointF(0, 0), QPointF(0, 0), QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    view.wheelEvent(ev2)
    assert view.font().pointSize() == before


def test_log_view_plain_wheel_ignored(qapp):
    view = _LogView()
    before = view.font().pointSize()
    ev = QWheelEvent(
        QPointF(0, 0), QPointF(0, 0), QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    view.wheelEvent(ev)
    assert view.font().pointSize() == before


def test_log_panel_on_theme_changed(qapp):
    panel = LogPanel()
    panel.on_theme_changed()
    assert panel._tool_icon_names
