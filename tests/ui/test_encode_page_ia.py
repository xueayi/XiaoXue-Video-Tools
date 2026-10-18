# -*- coding: utf-8 -*-
"""PR-04 视频压制页信息架构测试 (全部离屏, 不跑真实 ffmpeg)。

覆盖:
- 布局顺序 / 高级设置默认折叠
- 输出方案 5 卡与既有预设、ENCODERS 反查的映射
- 常规选项卡 8 字段与错误态 (monkeypatch probe_detailed)
- 执行摘要与 resolve_encoder_params 逐项一致 (含自动输出路径)
- build_args 键集不变 / 预设模式锁定被覆盖的控件
"""

import os

import pytest
from PyQt6.QtWidgets import QCheckBox, QFormLayout, QLabel, QToolButton

from src.encode_params import resolve_encoder_params
from src.media_probe import DetailedMediaInfo, StreamInfo
from src.presets import (
    AUDIO_ENCODERS, ENCODE_OUTPUT_FORMATS, ENCODERS, QUALITY_PRESETS,
    RATE_CONTROL_MODES,
)
from src.ui.execution_summary import PLACEHOLDER
from src.ui.input_media_card import INFO_FIELDS
from src.ui.output_plan_card import PLAN_TARGETS, encoder_badge
from src.ui.tabs import EncodeTab
from src.ui.widgets import WheelGuardComboBox
from src.utils import generate_output_path


@pytest.fixture
def tab(qapp):
    return EncodeTab()


# ----------------------------------------------------------------
# 工具
# ----------------------------------------------------------------

def _top_level_widgets(tab):
    layout = tab._main_layout
    widgets = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if widget is not None:
            widgets.append(widget)
    return widgets


def _resolved(tab):
    """与页面/执行器同源地解析当前参数。"""
    return resolve_encoder_params(
        args=tab.build_args(),
        quality_presets=QUALITY_PRESETS,
        encoders=ENCODERS,
        audio_encoders=AUDIO_ENCODERS,
        rate_control_modes=RATE_CONTROL_MODES,
        generate_output_path_func=generate_output_path,
    )


def _probe_info(file_size_bytes=123 * 1024 * 1024, duration_sec=65.4):
    return DetailedMediaInfo(
        path="C:/media/片头.mp4",
        file_size_bytes=file_size_bytes,
        duration_sec=duration_sec,
        video_streams=[StreamInfo(
            index=0, stream_index=0, codec_type="video", codec_name="h264",
            profile="High", width=1920, height=1080, fps=23.976,
        )],
        audio_streams=[
            StreamInfo(index=0, stream_index=1, codec_type="audio",
                       codec_name="aac"),
            StreamInfo(index=1, stream_index=2, codec_type="audio",
                       codec_name="aac"),
        ],
        subtitle_streams=[StreamInfo(
            index=0, stream_index=3, codec_type="subtitle", codec_name="ass",
        )],
    )


def _set_missing_input(tab, tmp_path, name="clip.mp4"):
    """设置一个不存在的输入路径：跳过真实 ffprobe，仅刷新摘要。"""
    tab.input_edit.setText(str(tmp_path / name))


# ----------------------------------------------------------------
# 布局顺序 / 折叠
# ----------------------------------------------------------------

def test_layout_order_matches_ia(tab):
    widgets = _top_level_widgets(tab)
    assert widgets[0] is tab.input_media_card
    index = {widget: position for position, widget in enumerate(widgets)}

    # A 常规选项 < B 字幕策略 < C 视频输出策略 < D 音频输出策略
    # < E 压制后分发 < F 片段截取 < G 高级折叠头 < H 执行摘要(页尾)
    assert index[tab.input_media_card] < index[tab.subtitle_group]
    assert index[tab.subtitle_group] < index[tab.output_plan_card]
    assert index[tab.output_plan_card] < index[tab.audio_group]
    assert index[tab.audio_group] < index[tab.transfer_group]
    assert index[tab.transfer_group] < index[tab.clip_editor]
    assert index[tab.clip_editor] < index[tab.advanced_header]
    assert index[tab.advanced_header] < index[tab.summary_card]
    assert widgets[-1] is tab.summary_card
    # 预设下拉仍复用视频输出策略卡内的唯一实例
    assert tab.preset_combo is tab.output_plan_card.preset_combo


