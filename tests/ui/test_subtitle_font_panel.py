from pathlib import Path

import pytest

from src.ui.subtitle_font_panel import SubtitleFontPanel
from src.subtitle_fonts import FontReport,FontIssue
from tests.test_subtitle_render import write_ass
from tests.fixtures.subtitle_compat.font_factory import make_font
import time


def pump_until(app,predicate,timeout=3):
    end=time.monotonic()+timeout
    while not predicate() and time.monotonic()<end:
        app.processEvents();time.sleep(0.005)
    assert predicate()


def test_mac_panel_under_hard_subtitle_and_defaults_off(qapp,monkeypatch,platform_caps_stub):
    import src.ui.tabs.encode_tab as module
    from src.capabilities.ffmpeg_probe import FfmpegCaps
    state=platform_caps_stub();state.os_name='darwin';state.avisynth_available=False
    monkeypatch.setattr(module,'platform_capabilities',lambda *a,**kw:state)
    tab=module.EncodeTab()
    assert not tab.font_panel.isHidden() and not tab.font_panel.options().enabled
    tab.release()


def test_args_summary_and_readiness_use_same_options(qapp,tmp_path):
    panel=SubtitleFontPanel()
    font=make_font(tmp_path/'font.ttf');ass=write_ass(tmp_path/'字幕.ass')
    panel.set_inputs(str(tmp_path/'video.mp4'),str(ass))
    panel.set_available(True)
    panel.setChecked(True)
    panel.add_sources([str(font)])
    panel.check_fonts()
    pump_until(qapp,lambda:panel.report is not None)
    assert panel.report.ready
    assert panel.options().enabled and panel.options().sources==(str(font),)
    panel.require_ready()
    panel.set_inputs(str(tmp_path/'other.mp4'),str(ass))
    with pytest.raises(ValueError,match='检查'):
        panel.require_ready()
    panel.release()


def test_missing_and_explicit_fallback_are_visible(qapp,tmp_path):
    panel=SubtitleFontPanel();ass=write_ass(tmp_path/'字幕.ass')
    panel.set_inputs('video.mp4',str(ass));panel.set_available(True);panel.setChecked(True)
    panel.check_fonts();pump_until(qapp,lambda:panel.report is not None)
    assert not panel.report.ready and '未找到字体' in panel.status.text()
    with pytest.raises(ValueError):panel.require_ready()
    panel.allow_fallback.setChecked(True);panel.require_ready()
    assert panel.options().allow_fallback
    panel.release()


def test_old_input_results_never_replace_current_panel(qapp,tmp_path):
    panel=SubtitleFontPanel();ass=write_ass(tmp_path/'字幕.ass')
    panel.set_inputs('first.mp4',str(ass));old=panel.generation
    panel.set_inputs('second.mp4',str(ass))
    panel.accept_result(old,{'kind':'scan','report':FontReport(ready=True),'faces':()})
    assert panel.report is None
    panel.release()


def test_enabled_args_and_summary_and_embed_clear_enhancement(qapp,tmp_path,monkeypatch,platform_caps_stub):
    from types import SimpleNamespace
    import src.ui.tabs.encode_tab as module
    state=platform_caps_stub(os_name='darwin',avisynth_available=False,
                             ffmpeg_caps=SimpleNamespace(filters={'subtitles'}))
    monkeypatch.setattr(module,'platform_capabilities',lambda *a,**kw:state)
    tab=module.EncodeTab()
    video=tmp_path/'source.mp4';video.write_bytes(b'fake')
    font=make_font(tmp_path/'font.ttf');ass=write_ass(tmp_path/'test.ass')
    tab.input_edit.setText(str(video));tab.subtitle_edit.setText(str(ass))
    tab.font_panel.setChecked(True);tab.font_panel.add_sources([str(font)])
    tab.font_panel.check_fonts();pump_until(qapp,lambda:tab.font_panel.report is not None)
    args=tab.build_args()
    assert args.subtitle_fonts.enabled and '字体兼容增强' in tab.summary_card.row_text('subtitle')
    tab.output_format_combo.setCurrentText('MKV')
    tab.subtitle_mode_combo.setCurrentText('内封（转为软字幕流）')
    assert not hasattr(tab.build_args(),'subtitle_fonts')
    tab.release()


def test_preview_has_enough_height_to_show_subtitle_image(qapp,tmp_path):
    from PIL import Image
    from src.subtitle_render import SubtitlePreview
    path=tmp_path/'frame.png';Image.new('RGB',(2160,1080),'white').save(path)
    panel=SubtitleFontPanel();panel.setChecked(True);panel.resize(800,450);panel.show()
    preview=SubtitlePreview(path,FontReport(ready=True),19_000_000)
    panel.accept_result(panel.generation,{'kind':'preview','preview':preview,'report':preview.report})
    qapp.processEvents()
    assert panel.image.height()>=250
    panel.release();panel.close()
