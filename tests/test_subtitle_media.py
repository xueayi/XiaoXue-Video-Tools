from pathlib import Path
import os
import subprocess

import pytest

from src.core import build_encode_command,build_2pass_commands,run_2pass_encode
from src.clip_plan import ClipPlan,ClipSpec
from src.subtitle_fonts import SubtitleFontOptions,FontCheckError
from src.subtitle_render import prepare_subtitle,render_subtitle_preview
from tests.fixtures.subtitle_compat.font_factory import make_font
from tests.test_subtitle_render import write_ass


def test_real_font_match_and_snapshot_equal_lossless_export(tmp_path,requires_libass,monkeypatch):
    from PIL import Image,ImageChops
    ff=requires_libass
    monkeypatch.setattr('src.subtitle_render.get_ffmpeg_path',lambda:ff)
    monkeypatch.setattr('src.core.get_ffmpeg_path',lambda:ff)
    video=tmp_path/'input.mkv'
    subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=black:s=320x180:r=24:d=2',
                     '-c:v','ffv1',str(video)],capture_output=True,check=True,timeout=20)
    font=make_font(tmp_path/'font.ttf');ass=write_ass(tmp_path/'test.ass')
    with pytest.raises(FontCheckError):
        with prepare_subtitle(str(ass),SubtitleFontOptions(True)):pass
    with prepare_subtitle(str(ass),SubtitleFontOptions(True,(str(font),))) as prepared:
        snapshot=render_subtitle_preview(str(video),1_000_000,prepared,tmp_path/'snapshot.png')
        assert snapshot.report.verified and len(snapshot.report.observed)==1
        from src.subtitle_render import build_subtitle_filter
        output=tmp_path/'render.mkv'
        subprocess.run([ff,'-v','error','-y','-i',str(video),'-vf',build_subtitle_filter(prepared),
                         '-c:v','ffv1',str(output)],capture_output=True,check=True,timeout=20)
        frame=tmp_path/'frame.png'
        subprocess.run([ff,'-v','error','-y','-ss','1','-i',str(output),'-frames:v','1',str(frame)],
                        capture_output=True,check=True,timeout=20)
        assert ImageChops.difference(Image.open(snapshot.path).convert('RGB'),Image.open(frame).convert('RGB')).getbbox() is None


def test_external_corpus_is_valid_when_explicitly_configured():
    root=os.environ.get('XIAOXUE_SUBTITLE_TEST_ROOT')
    if not root:pytest.skip('未配置外部字幕素材')
    path=Path(root)
    assert (path/'262_缩混.mp4').is_file() and (path/'262_缩混.ass').is_file()
    from src.subtitle_document import analyze_subtitle
    from src.subtitle_fonts import scan_font_sources,resolve_fonts
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as cache:
        faces=scan_font_sources((str(path/'字体整理/原字幕字体'),),Path(cache),lambda:False)
        result=resolve_fonts(analyze_subtitle(path/'262_缩混.ass'),faces)
    assert result.ready
    assert {f.weight for _,f in result.matches}=={500,900}


def test_shifted_test_subtitle_keeps_relative_animation(tmp_path):
    from tools.validate_subtitle_compat import shift_test_subtitle
    source=write_ass(tmp_path/'original.ass')
    source.write_text(source.read_text(encoding='utf-8').replace(
        '0:00:00.00,0:00:02.00', '0:00:17.77,0:00:23.64').replace(
        '中文', r'{\t(0,50,\alpha&H00&)}中文'), encoding='utf-8')
    before=source.read_bytes()
    output=tmp_path/'shifted.ass';shift_test_subtitle(source,output,16)
    assert '0:00:01.77,0:00:07.64' in output.read_text(encoding='utf-8')
    assert r'\t(0,50,\alpha&H00&)' in output.read_text(encoding='utf-8')
    assert source.read_bytes()==before


def test_two_fonts_and_reordered_clips_keep_source_subtitle_frame(tmp_path, requires_libass, monkeypatch):
    from PIL import Image, ImageChops
    from src.subtitle_render import FontSelectionCollector
    ff = requires_libass
    monkeypatch.setattr('src.subtitle_render.get_ffmpeg_path', lambda: ff)
    monkeypatch.setattr('src.core.get_ffmpeg_path', lambda: ff)
    video = tmp_path/'input.mkv'
    subprocess.run([ff, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'color=black:s=320x180:r=24:d=2', '-c:v', 'ffv1', str(video)],
                   capture_output=True, check=True, timeout=20)
    medium = make_font(tmp_path/'medium.ttf')
    black = make_font(tmp_path/'black.ttf', 'Demo Black', 900)
    ass = write_ass(tmp_path/'test.ass')
    ass.write_text(ass.read_text(encoding='utf-8').replace(
        '[Events]', 'Style: Title,Demo Black,30,0,0,&H000000FF,8\n[Events]') +
        r'Dialogue: 0:00:01.00,0:00:02.00,Title,{\fad(1000,0)}标题' + '\n',
        encoding='utf-8')
    with prepare_subtitle(str(ass), SubtitleFontOptions(True, (str(medium), str(black)))) as prepared:
        snapshot = render_subtitle_preview(str(video), 1_500_000, prepared, tmp_path/'source.png')
        assert snapshot.report.verified
        assert {f.weight for _, f in snapshot.report.matches} == {500, 900}
        output = tmp_path/'reordered.mkv'
        plan = ClipPlan(str(video), (ClipSpec(1_000_000, 2_000_000), ClipSpec(0, 1_000_000)))
        command = build_encode_command(str(video), str(output), encoder='libx264', crf=0,
                                       subtitle_path=str(ass), subtitle_render=prepared,
                                       clip_plan=plan, clip_video_only=True)
        command[command.index('-c:v')+1] = 'ffv1'
        encoded = subprocess.run(command, capture_output=True, check=True, timeout=20)
        collector = FontSelectionCollector(prepared)
        for line in encoded.stderr.decode(errors='replace').splitlines():
            collector.feed(line)
        assert collector.report().verified
        frame = tmp_path/'frame.png'
        subprocess.run([ff, '-v', 'error', '-y', '-ss', '0.5', '-i', str(output),
                        '-frames:v', '1', str(frame)], capture_output=True, check=True, timeout=20)
        # 标题淡入按原片 1.5 秒渲染；重排后不能在片段起点重新计时。
        assert ImageChops.difference(Image.open(snapshot.path).convert('RGB'),
                                    Image.open(frame).convert('RGB')).getbbox() is None