def test_transfer_group_hint_removed(tab):
    """「压制与分发」分组里的注释框已按要求整块删除。"""
    texts = [label.text() for label in tab.transfer_group.findChildren(QLabel)]
    assert not any("WebDAV" in text for text in texts)
    assert not any("NAS/云端" in text for text in texts)


def test_general_options_then_subtitle_strategy(tab):
    """高频输入在最前，字幕策略紧随其后 (A 常规选项 → B 字幕策略 → C 视频输出策略)。"""
    widgets = _top_level_widgets(tab)
    assert widgets[0] is tab.input_media_card
    assert widgets[1] is tab.subtitle_group
    assert widgets[2] is tab.output_plan_card
    # 常规选项里集中了三个高频输入
    card = tab.input_media_card
    assert card.title() == "常规选项"
    for widget in (tab.input_edit, tab.subtitle_edit, tab.output_edit):
        assert card.isAncestorOf(widget)


def test_three_strategy_groups_own_their_controls(tab):
    """视频/音频/字幕三块策略各自包含对应控件。"""
    assert tab.output_plan_card.title() == "视频输出策略"
    assert tab.output_plan_card.isAncestorOf(tab.output_format_combo)
    assert tab.output_plan_card.isAncestorOf(tab.resolution_edit)
    # 输出路径已上移到「常规选项」
    assert not tab.output_plan_card.isAncestorOf(tab.output_edit)

    assert tab.audio_group.isAncestorOf(tab.audio_encoder_combo)
    assert tab.audio_group.isAncestorOf(tab.audio_bitrate_combo)
    assert tab.audio_group.isAncestorOf(tab.audio_tracks_combo)

    assert tab.subtitle_group.isAncestorOf(tab.subtitle_mode_combo)
    assert tab.subtitle_group.isAncestorOf(tab.compat_mode_cb)
    assert tab.subtitle_group.isAncestorOf(tab.subtitle_tracks_combo)
    # 字幕文件选择器在「常规选项」，处理方式在「字幕策略」
    assert not tab.subtitle_group.isAncestorOf(tab.subtitle_edit)


def test_advanced_group_collapsed_by_default(tab):
    assert isinstance(tab.advanced_header, QToolButton)
    assert tab.advanced_header.isChecked() is False
    assert tab.advanced_content.isHidden() is True
    # 编码/质量/fps/额外参数控件都迁入了折叠内容
    for widget in (
        tab.encoder_combo, tab.speed_preset_combo, tab.nvenc_preset_combo,
        tab.rate_control_combo, tab.crf_spin, tab.video_bitrate_combo,
        tab.fps_spin, tab.extra_args_edit, tab.debug_mode_cb,
        tab.audio_tracks_custom_edit, tab.subtitle_tracks_custom_edit,
    ):
        assert tab.advanced_content.isAncestorOf(widget)


# ----------------------------------------------------------------
# B. 输出方案卡
# ----------------------------------------------------------------

def test_plan_cards_map_to_existing_presets(tab):
    cards = tab.output_plan_card.cards
    assert len(cards) == 5
    assert len(PLAN_TARGETS) == 5
    assert [card.target.title for card in cards] == [
        "均衡 H.264", "高质量 H.264", "HEVC 高压缩", "硬件极速", "自定义",
    ]
    for card in cards:
        assert card.preset_name in QUALITY_PRESETS
    # 5 卡覆盖任务指定的预设
    assert [card.preset_name for card in cards] == [
        "【均衡画质】x264 常用导出 (CRF18)",
        "【极致画质】x264 4K/高动态/AMV (CRF16)",
        "【均衡画质】x265/HEVC 高效压缩 (CRF20)",
        "【速度优先】NVIDIA 显卡加速",
        "自定义 (Custom)",
    ]


def test_more_presets_keeps_all_presets(tab):
    combo = tab.preset_combo
    assert combo is tab.output_plan_card.preset_combo
    # 统一使用抗误滚轮、自绘三角箭头的下拉框
    assert isinstance(combo, WheelGuardComboBox)
    # 原有 7 个预设 + 新增「复制视频流」预设
    assert combo.count() == len(QUALITY_PRESETS) == 8
    assert [combo.itemText(i) for i in range(combo.count())] == list(
        QUALITY_PRESETS.keys()
    )
    assert "【复制视频流】不重新编码" in [
        combo.itemText(i) for i in range(combo.count())]


