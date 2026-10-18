# -*- coding: utf-8 -*-
"""内封字幕流选项可用性: 仅 MKV / MOV 输出可选, MP4 等格式禁用并强制不保留。"""

import pytest
from PyQt6.QtWidgets import QCheckBox, QLabel

from src.capabilities.container import (
    EMBEDDED_SUBTITLE_FORMATS,
    embedded_subtitle_note,
    supports_embedded_subtitles,
)
from src.ui.tabs.encode_tab import EncodeTab


@pytest.fixture
def tab(qapp):
    widget = EncodeTab()
    yield widget
    widget.deleteLater()


def _note_label(tab):
    for label in tab.findChildren(QLabel):
        if label.objectName().startswith("hint_") and "支持保留内封字幕流" in label.text():
            return label
    return None


# ----------------------------------------------------------------
# 纯函数
# ----------------------------------------------------------------

@pytest.mark.parametrize("extension, expected", [
    (".mkv", True), (".MKV", True), ("mkv", True),
    (".mov", True),
    (".mp4", False), (".ts", False), (".webm", False), (".m4a", False),
    ("", False), (None, False),
])
def test_supports_embedded_subtitles(extension, expected):
    assert supports_embedded_subtitles(extension) is expected


def test_embedded_subtitle_note_mentions_supported_formats():
    note = embedded_subtitle_note()
    for extension in EMBEDDED_SUBTITLE_FORMATS:
        assert extension.upper() in note
    assert "不可用" in note


# ----------------------------------------------------------------
# 界面联动
# ----------------------------------------------------------------

def test_label_and_hint_text(tab):
    assert EMBEDDED_SUBTITLE_FORMATS == ("mkv", "mov")
    labels = [label.text() for label in tab.findChildren(QLabel)]
    assert "保留字幕流" in labels
    hint = _note_label(tab)
    assert hint is not None
    # 旧的长篇说明已移除
    assert "两个概念别混" not in hint.text()
    assert "MKV" in hint.text() and "MOV" in hint.text()


def test_mp4_output_disables_combo_by_default(tab):
    assert tab.output_format_combo.currentText() == "MP4"
    assert not tab.subtitle_tracks_combo.isEnabled()
    assert tab.subtitle_tracks_combo.currentText() == "不保留字幕"
    assert "不支持内封字幕流" in tab.subtitle_tracks_combo.toolTip()


def test_mkv_output_enables_combo(tab):
    tab.output_format_combo.setCurrentText("MKV")
    assert tab.subtitle_tracks_combo.isEnabled()
    assert tab.subtitle_tracks_combo.currentText() == "不保留字幕"
    assert tab.subtitle_tracks_combo.toolTip() == tab._subtitle_default_tooltip

    tab.subtitle_tracks_combo.setCurrentText("全部保留")
    assert tab.build_args().subtitle_tracks == "全部保留"


def test_switching_back_to_mp4_resets_selection(tab):
    tab.output_format_combo.setCurrentText("MKV")
    tab.subtitle_tracks_combo.setCurrentText("全部保留")
    tab.output_format_combo.setCurrentText("MP4")
    assert not tab.subtitle_tracks_combo.isEnabled()
    assert tab.subtitle_tracks_combo.currentText() == "不保留字幕"
    assert tab.build_args().subtitle_tracks == "不保留字幕"


def test_custom_extension_follows_support(tab):
    tab.output_format_combo.setCurrentText("自定义")
    tab.output_format_custom_edit.setText(".mkv")
    assert tab.subtitle_tracks_combo.isEnabled()

    tab.output_format_custom_edit.setText(".mp4")
    assert not tab.subtitle_tracks_combo.isEnabled()
    assert tab.subtitle_tracks_combo.currentText() == "不保留字幕"


def test_same_as_input_uses_input_extension(tab):
    tab.output_format_combo.setCurrentText("与输入相同")
    assert not tab.subtitle_tracks_combo.isEnabled()  # 无输入 → 未知 → 不可用

    tab.input_edit.setText(r"D:\media\clip.mkv")
    assert tab.subtitle_tracks_combo.isEnabled()

    tab.input_edit.setText(r"D:\media\clip.mp4")
    assert not tab.subtitle_tracks_combo.isEnabled()


def test_build_args_forces_none_even_if_set_programmatically(tab):
    # 直接改文本绕过禁用状态, build_args 也不能把字幕带进 MP4
    tab.subtitle_tracks_combo.setCurrentText("全部保留")
    args = tab.build_args()
    assert args.output_format == "MP4"
    assert args.subtitle_tracks == "不保留字幕"
    assert args.subtitle_tracks_custom == ""


def test_detected_track_panel_subtitle_checks_disabled_for_mp4(tab):
    checkbox = QCheckBox("sub")
    tab._sub_checks.append((checkbox, 0))
    tab._sync_subtitle_stream_availability()
    assert not checkbox.isEnabled()
    assert checkbox.isChecked() is False
    assert tab.build_args().subtitle_tracks == "不保留字幕"

    tab.output_format_combo.setCurrentText("MKV")
    assert checkbox.isEnabled()
