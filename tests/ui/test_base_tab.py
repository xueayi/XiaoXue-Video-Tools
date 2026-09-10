# -*- coding: utf-8 -*-
"""base_tab.py 测试: 表单助手、拖放反馈、状态标签、折叠面板、文件对话框。"""

import pytest
from PyQt6.QtCore import QPointF, QPoint, QMimeData, QUrl, Qt
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PyQt6.QtWidgets import QFileDialog

from src.ui.base_tab import (
    BaseTab, FileDropLineEdit, CONTENT_MAX_WIDTH, ACTION_BTN_WIDTH, SPIN_WIDTH,
    repolish, set_label_kind, _set_drag_over,
)


class DummyTab(BaseTab):
    def build_args(self):
        return None


@pytest.fixture
def tab(qapp):
    t = DummyTab("测试")
    t.resize(CONTENT_MAX_WIDTH + 100, 600)
    return t


def _drag_event(cls, path="C:/video/a.mp4"):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    pos = QPointF(1, 1) if cls is QDropEvent else QPoint(1, 1)
    ev = cls(
        pos,
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # C++ 事件只持有裸指针, 把 mime 挂在事件上防止 Python 侧提前回收
    ev._mime = mime
    return ev


# ----------------------------------------------------------------
# FileDropLineEdit
# ----------------------------------------------------------------

def test_drop_single_path(qapp):
    edit = FileDropLineEdit()
    edit.dropEvent(_drag_event(QDropEvent))
    assert edit.text() == "C:/video/a.mp4"


def test_drop_multi_paths(qapp):
    edit = FileDropLineEdit(multi=True)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(f"C:/x/{i}.mp4") for i in range(5)])
    ev = QDropEvent(
        QPointF(1, 1), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    ev._mime = mime  # 防 GC
    edit.dropEvent(ev)
    assert edit.text() == "已选择 5 个文件"
    assert len(edit._paths) == 5


def test_drop_empty_urls_noop(qapp):
    edit = FileDropLineEdit()
    mime = QMimeData()
    ev = QDropEvent(
        QPointF(1, 1), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    ev._mime = mime
    edit.dropEvent(ev)
    assert edit.text() == ""


def test_drag_enter_and_leave_highlight(qapp):
    edit = FileDropLineEdit()
    ev = _drag_event(QDragEnterEvent)
    edit.dragEnterEvent(ev)
    assert ev.isAccepted()
    assert edit.property("dragOver") is True
    edit.dragLeaveEvent(QDragLeaveEvent())
    assert edit.property("dragOver") is False


def test_drag_enter_non_url_falls_back(qapp):
    edit = FileDropLineEdit()
    mime = QMimeData()
    mime.setText("hello")
    ev = QDragEnterEvent(
        QPoint(1, 1), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    ev._mime = mime
    edit.dragEnterEvent(ev)
    assert edit.property("dragOver") is None


def test_set_drag_over_dedupes(qapp):
    edit = FileDropLineEdit()
    _set_drag_over(edit, True)
    _set_drag_over(edit, True)
    assert edit.property("dragOver") is True


# ----------------------------------------------------------------
# 状态标签
# ----------------------------------------------------------------

@pytest.mark.parametrize("kind, obj, italic", [
    ("muted", "muted_label", True),
    ("error", "error_label", False),
    ("strong", "strong_label", False),
])
def test_set_label_kind(qapp, kind, obj, italic):
    from PyQt6.QtWidgets import QLabel
    label = QLabel()
    set_label_kind(label, kind)
    assert label.objectName() == obj
    assert label.property("italic") is italic


def test_set_label_kind_unknown_falls_to_muted(qapp):
    from PyQt6.QtWidgets import QLabel
    label = QLabel()
    set_label_kind(label, "weird")
    assert label.objectName() == "muted_label"


def test_repolish(qapp, tab):
    repolish(tab)
    assert tab.objectName() == ""


# ----------------------------------------------------------------
# 表单助手
# ----------------------------------------------------------------

def test_add_group_and_description(tab):
    from PyQt6.QtWidgets import QLabel
    io = tab.add_group("输入/输出", "这是一段描述")
    tab.add_file_chooser(io, "输入视频")
    labels = [lb for lb in tab.widget().findChildren(QLabel)
              if lb.objectName() == "group_desc"]
    assert any("这是一段描述" in lb.text() for lb in labels)


def test_add_file_chooser_browse(tab, monkeypatch):
    io = tab.add_group("g")
    edit = tab.add_file_chooser(io, "输入", "所有文件 (*.*)", "提示")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: ("C:/ chosen.mp4", "")))
    from PyQt6.QtWidgets import QPushButton
    btns = [b for b in io.parentWidget().findChildren(QPushButton)
            if b.text() == "浏览"]
    assert btns and btns[0].minimumWidth() == ACTION_BTN_WIDTH
    btns[-1].click()
    assert edit.text() == "C:/ chosen.mp4"


def test_add_file_saver_browse(tab, monkeypatch):
    io = tab.add_group("g")
    edit = tab.add_file_saver(io, "输出")
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: ("C:/ out.mp4", "")))
    from PyQt6.QtWidgets import QPushButton
    for b in io.parentWidget().findChildren(QPushButton):
        if b.text() == "浏览":
            b.click()
    assert edit.text() == "C:/ out.mp4"