def test_plan_card_encoder_badge_derived_from_presets(tab):
    """卡面 encoder 文案必须由 preset -> ENCODERS 反查，而不是手写常量。"""
    for card in tab.output_plan_card.cards:
        preset = QUALITY_PRESETS[card.preset_name]
        encoder = preset.get("encoder")
        if encoder is None:
            assert card.badge_label.text() == "自定义参数"
            continue
        display_name = next(
            name for name, value in ENCODERS.items() if value == encoder
        )
        codec = display_name.split("(")[0].strip()
        assert codec in card.badge_label.text()
        assert encoder in card.badge_label.text()
        quality = preset.get("crf") if preset.get("crf") is not None else preset.get("cq")
        assert str(quality) in card.badge_label.text()

    assert encoder_badge("【均衡画质】x264 常用导出 (CRF18)") == (
        "H.264 · libx264 · CRF 18"
    )
    assert encoder_badge("【均衡画质】x265/HEVC 高效压缩 (CRF20)") == (
        "H.265/HEVC · libx265 · CRF 20"
    )
    assert encoder_badge("自定义 (Custom)") == "自定义参数"


def test_hardware_card_marks_capability_pending(tab):
    hardware_cards = [c for c in tab.output_plan_card.cards if c.target.hardware]
    assert len(hardware_cards) == 1
    hardware = hardware_cards[0]
    assert hardware.preset_name == "【速度优先】NVIDIA 显卡加速"
    assert hardware.capability_label.isHidden() is False
    assert hardware.capability_label.text() == "待能力检测"
    for card in tab.output_plan_card.cards:
        if card is hardware:
            continue
        assert card.capability_label.isHidden() is True


def test_plan_card_click_switches_preset_and_linkage(tab):
    hevc = tab.output_plan_card.card_for_preset(
        "【均衡画质】x265/HEVC 高效压缩 (CRF20)"
    )
    assert hevc is not None
    hevc.click()
    assert tab.preset_combo.currentText() == hevc.preset_name
    assert hevc.is_selected() is True
    assert tab.crf_spin.value() == 20
    assert tab.encoder_combo.currentText() == "H.265/HEVC (CPU - libx265)"
    # 预设模式：编码器控件锁定
    assert tab.encoder_combo.isEnabled() is False

    custom = tab.output_plan_card.card_for_preset("自定义 (Custom)")
    custom.click()
    assert tab.preset_combo.currentText() == "自定义 (Custom)"
    assert tab.encoder_combo.isEnabled() is True
    # 同一时刻只有一张卡处于选中态
    assert len([c for c in tab.output_plan_card.cards if c.is_selected()]) == 1


def test_plan_card_selection_is_a_checkbox_with_checkmark(tab):
    """选中态由右上角复选框的勾号表示, 不再画强调色矩形描边。"""
    cards = tab.output_plan_card.cards
    target = cards[1]
    target.click()
    for card in cards:
        assert isinstance(card.check_box, QCheckBox)
        assert card.check_box.isChecked() is (card is target)
    # 勾号来自 QSS 的 image 规则: 只给背景色会得到没有勾号的实心方块
    from src.ui import theme
    expected_icon = {"light": "checkbox-tick.svg", "dark": "checkbox-tick-dark.svg"}
    for name, icon in expected_icon.items():
        qss = theme.get_stylesheet(name)
        assert "QCheckBox#plan_check::indicator:checked" in qss
        assert icon in qss


def test_plan_param_form_grows_fields(tab):
    """macOS 的 QMacStyle 默认 FieldsStayAtSizeHint, 表单会整块居中。

    这里锁住统一后的增长策略, 保证三平台表单都撑满可用宽度。
    """
    form = tab.output_plan_card.param_form()
    assert form.fieldGrowthPolicy() == (
        QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)


# ----------------------------------------------------------------
# A. 输入媒体卡
# ----------------------------------------------------------------

