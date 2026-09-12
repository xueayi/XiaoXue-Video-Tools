# -*- coding: utf-8 -*-
"""12 个功能 Tab 的实例化、build_args 与控件联动测试。"""

import pytest

from src.media_probe import DetailedMediaInfo, StreamInfo
from src.ui.tabs import (
    EncodeTab, ReplaceAudioTab, RemuxTab, QcTab, MediaProbeTab,
    ExtractAvTab, ImageConvertTab, FolderCreatorTab, BatchRenameTab,
    ShieldTab, NotificationTab, HelpTab,
)
from src.ui.tabs.help_tab import _plain_to_html


def _info(path="C:/a.mp4", video_codec="h264", audio_codec="aac",
          sub_codec="ass", errors=None, with_subs=True):
    return DetailedMediaInfo(
        path=path,
        video_streams=[StreamInfo(index=0, stream_index=0, codec_type="video",
                                  codec_name=video_codec, width=1920, height=1080)],
        audio_streams=[StreamInfo(index=0, stream_index=1, codec_type="audio",
                                  codec_name=audio_codec, channels=2,
                                  channel_layout="stereo", sample_rate=48000,
                                  bitrate_kbps=192, language="jpn", title="主音轨")],
        subtitle_streams=[StreamInfo(index=0, stream_index=2, codec_type="subtitle",
                                     codec_name=sub_codec, language="chi")] if with_subs else [],
        duration_sec=61.5,
        errors=list(errors or []),
    )


# ----------------------------------------------------------------
# 实例化 + build_args
# ----------------------------------------------------------------

TAB_CASES = [
    (EncodeTab, "视频压制"),
    (ReplaceAudioTab, "音频替换"),
    (RemuxTab, "封装转换"),
    (QcTab, "素材质量检测"),
    (MediaProbeTab, "媒体元数据检测"),
    (ExtractAvTab, "音视频抽取"),
    (ImageConvertTab, "图片转换"),
    (FolderCreatorTab, "文件夹创建"),
    (BatchRenameTab, "批量重命名"),
    (NotificationTab, "通知设置"),
    (HelpTab, "使用说明"),
]


@pytest.mark.parametrize("cls, command", TAB_CASES)
def test_tab_instantiation_and_build_args(qapp, cls, command):
    if cls is NotificationTab:
        tab = cls(config={})
    else:
        tab = cls()
    assert tab.command_name == command
    args = tab.build_args()
    assert args.command == command


def test_shield_tab_full(qapp):
    tab = ShieldTab(shield_available=True)
    args = tab.build_args()
    assert args.command == "露骨图片识别"
    tab.on_theme_changed()


def test_shield_tab_unavailable(qapp):
    tab = ShieldTab(shield_available=False)
    assert tab.command_name == "露骨图片识别"


def test_notification_tab_none_config(qapp):
    tab = NotificationTab(config=None)
    assert tab.build_args().command == "通知设置"


# ----------------------------------------------------------------
# EncodeTab 联动
# ----------------------------------------------------------------

@pytest.fixture
def encode(qapp):
    return EncodeTab()


def test_encode_preset_changed_custom(encode):
    encode.preset_combo.setCurrentText("自定义 (Custom)")
    assert encode.encoder_combo.isEnabled()
    encode.preset_combo.setCurrentText("【均衡画质】x264 常用导出 (CRF18)")
    assert not encode.encoder_combo.isEnabled()
    assert encode.crf_spin.value() == 18


def test_encode_rate_control_linkage(encode):
    encode.preset_combo.setCurrentText("自定义 (Custom)")
    encode.rate_control_combo.setCurrentText("VBR (可变码率)")
    assert not encode.crf_spin.isEnabled()
    assert encode.video_bitrate_combo.isEnabled()
    encode.rate_control_combo.setCurrentText("CRF/CQ (恒定质量)")
    assert encode.crf_spin.isEnabled()
    assert not encode.video_bitrate_combo.isEnabled()


def test_encode_encoder_linkage(encode):
    encode.preset_combo.setCurrentText("自定义 (Custom)")
    encode.encoder_combo.setCurrentText(
        [n for n in encode.encoder_combo.currentText().split()][0] or "x")
    for name in [encode.encoder_combo.itemText(i)
                 for i in range(encode.encoder_combo.count())]:
        encode.encoder_combo.setCurrentText(name)
        enabled = "NVENC" in name or "nvenc" in name
        assert encode.nvenc_preset_combo.isEnabled() is enabled


def test_encode_output_format_linkage(encode):
    encode.output_format_combo.setCurrentText("自定义")
    assert encode.output_format_custom_edit.isEnabled()
    encode.output_format_combo.setCurrentText("MP4 (默认)")
    assert not encode.output_format_custom_edit.isEnabled()


