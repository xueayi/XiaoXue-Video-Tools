from pathlib import Path

import pytest

from src.subtitle_document import FontRequest, analyze_subtitle, rewrite_font_names


FIXTURE = Path(__file__).parent / 'fixtures/subtitle_compat/mixed.ass'


def test_collect_used_styles_and_inline_fonts():
    analysis = analyze_subtitle(FIXTURE)
    assert set(analysis.requests) == {
        FontRequest('Noto Sans SC Medium', 0, False),
        FontRequest('Noto Serif CJK SC Black', 0, False),
        FontRequest('MiSans Medium', 700, True),
    }
    chars = dict(analysis.codepoints)
    assert ord('甲') in chars[FontRequest('MiSans Medium', 700, True)]
    assert ord('乙') in chars[FontRequest('Noto Serif CJK SC Black', 0, False)]
    assert ord('丙') in chars[FontRequest('Noto Sans SC Medium', 0, False)]
    assert ord('m') not in set().union(*chars.values())  # vector drawing is not text


def test_mapping_preserves_animation_and_timing(tmp_path):
    source = tmp_path / '原字幕.ass'
    original = FIXTURE.read_bytes().replace(b'\n', b'\r\n')
    source.write_bytes(original)
    output = tmp_path / 'mapped.ass'
    rewrite_font_names(analyze_subtitle(source), {'Noto Sans SC Medium': 'Other Face',
                                                'MiSans Medium': 'Other Inline'}, output)
    expected = original.replace(b'Noto Sans SC Medium', b'Other Face').replace(b'MiSans Medium', b'Other Inline')
    assert output.read_bytes() == expected
    assert source.read_bytes() == original


def test_empty_mapping_reuses_original(tmp_path):
    output = tmp_path / 'unnecessary.ass'
    assert rewrite_font_names(analyze_subtitle(FIXTURE), {}, output) == FIXTURE
    assert not output.exists()


def test_animated_font_change_is_explicitly_unsupported(tmp_path):
    source = tmp_path / 'animated.ass'
    source.write_text(FIXTURE.read_text().replace(r'\t(0,500,\alpha&H00&)', r'\t(0,500,\fnOther)'))
    with pytest.raises(ValueError, match='字体.*变换|变换.*字体'):
        analyze_subtitle(source)


def test_missing_style_is_not_silently_treated_as_default(tmp_path):
    source = tmp_path / 'missing.ass'
    source.write_text(FIXTURE.read_text().replace(',Main,{', ',Unknown,{'))
    with pytest.raises(ValueError, match='样式'):
        analyze_subtitle(source)


def test_font_request_from_style_bold_is_not_lost(tmp_path):
    source = tmp_path / 'bold.ass'
    source.write_text(FIXTURE.read_text().replace('Main,0,0', 'Main,-1,0'))
    assert FontRequest('Noto Sans SC Medium', -1, False) in analyze_subtitle(source).requests