def test_input_media_card_renders_eight_fields(tab, monkeypatch, tmp_path):
    import src.ui.tabs.encode_tab as mod
    real = tmp_path / "片头.mp4"
    real.write_bytes(b"x")
    info = _probe_info()
    monkeypatch.setattr(mod, "probe_detailed", lambda path: info)

    tab.input_edit.setText(str(real))

    card = tab.input_media_card
    assert card.last_info is info
    assert [key for key, _title in INFO_FIELDS] == [
        "filename", "resolution", "codec", "fps", "duration", "size",
        "audio_tracks", "subtitle_tracks",
    ]
    assert len(INFO_FIELDS) == 8
    assert card.field_text("filename") == "片头.mp4"
    assert card.field_text("resolution") == "1920x1080"
    assert "h264" in card.field_text("codec")
    assert "23.976" in card.field_text("fps")
    assert card.field_text("duration") == "01:05"
    assert card.field_text("size") == "123.00 MB"
    assert card.field_text("audio_tracks") == "2"
    assert card.field_text("subtitle_tracks") == "1"
    assert "已探测" in card.status_label.text()
    # 轨道面板同步
    assert len(tab._audio_checks) == 2
    assert len(tab._sub_checks) == 1


def test_input_media_card_probe_error_state(tab, monkeypatch, tmp_path):
    import src.ui.tabs.encode_tab as mod
    real = tmp_path / "坏文件.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr(
        mod, "probe_detailed",
        lambda path: DetailedMediaInfo(path=str(real), errors=["ffprobe 无法读取文件: x"]),
    )

    tab.input_edit.setText(str(real))

    card = tab.input_media_card
    assert card.last_info is None
    assert "探测失败" in card.status_label.text()
    assert all(value == "—" for value in card.field_values().values())
    assert "检测失败" in tab._track_status.text()


def test_input_media_card_missing_file_state(tab):
    tab.input_edit.setText("Z:/不存在/xx.mp4")
    card = tab.input_media_card
    assert card.last_info is None
    assert "文件不存在" in card.status_label.text()
    assert all(value == "—" for value in card.field_values().values())


def test_input_media_card_reset_when_input_cleared(tab, monkeypatch, tmp_path):
    import src.ui.tabs.encode_tab as mod
    real = tmp_path / "ok.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr(mod, "probe_detailed", lambda path: _probe_info())
    tab.input_edit.setText(str(real))
    assert tab.input_media_card.field_text("audio_tracks") == "2"

    tab.input_edit.setText("")
    card = tab.input_media_card
    assert card.last_info is None
    assert all(value == "—" for value in card.field_values().values())


# ----------------------------------------------------------------
# C. 常用设置：画质镜像 / 预设锁定
# ----------------------------------------------------------------

def test_quality_mirror_readonly(tab):
    # 默认预设模式: 画质镜像显示 crf_spin 值, 并提示高级设置可调
    assert "18" in tab.quality_mirror_label.text()
    assert "高级设置" in tab._quality_hint.text()
    # 预设切换后镜像跟随
    tab.preset_combo.setCurrentText("【均衡画质】x265/HEVC 高效压缩 (CRF20)")
    assert "20" in tab.quality_mirror_label.text()
    # 自定义模式下直接改 crf_spin, 镜像实时跟随
    tab.preset_combo.setCurrentText("自定义 (Custom)")
    tab.crf_spin.setValue(30)
    assert "30" in tab.quality_mirror_label.text()


def test_preset_mode_locks_overridden_controls(tab):
    tab.preset_combo.setCurrentText("【均衡画质】x264 常用导出 (CRF18)")
    for widget in (
        tab.resolution_edit,
        tab.fps_spin,
        tab.audio_encoder_combo,
        tab.audio_bitrate_combo,
    ):
        assert widget.isEnabled() is False
    assert tab._preset_lock_hint.isHidden() is False

    tab.preset_combo.setCurrentText("自定义 (Custom)")
    for widget in (
        tab.resolution_edit,
        tab.fps_spin,
        tab.audio_encoder_combo,
        tab.audio_bitrate_combo,
    ):
        assert widget.isEnabled() is True
    assert tab._preset_lock_hint.isHidden() is True


# ----------------------------------------------------------------
# F. 执行摘要
# ----------------------------------------------------------------

def test_summary_placeholder_without_input(tab):
    card = tab.summary_card
    assert card.last_params is None
    for key in ("video", "audio", "subtitle", "format", "output"):
        assert card.row_text(key) == PLACEHOLDER
    assert PLACEHOLDER in card.all_text()


