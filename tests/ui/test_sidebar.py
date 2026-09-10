# -*- coding: utf-8 -*-
"""sidebar.py 测试: 分组/页面索引映射、药丸指示器、主题联动。"""

import pytest
from PyQt6.QtCore import Qt

from src._version import __version__
from src.ui import theme
from src.ui.sidebar import Sidebar


@pytest.fixture
def sidebar(qapp):
    s = Sidebar()
    for section in ("分组A", "分组B"):
        s.add_section(section)
        s.add_item(f"{section}-1", "ri.film-line")
        s.add_item(f"{section}-2", "ri.music-2-line")
    return s


def test_brand_header(sidebar):
    assert sidebar._title_label.text() == "小雪工具箱"
    assert sidebar._version_label.text() == f"v{__version__}"


def test_sections_not_selectable(sidebar):
    from PyQt6.QtCore import Qt
    item = sidebar._list.item(0)
    assert not (item.flags() & Qt.ItemFlag.ItemIsSelectable)
    assert not (item.flags() & Qt.ItemFlag.ItemIsEnabled)


def test_page_index_skips_sections(sidebar, qapp):
    assert not (sidebar._list.item(0).flags() & Qt.ItemFlag.ItemIsSelectable)
    assert sidebar.count() == 4
    assert sidebar.item_text(0) == "分组A-1"
    assert sidebar.item_text(2) == "分组B-1"


def test_current_row_default(sidebar):
    assert sidebar.currentRow() == -1


def test_set_current_row_and_signal(sidebar, qapp):
    got = []
    sidebar.tab_changed.connect(got.append)
    sidebar.setCurrentRow(2)  # 页面索引 2 -> 行 3 (跳过分组B)
    assert sidebar.currentRow() == 2
    assert got and got[-1] == 2


def test_theme_icons_switch(sidebar, qapp):
    sidebar.setCurrentRow(0)
    theme.set_theme("dark")
    sidebar.set_theme_icons()
    assert sidebar._theme_btn.text() == "切换浅色模式"
    theme.set_theme("light")
    sidebar.set_theme_icons()
    assert sidebar._theme_btn.text() == "切换深色模式"
    assert sidebar._logo_label.pixmap() is not None


def test_set_enabled_disables_children(sidebar):
    sidebar.setEnabled(False)
    assert not sidebar._list.isEnabled()
    assert not sidebar._theme_btn.isEnabled()
    sidebar.setEnabled(True)
    assert sidebar._list.isEnabled()


def test_pill_indicator_visible_after_selection(sidebar, qapp):
    sidebar.resize(sidebar.size())
    sidebar.setCurrentRow(1)
    sidebar._list.repaint()
    assert not sidebar._pill.isHidden()


def test_move_pill_invalid_row_hides(sidebar, qapp):
    sidebar.setCurrentRow(0)
    sidebar._move_pill(-1)
    assert sidebar._pill.isHidden()


def test_apply_row_icon_skips_sections(sidebar, qapp):
    sidebar._apply_row_icon(0)  # 分组行 (icon_names 为 None)
    assert sidebar._list.item(0).text() == "分组A"


def test_resize_event_moves_pill(sidebar, qapp):
    sidebar.setCurrentRow(0)
    sidebar.resize(220, 400)
    assert not sidebar._pill.isHidden()


def test_theme_button_click_no_crash(sidebar, qapp):
    sidebar.theme_button().click()
