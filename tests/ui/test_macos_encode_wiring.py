"""实际控件、摘要与后端共用 Apple 编码器参数。"""
import pytest
from src.capabilities.ffmpeg_probe import FfmpegCaps
from src.platform import capabilities as platform_caps
from src.ui.tabs.encode_tab import EncodeTab


@pytest.fixture
def apple_tab(qapp, monkeypatch):
    monkeypatch.setattr(platform_caps, 'detect', lambda: platform_caps.PlatformCapabilities(os_name='darwin'))
    platform_caps.reset_platform_capabilities()
    tab = EncodeTab()
    tab.apply_capabilities(FfmpegCaps(ffmpeg_path='ffmpeg', encoders=frozenset({
        'libx264', 'libx265', 'h264_videotoolbox', 'hevc_videotoolbox'})))
    yield tab
    tab.close()
    platform_caps.reset_platform_capabilities()


def test_apple_selection_reaches_summary_and_survives_refresh(apple_tab, tmp_path):
    tab = apple_tab
    assert tab.encoder_combo.findText('H.264 (Apple VideoToolbox)') >= 0
    tab.preset_combo.setCurrentText('自定义 (Custom)')
    tab.encoder_combo.setCurrentText('H.264 (Apple VideoToolbox)')
    tab.crf_spin.setValue(65)
    assert tab.crf_spin.maximum() == 100
    assert tab.speed_preset_combo.currentText() == 'auto'
    source = tmp_path / '输入.mp4'
    source.write_bytes(b'x')
    tab.input_edit.setText(str(source))
    tab._refresh_summary()
    assert tab.summary_card.last_params.encoder == 'h264_videotoolbox'
    assert tab.summary_card.last_params.crf == 65
    tab.apply_capabilities(tab._caps)
    assert tab.encoder_combo.currentText() == 'H.264 (Apple VideoToolbox)'
    tab.apply_capabilities(FfmpegCaps(ffmpeg_path='ffmpeg', encoders=frozenset({'libx264'})))
    assert tab.encoder_combo.currentText() == 'H.264 (CPU - libx264)'
    assert tab.crf_spin.maximum() == 51


def test_hardware_card_selects_apple_preset(apple_tab):
    card = apple_tab.output_plan_card.cards[3]
    assert 'videotoolbox' in card.badge_label.text()
    assert 'Apple' in card.capability_label.text()
    apple_tab.output_plan_card._on_card_clicked(card.preset_name)
    assert apple_tab.encoder_combo.currentText() == 'H.264 (Apple VideoToolbox)'
    assert apple_tab.crf_spin.value() == 65
