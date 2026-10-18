from pathlib import Path
from dataclasses import replace

import pytest

from src.subtitle_document import FontRequest
from src.subtitle_fonts import (FontBinding, FontCheckError, FontReport, SubtitleFontOptions,
                                 scan_font_sources)
from src.subtitle_render import (PreparedSubtitle, FontSelectionCollector, build_subtitle_filter,
                                  prepare_subtitle)
from src.task.context import TaskCancelled, TaskContext, set_current_task, reset_current_task
from tests.fixtures.subtitle_compat.font_factory import make_font


def write_ass(path, name='Demo Medium'):
    path.write_text(f'''[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 180
[V4+ Styles]
Format: Name,Fontname,Fontsize,Bold,Italic,PrimaryColour,Alignment
Style: Default,{name},30,0,0,&H00FFFFFF,2
[Events]
Format: Start,End,Style,Text
Dialogue: 0:00:00.00,0:00:02.00,Default,中文
''', encoding='utf-8')
    return path


def test_direct_fontsdir_does_not_rewrite_ass(tmp_path):
    font = make_font(tmp_path/'font.ttf')
    ass = write_ass(tmp_path/'原字幕.ass')
    before = ass.read_bytes()
    with prepare_subtitle(str(ass), SubtitleFontOptions(True, (str(font),))) as prepared:
        assert Path(prepared.path).read_bytes() == before
        assert prepared.report.ready and not prepared.report.verified
        assert len(list(Path(prepared.fonts_dir).iterdir())) == 1
        directory = Path(prepared.fonts_dir).parent
    assert not directory.exists() and ass.read_bytes() == before


def test_explicit_mapping_changes_only_font_names(tmp_path):
    font = make_font(tmp_path/'font.ttf', 'Other Medium')
    face = scan_font_sources((str(font),), tmp_path/'cache', lambda: False)[0]
    ass = write_ass(tmp_path/'字幕.ass')
    before = ass.read_bytes()
    options = SubtitleFontOptions(True, (str(font),), (FontBinding('Demo Medium', face),))
    with prepare_subtitle(str(ass), options) as prepared:
        assert Path(prepared.path).read_bytes() == before.replace(b'Demo Medium', b'Other Medium')
        assert ass.read_bytes() == before


@pytest.mark.parametrize('exception', [RuntimeError, TaskCancelled])
def test_cleanup_after_success_failure_cancel(tmp_path, exception):
    font = make_font(tmp_path/'font.ttf')
    ass = write_ass(tmp_path/'字幕.ass')
    with pytest.raises(exception):
        with prepare_subtitle(str(ass), SubtitleFontOptions(True, (str(font),))) as prepared:
            directory = Path(prepared.fonts_dir).parent
            raise exception('stop')
    assert not directory.exists()


def test_two_jobs_do_not_share_temp_files(tmp_path):
    font = make_font(tmp_path/'font.ttf')
    ass = write_ass(tmp_path/'字幕.ass')
    options = SubtitleFontOptions(True, (str(font),))
    with prepare_subtitle(str(ass), options) as a, prepare_subtitle(str(ass), options) as b:
        assert a.fonts_dir != b.fonts_dir


def test_font_changed_after_scan_is_rejected(tmp_path):
    font = make_font(tmp_path/'font.ttf')
    face = scan_font_sources((str(font),), tmp_path/'cache', lambda: False)[0]
    make_font(font, 'Changed Medium')
    ass = write_ass(tmp_path/'字幕.ass')
    with pytest.raises(FontCheckError):
        with prepare_subtitle(str(ass), SubtitleFontOptions(True, (str(font),),
                                (FontBinding('Demo Medium', face),))):
            pass


def test_strict_missing_font_and_explicit_fallback(tmp_path):
    ass = write_ass(tmp_path/'字幕.ass')
    with pytest.raises(FontCheckError, match='未找到字体'):
        with prepare_subtitle(str(ass), SubtitleFontOptions(True)):
            pass
    with prepare_subtitle(str(ass), SubtitleFontOptions(True, allow_fallback=True)) as prepared:
        assert prepared.report.issues and not prepared.report.ready


def test_cancelled_context_stops_font_import(tmp_path):
    font = make_font(tmp_path/'font.ttf')
    ass = write_ass(tmp_path/'字幕.ass')
    context = TaskContext(); context.cancel()
    token = set_current_task(context)
    try:
        with pytest.raises(TaskCancelled):
            with prepare_subtitle(str(ass), SubtitleFontOptions(True, (str(font),))):
                pass
    finally:
        reset_current_task(token)


def test_fontselect_failure_cannot_be_reported_as_verified(tmp_path):
    font = make_font(tmp_path/'font.ttf')
    face = scan_font_sources((str(font),), tmp_path/'cache', lambda: False)[0]
    report = FontReport(((FontRequest('Demo Medium'), face),), (), True)
    prepared = PreparedSubtitle('test.ass', 'fonts', report)
    good = FontSelectionCollector(prepared)
    good.feed('[Parsed_subtitles_0] fontselect: (Demo Medium, 400, 0) -> filename,with,commas.ttf, 0, Demo-Medium')
    assert good.report().verified
    wrong = FontSelectionCollector(prepared)
    wrong.feed('[Parsed_subtitles_0] fontselect: (Demo Medium, 400, 0) -> Helvetica, 0, Helvetica')
    assert not wrong.report().verified and wrong.report().issues[0].code == 'fallback'
    unknown = FontSelectionCollector(prepared)
    unknown.feed('[Parsed_subtitles_0] fontselect: unexpected format')
    assert not unknown.report().verified


def test_filter_escapes_chinese_spaces_quote_colon_and_comma(tmp_path, requires_libass):
    import subprocess
    font = make_font(tmp_path/'font.ttf')
    # Colon is illegal in Windows paths; the same escaping is exercised on macOS/Linux.
    name = "中文 O'Brien,字幕.ass"
    ass = write_ass(tmp_path/name)
    faces = scan_font_sources((str(font),), tmp_path/'cache', lambda: False)
    from src.subtitle_document import analyze_subtitle
    from src.subtitle_fonts import resolve_fonts
    report = resolve_fonts(analyze_subtitle(ass), faces)
    prepared = PreparedSubtitle(str(ass), str(tmp_path), report)
    result = subprocess.run([requires_libass, '-v', 'error', '-f', 'lavfi', '-i',
                             'color=s=320x180:d=0.1', '-vf', build_subtitle_filter(prepared),
                             '-frames:v', '1', '-f', 'null', '-'], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