@pytest.mark.parametrize("preset_name", list(QUALITY_PRESETS.keys()))
def test_summary_matches_resolve_encoder_params(tab, tmp_path, preset_name):
    _set_missing_input(tab, tmp_path)
    tab.preset_combo.setCurrentText(preset_name)

    expected = _resolved(tab)
    card = tab.summary_card

    # 摘要必须使用与 executor 完全一致的解析结果
    assert card.last_params == expected
    assert card.auto_generated is True

    text = card.all_text()
    if expected.encoder == "copy":
        # 复制视频流: 摘要用中文说明, 不直接展示内部标识
        assert "复制视频流" in card.row_text("video")
    else:
        assert expected.encoder in text
    assert expected.output_path in text
    assert "自动生成" in card.row_text("output")
    assert expected.output_path == generate_output_path(
        expected.input_path,
        QUALITY_PRESETS[preset_name]["encoder"] or expected.encoder,
        ENCODE_OUTPUT_FORMATS[tab.output_format_combo.currentText()],
    )

    video = card.row_text("video")
    if expected.encoder == "copy":
        assert "复制视频流" in video
    else:
        assert expected.encoder in video
    if expected.crf is not None:
        assert f"CRF {expected.crf}" in video
    if expected.bitrate:
        assert expected.bitrate in video
    if expected.speed_preset:
        assert f"速度 {expected.speed_preset}" in video

    if expected.audio_encoder == "copy":
        assert "复制" in card.row_text("audio")
    else:
        assert expected.audio_encoder in card.row_text("audio")
        assert expected.audio_bitrate in card.row_text("audio")


def test_summary_matches_resolve_custom_params(tab, tmp_path):
    _set_missing_input(tab, tmp_path)
    tab.preset_combo.setCurrentText("自定义 (Custom)")
    # M3.2: 真 2-Pass 仅 CPU 编码器 (硬件 2pass 会回退 VBR/multipass)
    tab.encoder_combo.setCurrentText("H.264 (CPU - libx264)")
    tab.rate_control_combo.setCurrentText("2-Pass VBR (两遍编码)")
    tab.video_bitrate_combo.setCurrentText("8M")
    tab.resolution_edit.setText("1280x720")
    tab.fps_spin.setValue(30)
    tab.audio_encoder_combo.setCurrentText("AAC (推荐)")
    tab.audio_bitrate_combo.setCurrentText("256k")

    expected = _resolved(tab)
    card = tab.summary_card
    assert card.last_params == expected
    assert expected.encoder == "libx264"
    assert expected.bitrate == "8M"
    assert expected.speed_preset == "medium"
    assert expected.resolution == "1280x720"
    assert expected.fps == 30
    assert expected.get_encode_mode().value == "2pass"

    video = card.row_text("video")
    for token in ("libx264", "码率 8M", "2-Pass VBR", "速度 medium",
                  "分辨率 1280x720", "帧率 30"):
        assert token in video
    audio = card.row_text("audio")
    assert "aac" in audio and "256k" in audio


def test_summary_hardware_2pass_never_claims_two_pass(qapp, tmp_path):
    """M3.2: 硬件 + 2-Pass 摘要不再出现 "2-Pass" 字样 (跟随 get_encode_mode)。"""
    from src.ui.args_builder import ArgsNamespace
    from src.ui.execution_summary import ExecutionSummaryCard

    card = ExecutionSummaryCard()
    args = ArgsNamespace(
        command="视频压制",
        input=str(tmp_path / "clip.mp4"), output="", subtitle="",
        compat_mode=False, preset="自定义 (Custom)",
        encoder="H.264 (NVIDIA NVENC)", speed_preset="medium",
        nvenc_preset="使用预设默认", rate_control="2-Pass VBR (两遍编码)",
        crf=20, video_bitrate="8M", output_format="MP4",
        output_format_custom="", resolution="", fps=0,
        audio_encoder="复制 (不重新编码)", audio_bitrate="192k",
        audio_tracks="仅保留第 1 条 (#0)", audio_tracks_custom="",
        subtitle_tracks="不保留字幕", subtitle_tracks_custom="",
        post_transfer_mode="不分发", post_transfer_dir="",
        extra_args="", debug_mode=False,
    )
    params = card.update_from_args(args)

    assert params is not None
    assert params.encoder == "h264_nvenc"
    assert params.get_encode_mode().value != "2pass"
    assert "2-Pass" not in card.row_text("video")
    assert "码率 8M" in card.row_text("video")


