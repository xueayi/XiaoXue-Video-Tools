from dataclasses import replace
from pathlib import Path
import zipfile

import pytest

from src.subtitle_document import FontRequest, SubtitleAnalysis
from src.subtitle_fonts import (FontBinding, FontCheckError, resolve_fonts, scan_font_sources)
from src.task.context import TaskCancelled
from tests.fixtures.subtitle_compat.font_factory import make_font


def analysis(name, bold=0, text='中文'):
    request = FontRequest(name, bold, False)
    return SubtitleAnalysis(Path('test.ass'), (request,), ((request, frozenset(map(ord, text))),))


def test_full_name_medium_black_keeps_real_weight(tmp_path):
    make_font(tmp_path/'medium.ttf', 'Demo Medium', 500)
    make_font(tmp_path/'black.ttf', 'Demo Black', 900)
    faces = scan_font_sources((str(tmp_path),), tmp_path/'cache', lambda: False)
    for name, weight in [('Demo Medium', 500), ('Demo Black', 900)]:
        report = resolve_fonts(analysis(name), faces)
        assert report.ready and not report.issues
        assert report.matches[0][1].weight == weight


def test_ttc_face_names_and_index(tmp_path):
    from fontTools.ttLib import TTCollection, TTFont
    regular = make_font(tmp_path/'regular.ttf', 'Collection Regular', 400)
    heavy = make_font(tmp_path/'heavy.ttf', 'Collection Heavy', 900)
    collection = TTCollection()
    collection.fonts = [TTFont(regular), TTFont(heavy)]
    collection.save(tmp_path/'fonts.ttc')
    for f in collection.fonts: f.close()
    faces = scan_font_sources((str(tmp_path/'fonts.ttc'),), tmp_path/'cache', lambda: False)
    assert [(f.index, f.weight) for f in faces] == [(0, 400), (1, 900)]
    assert resolve_fonts(analysis('Collection Heavy'), faces).matches[0][1].index == 1


def test_duplicate_full_name_requires_choice(tmp_path):
    a = make_font(tmp_path/'a.ttf', 'Duplicate', 500, characters='中文')
    make_font(tmp_path/'b.ttf', 'Duplicate', 500, characters='中文甲')
    faces = scan_font_sources((str(tmp_path),), tmp_path/'cache', lambda: False)
    report = resolve_fonts(analysis('Duplicate'), faces)
    assert not report.ready and report.issues[0].code == 'ambiguous'
    selected = next(f for f in faces if f.path == a)
    assert resolve_fonts(analysis('Duplicate'), faces, (FontBinding('Duplicate', selected),)).ready


def test_import_zip_skips_appledouble_and_never_writes_source(tmp_path):
    font = make_font(tmp_path/'font.ttf')
    archive = tmp_path/'字体.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.write(font, 'nested/font.ttf')
        z.writestr('__MACOSX/._font.ttf', b'not a font')
        z.writestr('../escape.ttf', font.read_bytes())
    original = archive.read_bytes()
    faces = scan_font_sources((str(archive),), tmp_path/'cache', lambda: False)
    assert len(faces) == 1 and faces[0].weight == 500
    assert '字体.zip' in faces[0].source and 'nested/font.ttf' in faces[0].source
    assert faces[0].path.is_relative_to(tmp_path/'cache')
    assert archive.read_bytes() == original and not (tmp_path.parent/'escape.ttf').exists()


def test_disconnected_source_cancel_and_invalid_font(tmp_path):
    make_font(tmp_path/'good.ttf')
    (tmp_path/'broken.ttf').write_bytes(b'bad font')
    assert len(scan_font_sources((str(tmp_path),), tmp_path/'cache', lambda: False)) == 1
    with pytest.raises(FontCheckError, match='字体来源'):
        scan_font_sources((str(tmp_path/'offline'),), tmp_path/'cache', lambda: False)
    with pytest.raises(TaskCancelled):
        scan_font_sources((str(tmp_path),), tmp_path/'cache', lambda: True)


def test_missing_glyph_and_variable_are_not_reported_as_ready(tmp_path):
    make_font(tmp_path/'latin.ttf', 'Latin', 400, characters='ABC')
    faces = scan_font_sources((str(tmp_path/'latin.ttf'),), tmp_path/'cache', lambda: False)
    assert resolve_fonts(analysis('Latin'), faces).issues[0].code == 'missing_glyph'
    assert resolve_fonts(analysis('Absent'), faces).issues[0].code == 'missing'
    variable = (replace(faces[0], variable=True),)
    assert resolve_fonts(analysis('Latin', text='A'), variable).issues[0].code == 'unsupported'


def test_misans_is_only_selected_when_user_maps_it(tmp_path):
    make_font(tmp_path/'mi.ttf', 'MiSans Medium', 500)
    faces = scan_font_sources((str(tmp_path/'mi.ttf'),), tmp_path/'cache', lambda: False)
    assert not resolve_fonts(analysis('Noto Sans SC Medium'), faces).ready
    report = resolve_fonts(analysis('Noto Sans SC Medium'), faces,
                           (FontBinding('Noto Sans SC Medium', faces[0]),))
    assert report.ready and report.matches[0][1].postscript_name == 'MiSans-Medium'


def test_explicit_binding_must_still_belong_to_current_sources(tmp_path):
    font = make_font(tmp_path/'font.ttf')
    faces = scan_font_sources((str(font),), tmp_path/'cache', lambda: False)
    report = resolve_fonts(analysis('Old Name'), (), (FontBinding('Old Name', faces[0]),))
    assert not report.ready
    assert report.issues[0].code == 'source_unavailable'
    assert not report.matches