def test_add_dir_chooser_browse(tab, monkeypatch):
    io = tab.add_group("g")
    edit = tab.add_dir_chooser(io, "目录")
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: "C:/outdir"))
    from PyQt6.QtWidgets import QPushButton
    for b in io.parentWidget().findChildren(QPushButton):
        if b.text() == "浏览":
            b.click()
    assert edit.text() == "C:/outdir"


def test_add_multi_file_chooser_browse(tab, monkeypatch):
    io = tab.add_group("g")
    edit = tab.add_multi_file_chooser(io, "多选")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames",
        staticmethod(lambda *a, **k: (["C:/1.mp4", "C:/2.mp4"], "")))
    from PyQt6.QtWidgets import QPushButton
    for b in io.parentWidget().findChildren(QPushButton):
        if b.text() == "浏览":
            b.click()
    assert edit.text() == "C:/1.mp4; C:/2.mp4"


def test_add_basic_controls(tab):
    io = tab.add_group("g")
    combo_default = tab.add_combo(io, "c1", ["a", "b"], "b")
    assert combo_default.currentText() == "b"
    combo_nodef = tab.add_combo(io, "c2", ["a", "b"], "zz")
    assert combo_nodef.currentText() == "a"
    cb = tab.add_checkbox(io, "cb", True, "tip")
    assert cb.isChecked()
    spin = tab.add_spinbox(io, "n", 0, 10, 3)
    assert spin.value() == 3 and spin.minimumWidth() == SPIN_WIDTH
    text = tab.add_text_input(io, "t", "hi", "tip")
    assert text.text() == "hi"
    area = tab.add_text_area(io, "ta", "body", 80, "tip")
    assert area.toPlainText() == "body" and area.maximumHeight() == 80


def test_add_hint_types(tab):
    io = tab.add_group("g")
    info = tab.add_hint(io, "i", "info")
    warn = tab.add_hint(io, "w", "warning")
    tip = tab.add_hint(io, "t", "tip")
    odd = tab.add_hint(io, "o", "mystery")
    assert info.objectName() == "hint_info"
    assert warn.objectName() == "hint_warning"
    assert tip.objectName() == "hint_tip"
    assert odd.objectName() == "hint_info"


def test_add_link(tab):
    from PyQt6.QtWidgets import QLabel
    io = tab.add_group("g")
    tab.add_link(io, "https://example.com", "点我")
    links = [lb for lb in io.parentWidget().findChildren(QLabel)
             if lb.text().startswith("<a href")]
    assert links and "点我" in links[0].text()


def test_add_collapsible_group(tab):
    lay = tab.add_collapsible_group("高级", "说明", expanded=True)
    tab.add_text_input(lay, "字段", "")
    assert tab._main_layout.count() >= 2
    from PyQt6.QtWidgets import QToolButton, QWidget
    header = tab._main_layout.itemAt(tab._main_layout.count() - 2).widget()
    content = tab._main_layout.itemAt(tab._main_layout.count() - 1).widget()
    assert isinstance(header, QToolButton) and header.isChecked()
    assert isinstance(content, QWidget) and content.isVisibleTo(tab)
    header.setChecked(False)
    assert "▸" in header.text()
    header.setChecked(True)
    assert "▾" in header.text() and content.isVisibleTo(tab)


def test_get_multi_paths(tab):
    io = tab.add_group("g")
    edit = tab.add_multi_file_chooser(io, "多选")
    edit._paths = ["C:/a", "C:/b"]
    assert tab.get_multi_paths(edit) == ["C:/a", "C:/b"]
    edit._paths = []
    edit.setText("C:/x; C:/y")
    assert tab.get_multi_paths(edit) == ["C:/x", "C:/y"]
    edit.setText("已选择 5 个文件")
    assert tab.get_multi_paths(edit) == []
    edit.setText("")
    assert tab.get_multi_paths(edit) == []


def test_base_build_args_raises(tab):
    with pytest.raises(NotImplementedError):
        BaseTab.build_args(tab)


def test_on_theme_changed_noop(tab):
    tab.on_theme_changed()


def test_content_max_width_constant():
    assert CONTENT_MAX_WIDTH == 860