def test_summary_subtitle_burn_and_keep(tab, tmp_path):
    _set_missing_input(tab, tmp_path)
    subtitle = tmp_path / "sub.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    tab.preset_combo.setCurrentText("自定义 (Custom)")
    tab.subtitle_edit.setText(str(subtitle))
    tab.compat_mode_cb.setChecked(True)
    # 内封字幕流仅 MKV / MOV 可用, 先切到 MKV 再选择保留编号
    tab.output_format_combo.setCurrentText("MKV")
    tab.subtitle_tracks_combo.setCurrentText("自定义选择 (填写编号)")
    tab.subtitle_tracks_custom_edit.setText("0,1")

    expected = _resolved(tab)
    card = tab.summary_card
    assert card.last_params == expected
    text = card.row_text("subtitle")
    assert "内嵌" in text and "sub.srt" in text
    assert "AviSynth+VSFilter" in text
    assert "0,1" in text

    # MP4 输出: 保留字幕流不可选, 参数强制为「不保留字幕」
    tab.output_format_combo.setCurrentText("MP4")
    assert not tab.subtitle_tracks_combo.isEnabled()
    assert tab.subtitle_tracks_combo.currentText() == "不保留字幕"
    mp4_expected = _resolved(tab)
    assert mp4_expected.subtitle_tracks == "none"  # 标签「不保留字幕」解析后的值
    assert "0,1" not in card.row_text("subtitle")

    # 取消烧录与兼容模式后实时刷新
    tab.subtitle_edit.setText("")
    tab.compat_mode_cb.setChecked(False)
    assert "不处理外挂字幕" in card.row_text("subtitle")
    assert "AviSynth+VSFilter" not in card.row_text("subtitle")


def test_subtitle_mode_offers_embed_only_for_subtitle_containers(tab):
    """内封只对 MKV / MOV 开放; MP4 下该项禁用并回退到内嵌。"""
    combo = tab.subtitle_mode_combo
    assert combo.currentText() == "内嵌（烧录进画面）"
    embed_row = next(
        row for row in range(combo.count()) if "内封" in combo.itemText(row))

    tab.output_format_combo.setCurrentText("MP4")
    model = combo.model()
    assert model.item(embed_row).isEnabled() is False

    tab.output_format_combo.setCurrentText("MKV")
    assert model.item(embed_row).isEnabled() is True
    combo.setCurrentText(combo.itemText(embed_row))
    assert tab.build_args().subtitle_mode == "内封（转为软字幕流）"

    # 兼容模式只在内嵌烧录时可用
    assert tab.compat_mode_cb.isEnabled() is False
    combo.setCurrentText("内嵌（烧录进画面）")
    assert tab.compat_mode_cb.isEnabled() is True


def test_summary_shows_embed_mode(tab, tmp_path):
    _set_missing_input(tab, tmp_path)
    subtitle = tmp_path / "sub.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    tab.output_format_combo.setCurrentText("MKV")
    tab.subtitle_edit.setText(str(subtitle))
    tab.subtitle_mode_combo.setCurrentText("内封（转为软字幕流）")

    text = tab.summary_card.row_text("subtitle")
    assert "内封" in text and "sub.srt" in text
    assert tab.summary_card.last_params.subtitle_mode == "embed"

    # 不处理: 文件保留但不参与输出
    tab.subtitle_mode_combo.setCurrentText("不处理")
    assert "不处理外挂字幕" in tab.summary_card.row_text("subtitle")
    assert tab.summary_card.last_params.subtitle_mode == "none"
    assert tab.summary_card.last_params.subtitle_path  # 路径仍记录, 便于改回


def test_copy_mode_keeps_subtitle_file_and_switches_to_embed(tab, tmp_path):
    """复制视频流不能烧录, 但字幕文件保留并自动改为内封。"""
    subtitle = tmp_path / "sub.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    tab.output_format_combo.setCurrentText("MKV")
    tab.subtitle_edit.setText(str(subtitle))
    assert tab.subtitle_mode_combo.currentText() == "内嵌（烧录进画面）"

    tab.preset_combo.setCurrentText("【复制视频流】不重新编码")
    assert tab.subtitle_edit.isEnabled() is True
    assert tab.subtitle_edit.text() == str(subtitle)
    assert tab.subtitle_mode_combo.currentText() == "内封（转为软字幕流）"
    assert tab.build_args().subtitle_mode == "内封（转为软字幕流）"

    # 切回普通预设不强制改回内嵌
    tab.preset_combo.setCurrentText("【均衡画质】x264 常用导出 (CRF18)")
    assert tab.subtitle_mode_combo.currentText() == "内封（转为软字幕流）"


