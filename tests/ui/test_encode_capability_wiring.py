# -*- coding: utf-8 -*-
"""M3.2 编码器能力 → 压制页联动测试。

覆盖:
* 编码器下拉按探测结果置灰/回退 CPU、预设下拉 NVENC 预设置灰；
* RC 下拉按编码器过滤 (硬件去掉 2-Pass) 与不支持项回退；
* 速度档按编码器重建 (AMF=speed/balanced/quality, QSV=CPU 档) 且仅自定义可用；
* 输出方案硬件卡三态 (待检测/可用/不可用 + 禁用点击无效)；
* 主窗口能力探测回调把快照转发给 UI 页 (探测失败归一为 None)。
全部 offscreen, 不跑真实 ffmpeg。
"""

import pytest

from src.capabilities.ffmpeg_probe import KEY_ENCODERS, FfmpegCaps
from src.presets import CPU_PRESETS
from src.ui.main_window import MainWindow
from src.ui.tabs import EncodeTab

NVENC_PRESET = "【速度优先】NVIDIA 显卡加速"
DEFAULT_PRESET = "【均衡画质】x264 常用导出 (CRF18)"
RC_CRF = "CRF/CQ (恒定质量)"
RC_2PASS = "2-Pass VBR (两遍编码)"


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


CPU_ONLY = ("libx264", "libx265")
NO_HW_CAPS = lambda: _caps(CPU_ONLY)  # noqa: E731


def _item_enabled(combo, index):
    item = combo.model().item(index)
    return True if item is None else item.isEnabled()


def _item_tooltip(combo, index):
    from PyQt6.QtCore import Qt

    item = combo.model().item(index)
    if item is None:
        return None
    return item.data(Qt.ItemDataRole.ToolTipRole)


def _combo_items(combo):
    return [combo.itemText(index) for index in range(combo.count())]


@pytest.fixture
def tab(qapp):
    return EncodeTab()


@pytest.fixture
def win(qapp):
    window = MainWindow()
    yield window
    window.close()


def _encode_tab_of(window):
    return window._tabs[window._page_index["视频压制"]]


def _enter_custom(tab):
    tab.preset_combo.setCurrentText("自定义 (Custom)")


# ----------------------------------------------------------------
# 编码器下拉置灰 / 回退
# ----------------------------------------------------------------

def test_initial_unknown_caps_keep_all_encoders_enabled(tab):
    assert tab.encoder_combo.count() == 6
    for index in range(tab.encoder_combo.count()):
        assert _item_enabled(tab.encoder_combo, index) is True
    # 未知能力 -> 硬件卡保持「待能力检测」
    hardware_card = tab.output_plan_card.cards[3]
    assert hardware_card.capability_label.text() == "待能力检测"
    assert hardware_card.isEnabled() is True


def test_apply_capabilities_disables_missing_hardware(tab):
    tab.apply_capabilities(NO_HW_CAPS())

    for index in range(tab.encoder_combo.count()):
        display = tab.encoder_combo.itemText(index)
        is_hardware = "CPU" not in display
        assert _item_enabled(tab.encoder_combo, index) is (not is_hardware)
        if is_hardware:
            assert _item_tooltip(tab.encoder_combo, index) == (
                "未检测到该硬件编码器")

    # NVENC 两个预设同样置灰 + tooltip
    preset_combo = tab.preset_combo
    nvenc_presets = [NVENC_PRESET, "【画质优先】NVIDIA 显卡加速 (HQ)"]
    for preset_name in nvenc_presets:
        index = preset_combo.findText(preset_name)
        assert index >= 0
        assert _item_enabled(preset_combo, index) is False
        assert _item_tooltip(preset_combo, index) == "依赖的硬件编码器不可用"
    # CPU 预设保持可用
    cpu_index = preset_combo.findText(DEFAULT_PRESET)
    assert _item_enabled(preset_combo, cpu_index) is True
    # 当前是 CPU 预设, 不应被回退
    assert preset_combo.currentText() == DEFAULT_PRESET


