import json
import subprocess

from tests.test_subtitle_render import write_ass
from tests.fixtures.subtitle_compat.font_factory import make_font


def test_font_diagnostics_exercises_ui_scan_snapshot_and_cleanup(qapp,tmp_path,requires_libass,monkeypatch):
    from src.subtitle_diagnostics import run_font_diagnostics
    ff=requires_libass
    monkeypatch.setenv('XIAOXUE_FFMPEG',ff)
    video=tmp_path/'input.mkv'
    subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','color=black:s=320x180:r=24:d=2',
                     '-c:v','ffv1',str(video)],capture_output=True,check=True,timeout=20)
    ass=write_ass(tmp_path/'字幕.ass');font=make_font(tmp_path/'font.ttf')
    report=tmp_path/'report.json'
    assert run_font_diagnostics(str(video),str(ass),(str(font),),str(report),1_000_000)==0
    data=json.loads(report.read_text(encoding='utf-8'))
    assert data['ok'] and data['font_report']['verified']
    assert (tmp_path/'report.png').is_file()