def test_summary_tracks_output_format_and_path_live(tab, tmp_path):
    _set_missing_input(tab, tmp_path)

    tab.output_format_combo.setCurrentText("MKV")
    expected = _resolved(tab)
    assert expected.output_path.endswith(".mkv")
    assert expected.output_path in tab.summary_card.all_text()
    assert tab.summary_card.row_text("format") == "MKV (.mkv)"

    custom_output = str(tmp_path / "final.mp4")
    tab.output_edit.setText(custom_output)
    card = tab.summary_card
    assert card.last_params.output_path == custom_output
    assert card.auto_generated is False
    assert custom_output in card.row_text("output")
    assert "自动生成" not in card.row_text("output")
    assert card.row_text("format") == "MP4 (.mp4)"


def test_summary_refreshes_on_any_parameter_change(tab, tmp_path):
    _set_missing_input(tab, tmp_path)
    card = tab.summary_card
    before = card.all_text()

    tab.preset_combo.setCurrentText("【均衡画质】x265/HEVC 高效压缩 (CRF20)")
    after_preset = card.all_text()
    assert after_preset != before
    assert "libx265" in after_preset

    tab.preset_combo.setCurrentText("自定义 (Custom)")
    tab.resolution_edit.setText("640x360")
    assert "分辨率 640x360" in card.row_text("video")

    tab.extra_args_edit.setText("-tune animation")
    assert card.last_params.extra_args == "-tune animation"


def test_summary_uses_shared_resolver(qapp, monkeypatch, tmp_path):
    """执行摘要必须调用 encode_params.resolve_encoder_params，不得另拼参数。"""
    import src.ui.execution_summary as summary_mod

    real_resolver = summary_mod.resolve_encoder_params
    calls = []

    def spy(**kwargs):
        calls.append(kwargs)
        return real_resolver(**kwargs)

    monkeypatch.setattr(summary_mod, "resolve_encoder_params", spy)

    tab = EncodeTab()
    _set_missing_input(tab, tmp_path)

    assert calls, "执行摘要未调用 resolve_encoder_params"
    last = calls[-1]
    from src.presets import ALL_QUALITY_PRESETS
    assert last["quality_presets"] is ALL_QUALITY_PRESETS
    assert last["encoders"] is ENCODERS
    assert last["audio_encoders"] is AUDIO_ENCODERS
    assert last["rate_control_modes"] is RATE_CONTROL_MODES
    assert last["generate_output_path_func"] is generate_output_path
    assert tab.summary_card.last_params == real_resolver(**last)


# ----------------------------------------------------------------
# 硬约束：build_args 键集 / command 不变
# ----------------------------------------------------------------

EXPECTED_BUILD_ARGS_KEYS = {
    "command", "input", "output", "subtitle", "compat_mode", "preset",
    "encoder", "speed_preset", "nvenc_preset", "rate_control", "crf",
    "video_bitrate", "output_format", "output_format_custom", "resolution",
    "fps", "audio_encoder", "audio_bitrate", "audio_tracks",
    "audio_tracks_custom", "subtitle_tracks", "subtitle_tracks_custom",
    "subtitle_mode",
    "post_transfer_mode", "post_transfer_dir", "extra_args", "debug_mode",
}


def test_build_args_key_set_unchanged(tab):
    args = tab.build_args()
    assert args.command == "视频压制"
    assert set(vars(args)) == EXPECTED_BUILD_ARGS_KEYS


def test_existing_control_attributes_preserved(tab):
    for attribute in (
        "preset_combo", "input_edit", "output_edit", "crf_spin",
        "audio_encoder_combo", "audio_bitrate_combo", "video_bitrate_combo",
        "encoder_combo", "speed_preset_combo", "nvenc_preset_combo",
        "rate_control_combo", "output_format_combo",
        "output_format_custom_edit", "resolution_edit", "fps_spin",
        "audio_tracks_combo", "audio_tracks_custom_edit",
        "subtitle_edit", "subtitle_mode_combo", "subtitle_tracks_combo",
        "subtitle_tracks_custom_edit", "compat_mode_cb",
        "post_transfer_mode_combo", "post_transfer_dir_edit",
        "extra_args_edit", "debug_mode_cb", "_track_status",
        "_audio_checks", "_sub_checks",
    ):
        assert hasattr(tab, attribute), attribute
