from pathlib import Path
import subprocess

import pytest

from src.subtitle_fonts import SubtitleFontOptions
from src.subtitle_render import prepare_subtitle, render_subtitle_preview
from tests.test_subtitle_render import write_ass
from tests.fixtures.subtitle_compat.font_factory import make_font


@pytest.mark.parametrize('start', [0,5])
def test_preview_at_nonzero_time_keeps_ass_clock(tmp_path,requires_libass,monkeypatch,start):
    ffmpeg=requires_libass
    monkeypatch.setattr('src.subtitle_render.get_ffmpeg_path',lambda:ffmpeg)
    video=tmp_path/'source.mkv'
    command=[ffmpeg,'-v','error','-y','-f','lavfi','-i','color=black:s=320x180:r=24:d=2',
             '-vf',f'setpts=PTS+{start}/TB','-c:v','ffv1',str(video)]
    subprocess.run(command,check=True,capture_output=True,timeout=20)
    ass=write_ass(tmp_path/'test.ass')
    ass.write_text(ass.read_text(encoding='utf-8').replace('0:00:00.00,0:00:02.00','0:00:01.00,0:00:02.00'),
                   encoding='utf-8')
    font=make_font(tmp_path/'font.ttf')
    with prepare_subtitle(str(ass),SubtitleFontOptions(True,(str(font),))) as prepared:
        before=render_subtitle_preview(str(video),500_000,prepared,tmp_path/'before.png')
        after=render_subtitle_preview(str(video),1_250_000,prepared,tmp_path/'after.png')
    from PIL import Image
    assert Image.open(before.path).convert('RGB').getextrema()==((0,0),(0,0),(0,0))
    assert max(Image.open(after.path).convert('RGB').getextrema()[0])>100
    assert after.report.verified
    assert abs(after.actual_us-1_250_000)<1