def test_current_encoder_falls_back_to_cpu_when_unavailable(tab):
    _enter_custom(tab)
    tab.encoder_combo.setCurrentText("H.264 (NVIDIA NVENC)")
    assert tab.encoder_combo.currentText() == "H.264 (NVIDIA NVENC)"

    tab.apply_capabilities(NO_HW_CAPS())
    assert tab.encoder_combo.currentText() == "H.264 (CPU - libx264)"
    assert _combo_items(tab.rate_control_combo) == [
        RC_CRF, "VBR (可变码率)", "CBR (恒定码率)", RC_2PASS]


def test_current_nvenc_preset_falls_back_when_nvenc_unavailable(tab):
    tab.preset_combo.setCurrentText(NVENC_PRESET)
    tab.apply_capabilities(NO_HW_CAPS())
    assert tab.preset_combo.currentText() == DEFAULT_PRESET


def test_apply_capabilities_unknown_restores_all_items(tab):
    tab.apply_capabilities(NO_HW_CAPS())
    tab.apply_capabilities(None)
    for index in range(tab.encoder_combo.count()):
        assert _item_enabled(tab.encoder_combo, index) is True
    for index in range(tab.preset_combo.count()):
        assert _item_enabled(tab.preset_combo, index) is True
    assert tab.output_plan_card.cards[3].capability_label.text() == "待能力检测"


# ----------------------------------------------------------------
# RC 下拉联动
# ----------------------------------------------------------------

def test_rc_options_filtered_by_encoder(tab):
    _enter_custom(tab)
    assert _combo_items(tab.rate_control_combo) == [
        RC_CRF, "VBR (可变码率)", "CBR (恒定码率)", RC_2PASS]

    tab.encoder_combo.setCurrentText("H.264 (NVIDIA NVENC)")
    assert _combo_items(tab.rate_control_combo) == [
        RC_CRF, "VBR (可变码率)", "CBR (恒定码率)"]
    assert "不支持 2-Pass" in tab.rate_control_combo.toolTip()

    tab.encoder_combo.setCurrentText("H.264 (AMD AMF)")
    assert RC_2PASS not in _combo_items(tab.rate_control_combo)
    assert "不支持 2-Pass" in tab.rate_control_combo.toolTip()

    tab.encoder_combo.setCurrentText("H.264 (CPU - libx264)")
    assert _combo_items(tab.rate_control_combo) == [
        RC_CRF, "VBR (可变码率)", "CBR (恒定码率)", RC_2PASS]
    assert tab.rate_control_combo.toolTip() == ""


def test_rc_falls_back_to_crf_when_current_unsupported(tab):
    _enter_custom(tab)
    tab.rate_control_combo.setCurrentText(RC_2PASS)
    assert tab.rate_control_combo.currentText() == RC_2PASS

    tab.encoder_combo.setCurrentText("H.264 (NVIDIA NVENC)")
    assert tab.rate_control_combo.currentText() == RC_CRF
    assert tab.crf_spin.isEnabled() is True
    assert tab.video_bitrate_combo.isEnabled() is False


# ----------------------------------------------------------------
# 速度档联动
# ----------------------------------------------------------------

def test_speed_options_amf(tab):
    _enter_custom(tab)
    tab.encoder_combo.setCurrentText("H.264 (AMD AMF)")
    assert _combo_items(tab.speed_preset_combo) == [
        "speed", "balanced", "quality"]
    assert tab.speed_preset_combo.currentText() == "balanced"
    assert tab.nvenc_preset_combo.isEnabled() is False
    assert tab.speed_preset_combo.isEnabled() is True


def test_speed_options_qsv_use_cpu_presets(tab):
    _enter_custom(tab)
    tab.encoder_combo.setCurrentText("H.264 (Intel QSV)")
    assert _combo_items(tab.speed_preset_combo) == list(CPU_PRESETS)
    assert tab.speed_preset_combo.currentText() == "medium"