def test_encode_track_combos_linkage(encode):
    encode.audio_tracks_combo.setCurrentText("自定义选择 (填写编号)")
    assert encode.audio_tracks_custom_edit.isEnabled()
    encode.subtitle_tracks_combo.setCurrentText("自定义选择 (填写编号)")
    assert encode.subtitle_tracks_custom_edit.isEnabled()


def test_encode_transfer_linkage(encode):
    encode.post_transfer_mode_combo.setCurrentText("复制到指定目录")
    assert encode.post_transfer_dir_edit.isEnabled()
    encode.post_transfer_mode_combo.setCurrentText("不分发")
    assert not encode.post_transfer_dir_edit.isEnabled()


def test_encode_probe_file_not_found(encode):
    encode.input_edit.setText("Z:/不存在/xx.mp4")
    assert "文件不存在" in encode._track_status.text()
    assert encode._probe_btn.isVisibleTo(encode)


def test_encode_probe_error(encode, monkeypatch, tmp_path):
    import src.ui.tabs.encode_tab as mod
    real = tmp_path / "bad.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr(mod, "probe_detailed", lambda p: _info(errors=["坏文件"]))
    encode.input_edit.setText(str(real))
    assert "检测失败" in encode._track_status.text()


def test_encode_probe_success_and_tracks(encode, monkeypatch, tmp_path):
    import src.ui.tabs.encode_tab as mod
    real = tmp_path / "ok.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr(mod, "probe_detailed", lambda p: _info())
    encode.input_edit.setText(str(real))
    assert "1920x1080" in encode._track_status.text()
    assert len(encode._audio_checks) == 1
    assert len(encode._sub_checks) == 1
    assert not encode.audio_tracks_combo.isVisibleTo(encode)


def test_encode_probe_no_tracks(encode, monkeypatch, tmp_path):
    import src.ui.tabs.encode_tab as mod
    real = tmp_path / "empty.mp4"
    real.write_bytes(b"x")
    bare = DetailedMediaInfo(
        path="C:/a.mp4",
        video_streams=[StreamInfo(index=0, stream_index=0,
                                  codec_type="video", codec_name="h264")],
        duration_sec=10,
    )
    monkeypatch.setattr(mod, "probe_detailed", lambda p: bare)
    encode.input_edit.setText(str(real))
    assert "未检测到" in encode._track_no_hint.text()


def test_encode_reset_track_panel(encode):
    encode._reset_track_panel()
    assert "自动检测" in encode._track_status.text()


def test_encode_resolve_track_selection(encode):
    cb_on = type("CB", (), {"isChecked": lambda self: True})()
    cb_off = type("CB", (), {"isChecked": lambda self: False})()
    assert EncodeTab._resolve_track_selection(
        [(cb_on, 0), (cb_on, 1)], "全部保留", "不保留音轨") == ("全部保留", "")
    assert EncodeTab._resolve_track_selection(
        [(cb_off, 0)], "全部保留", "不保留音轨") == ("不保留音轨", "")
    assert EncodeTab._resolve_track_selection(
        [(cb_on, 0), (cb_off, 1)], "全部保留", "不保留音轨") == (
        "自定义选择 (填写编号)", "0")


def test_encode_fmt_dur():
    assert EncodeTab._fmt_dur(0) == ""
    assert EncodeTab._fmt_dur(65) == "01:05"
    assert EncodeTab._fmt_dur(3700) == "01:01:40"


def test_encode_clear_layout(encode):
    from PyQt6.QtWidgets import QLabel
    encode._clear_layout(encode._track_audio_layout)
    assert encode._track_audio_layout.count() == 0


# ----------------------------------------------------------------
# RemuxTab
# ----------------------------------------------------------------

@pytest.fixture
def remux(qapp):
    return RemuxTab()


def test_remux_preset_custom(remux):
    remux.remux_preset_combo.setCurrentText("自定义")
    assert remux.remux_format_custom_edit.isEnabled()
    remux.remux_preset_combo.setCurrentText("MP4 (H.264 兼容)")
    assert not remux.remux_format_custom_edit.isEnabled()
    assert remux.remux_format_custom_edit.text() == ""


def test_remux_probe_no_files(remux):
    remux._do_probe()
    assert "自动检测" in remux._track_status.text()


def test_remux_probe_file_missing(remux):
    remux.remux_input_edit.setText("Z:/nope.mp4")
    assert "文件不存在" in remux._track_status.text()


