# -*- coding: utf-8 -*-
"""压制页 AviSynth 门禁测试 (M4.4)。

覆盖:
* platform_capabilities().avisynth_available 为 False 时隐藏「兼容模式 (字幕)」
  整行 (复选框 + 表单标签 + tooltip), libass 字幕路径与 build_args 键集不变;
* 为 True 时行为与改造前一致 (可见 / 有 tooltip / 勾选可生效);
* 探测结果推送后重新按平台快照同步 (apply_capabilities);
* 压制页/输出方案卡的硬件可用性仍复用 build_encoder_capabilities 结果。

平台快照通过 monkeypatch 页面模块里的 platform_capabilities 注入, 不做真实
平台探测。
"""

from PyQt6.QtWidgets import QCheckBox

import pytest

import src.ui.tabs.encode_tab as encode_tab_module
from src.capabilities.ffmpeg_probe import KEY_ENCODERS, FfmpegCaps
from src.presets import ENCODERS
from src.ui.tabs.encode_tab import COMPAT_MODE_TOOLTIP, EncodeTab


def _caps(encoders=None, probe_error=None):
    names = set(KEY_ENCODERS) if encoders is None else set(encoders)
    return FfmpegCaps(
        ffmpeg_path="C:/bin/ffmpeg.exe",
        version="7.1",
        encoders=frozenset(names),
        filters=frozenset(),
        hwaccels=frozenset(),
        probe_error=probe_error,
        probed_at=1.0,
    )


@pytest.fixture
def platform(monkeypatch, platform_caps_stub):
    """可变的平台能力快照 (用例里改属性后重新同步即可生效)。"""
    state = platform_caps_stub()
    monkeypatch.setattr(encode_tab_module, "platform_capabilities",
                        lambda refresh=False: state)
    return state


def _compat_label(tab):
    layout = tab.common_group.layout()
    return layout.labelForField(tab.compat_mode_cb)


# ----------------------------------------------------------------
# 隐藏 / 显示
# ----------------------------------------------------------------

def test_compat_row_visible_when_avisynth_available(qapp, platform):
    tab = EncodeTab()

    assert tab.compat_mode_cb.isHidden() is False
    assert tab.compat_mode_cb.toolTip() == COMPAT_MODE_TOOLTIP
    assert _compat_label(tab).isHidden() is False
    assert _compat_label(tab).text() == "兼容模式 (字幕)"


def test_compat_row_hidden_when_avisynth_unavailable(qapp, platform):
    platform.avisynth_available = False
    tab = EncodeTab()

    assert tab.compat_mode_cb.isHidden() is True
    assert tab.compat_mode_cb.toolTip() == ""  # 说明/tooltip 一并收起
    label = _compat_label(tab)
    assert label is not None
    assert label.isHidden() is True


def test_hidden_compat_checkbox_does_not_leak_into_args(qapp, platform):
    """隐藏行不改变 build_args 键集; 默认未勾选 → compat_mode=False。"""
    visible_tab = EncodeTab()
    visible_keys = set(vars(visible_tab.build_args()))

    platform.avisynth_available = False
    hidden_tab = EncodeTab()
    args = hidden_tab.build_args()

    assert set(vars(args)) == visible_keys
    assert args.compat_mode is False


def test_libass_subtitle_path_unchanged(qapp, platform, tmp_path):
    """普通 libass 字幕烧录路径不因门禁消失 (控件与参数都保持)。"""
    platform.avisynth_available = False
    tab = EncodeTab()
    subtitle = tmp_path / "sub.ass"
    subtitle.write_text("[Script Info]\n", encoding="utf-8")

    tab.subtitle_edit.setText(str(subtitle))
    args = tab.build_args()

    assert args.subtitle == str(subtitle)
    assert args.compat_mode is False
    assert tab.subtitle_edit.isHidden() is False
    assert tab.subtitle_tracks_combo.isHidden() is False
    assert tab.compat_mode_cb.isHidden() is True


def test_apply_capabilities_resyncs_avisynth_gate(qapp, platform):
    """探测结果推送时按最新平台快照重新同步 (AviSynth 由可用变不可用)。"""
    tab = EncodeTab()
    assert tab.compat_mode_cb.isHidden() is False

    platform.avisynth_available = False
    tab.apply_capabilities(_caps())

    assert tab.compat_mode_cb.isHidden() is True
    assert tab.compat_mode_cb.toolTip() == ""

    platform.avisynth_available = True
    tab.apply_capabilities(None)  # 未知/探测失败也重新同步

    assert tab.compat_mode_cb.isHidden() is False
    assert tab.compat_mode_cb.toolTip() == COMPAT_MODE_TOOLTIP


def test_compat_checkbox_feeds_build_args_when_visible(qapp, platform):
    """AviSynth 可用时勾选兼容模式照常进入参数 (行为不变)。"""
    tab = EncodeTab()
    assert tab.build_args().compat_mode is False

    tab.compat_mode_cb.setChecked(True)
    assert tab.build_args().compat_mode is True

    tab.compat_mode_cb.setChecked(False)
    assert tab.build_args().compat_mode is False


def test_widget_is_still_a_checkbox(qapp, platform):
    """硬约束: 控件属性/类型不变 (隐藏不等于移除)。"""
    platform.avisynth_available = False
    tab = EncodeTab()

    assert isinstance(tab.compat_mode_cb, QCheckBox)
    assert hasattr(tab, "compat_mode_cb")


# ----------------------------------------------------------------
# 编码器能力仍复用 build_encoder_capabilities
# ----------------------------------------------------------------

def test_encoder_catalog_still_drives_hardware_state(qapp, platform):
    tab = EncodeTab()
    tab.apply_capabilities(_caps(encoders={"libx264", "libx265"}))

    names = [cap.name for cap in tab.encoder_capabilities]
    assert names == list(ENCODERS.values())  # Windows 不追加 VideoToolbox
    assert tab.output_plan_card.cards[3].capability_label.text() == "NVENC 不可用"