def test_speed_options_nvenc_use_p_presets(tab):
    _enter_custom(tab)
    tab.encoder_combo.setCurrentText("H.264 (NVIDIA NVENC)")
    assert tab.nvenc_preset_combo.isEnabled() is True
    assert tab.speed_preset_combo.isEnabled() is False


def test_speed_controls_locked_in_preset_mode(tab):
    assert tab.nvenc_preset_combo.isEnabled() is False
    assert tab.speed_preset_combo.isEnabled() is False
    tab.preset_combo.setCurrentText(NVENC_PRESET)
    # 预设模式即使选中 NVENC 也不允许改档位
    assert tab.nvenc_preset_combo.isEnabled() is False
    assert tab.speed_preset_combo.isEnabled() is False


# ----------------------------------------------------------------
# 输出方案硬件卡三态
# ----------------------------------------------------------------

def test_hardware_card_available_state(tab):
    tab.apply_capabilities(_caps())
    card = tab.output_plan_card.cards[3]
    assert card.capability_label.text() == "NVENC 可用"
    assert card.isEnabled() is True

    card.click()
    assert tab.preset_combo.currentText() == NVENC_PRESET


def test_hardware_card_unavailable_state_blocks_click(tab):
    tab.apply_capabilities(NO_HW_CAPS())
    card = tab.output_plan_card.cards[3]
    assert card.capability_label.text() == "NVENC 不可用"
    assert card.isEnabled() is False
    assert card.is_hardware_blocked() is True

    before = tab.preset_combo.currentText()
    card.click()
    assert tab.preset_combo.currentText() == before


def test_hardware_card_pending_state_is_clickable(tab):
    card = tab.output_plan_card.cards[3]
    assert card.capability_label.text() == "待能力检测"
    assert card.isEnabled() is True
    card.click()
    assert tab.preset_combo.currentText() == NVENC_PRESET


def test_hardware_card_probe_error_is_pending(tab):
    tab.apply_capabilities(_caps(encoders=set(), probe_error="boom"))
    card = tab.output_plan_card.cards[3]
    assert card.capability_label.text() == "待能力检测"
    assert card.isEnabled() is True


# ----------------------------------------------------------------
# 主窗口探测回调转发
# ----------------------------------------------------------------

def test_main_window_on_capabilities_ready_forwards_to_encode_tab(win):
    encode_tab = _encode_tab_of(win)
    forwarded = []
    original = encode_tab.apply_capabilities

    def spy(caps):
        forwarded.append(caps)
        original(caps)

    encode_tab.apply_capabilities = spy
    caps = _caps()
    win._on_capabilities_ready(caps)
    assert forwarded == [caps]

    encode_tab.apply_capabilities = spy
    win._on_capabilities_ready(None)
    assert forwarded[-1] is None


def test_main_window_apply_capabilities_normalizes_probe_error(win):
    encode_tab = _encode_tab_of(win)
    forwarded = []
    encode_tab.apply_capabilities = forwarded.append

    bad = _caps(encoders=set(), probe_error="ffmpeg 不可用")
    win._apply_capabilities(bad)
    assert forwarded == [None]

    good = _caps()
    win._apply_capabilities(good)
    assert forwarded == [None, good]


def test_main_window_probing_state_resets_encode_tab(win):
    encode_tab = _encode_tab_of(win)
    forwarded = []
    encode_tab.apply_capabilities = forwarded.append

    win._set_capabilities_probing()
    assert forwarded == [None]


def test_build_args_keys_unchanged_after_capabilities(tab):
    before = set(vars(tab.build_args()))
    tab.apply_capabilities(NO_HW_CAPS())
    tab.preset_combo.setCurrentText("自定义 (Custom)")
    after = set(vars(tab.build_args()))
    assert before == after