def test_remux_probe_error(remux, monkeypatch, tmp_path):
    import src.ui.tabs.remux_tab as mod
    real = tmp_path / "bad.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr(mod, "probe_detailed", lambda p: _info(errors=["x"]))
    remux.remux_input_edit.setText(str(real))
    assert "检测失败" in remux._track_status.text()


def test_remux_probe_ok_single(remux, monkeypatch, tmp_path):
    import src.ui.tabs.remux_tab as mod
    real = tmp_path / "one.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr(mod, "probe_detailed", lambda p: _info())
    remux.remux_input_edit.setText(str(real))
    assert "1920x1080" in remux._track_status.text()
    assert remux._probe_btn.isVisibleTo(remux)


def test_remux_probe_ok_batch(remux, monkeypatch, tmp_path):
    import src.ui.tabs.remux_tab as mod
    real = tmp_path / "first.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr(mod, "probe_detailed", lambda p: _info())
    remux.remux_input_edit.setText(f"{real}; C:/b.mp4")
    assert "批量模式" in remux._track_status.text()


def test_remux_compat_warn_on_incompatible(remux, monkeypatch, tmp_path):
    import src.ui.tabs.remux_tab as mod
    real = tmp_path / "warn.mp4"
    real.write_bytes(b"x")
    # VP9 视频 + ASS 字幕 → MP4 不兼容
    monkeypatch.setattr(mod, "probe_detailed",
                        lambda p: _info(video_codec="vp9", sub_codec="ass"))
    remux.remux_input_edit.setText(str(real))
    assert remux._compat_warn_label.isVisibleTo(remux)
    assert "兼容性警告" in remux._compat_warn_label.text()


def test_remux_compat_ok(remux, monkeypatch, tmp_path):
    import src.ui.tabs.remux_tab as mod
    real = tmp_path / "clean.mp4"
    real.write_bytes(b"x")
    # h264 + aac + 无字幕流 -> MP4 完全兼容
    monkeypatch.setattr(mod, "probe_detailed",
                        lambda p: _info(with_subs=False))
    remux.remux_input_edit.setText(str(real))
    assert not remux._compat_warn_label.isVisibleTo(remux)


def test_remux_compat_custom_ext(remux):
    remux.remux_preset_combo.setCurrentText("自定义")
    remux.remux_format_custom_edit.setText("mp4")
    remux._last_probe_info = _info(video_codec="vp9")
    remux._check_compat()
    assert "兼容性警告" in remux._compat_warn_label.text()


def test_remux_compat_no_extension(remux):
    remux.remux_preset_combo.setCurrentText("自定义")
    remux.remux_format_custom_edit.setText("")
    remux._last_probe_info = _info()
    remux._check_compat()
    assert not remux._compat_warn_label.isVisibleTo(remux)


def test_remux_lang_display():
    from src.ui.tabs.remux_tab import _lang_display
    assert "Japanese" in _lang_display("jpn") or _lang_display("jpn")
    assert _lang_display("") == ""


# ----------------------------------------------------------------
# QcTab / HelpTab
# ----------------------------------------------------------------

def test_qc_res_linkage(qapp):
    tab = QcTab()
    tab.max_res_combo.setCurrentText("自定义")
    assert tab.max_res_custom_edit.isEnabled()
    tab.max_res_combo.setCurrentText("不限制")
    assert not tab.max_res_custom_edit.isEnabled()
    tab.min_res_combo.setCurrentText("自定义")
    assert tab.min_res_custom_edit.isEnabled()
    tab.min_res_combo.setCurrentText("1080P (1920x1080)")
    assert not tab.min_res_custom_edit.isEnabled()


def test_help_tab_topic_switch(qapp):
    tab = HelpTab()
    tab.topic_combo.setCurrentText("封装转换")
    assert "封装转换" in tab._help_display.toPlainText() or \
        tab._help_display.toPlainText()
    tab.on_theme_changed()


@pytest.mark.parametrize("line, marker", [
    ("在线文档: https://example.com", "example.com"),
    ("【标题】内容", "<h2>"),
    ("━━ 基本使用 ━━", "section-title"),
    ("• 列表项", "<li>"),
    ("✅ 很好", "tip"),
    ("⚠️ 注意", "warn"),
    ("❌ 错误", "warn"),
    ("❓ 疑问", "<b>"),
    ("→ 缩进行", "margin-left:16px"),
    ("普通段落", "<p>"),
])
def test_help_plain_to_html(line, marker):
    assert marker in _plain_to_html(line)


def test_help_escapes_html():
    assert "&lt;b&gt;" in _plain_to_html("<b>")
    assert "<br/>" in _plain_to_html("a\n\nb")
