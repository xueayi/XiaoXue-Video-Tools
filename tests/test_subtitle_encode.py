from dataclasses import replace
from pathlib import Path

import pytest

from src.core import build_encode_command, build_2pass_commands
from src.encode_params import EncodeParams, EncodeMode
from src.clip_plan import ClipPlan, ClipSpec
from src.subtitle_fonts import FontReport, SubtitleFontOptions
from src.subtitle_render import PreparedSubtitle


@pytest.fixture
def prepared():
    return PreparedSubtitle('/tmp/prepared.ass', '/tmp/prepared-fonts', FontReport())


def test_disabled_keeps_existing_commands():
    normal = build_encode_command('in.mp4', 'out.mp4', subtitle_path='test.ass')
    assert normal == build_encode_command('in.mp4', 'out.mp4', subtitle_path='test.ass', subtitle_render=None)


def test_enhancement_does_not_select_avisynth_mode():
    params = EncodeParams('a.mp4', 'out.mp4', subtitle_path='a.ass',
                          subtitle_fonts=SubtitleFontOptions(True), is_custom=True,
                          rc_mode='2pass', bitrate='2M')
    assert params.get_encode_mode() == EncodeMode.TWO_PASS


def test_apple_and_cpu_use_same_subtitle_filter(prepared):
    commands = [build_encode_command('in.mp4', 'out.mp4', encoder=encoder, crf=quality,
                                     subtitle_path='original.ass', subtitle_render=prepared)
                for encoder, quality in [('libx264', 18), ('h264_videotoolbox', 65)]]
    filters = [c[c.index('-vf')+1] for c in commands]
    assert filters[0] == filters[1]
    assert 'prepared.ass' in filters[0] and 'fontsdir=' in filters[0]
    assert '-q:v' in commands[1] and '-crf' not in commands[1]


def test_both_passes_reuse_prepared_subtitle(prepared):
    first, second = build_2pass_commands('in.mp4', 'out.mp4', subtitle_path='original.ass',
                                        subtitle_render=prepared)
    assert first[first.index('-vf')+1] == second[second.index('-vf')+1]
    assert 'prepared-fonts' in first[first.index('-vf')+1]


def test_clips_render_before_trim_and_keep_source_time(prepared):
    plan = ClipPlan('in.mp4', (ClipSpec(5_000_000, 6_000_000), ClipSpec(1_000_000, 2_000_000)))
    for command in build_2pass_commands('in.mp4', 'out.mp4', subtitle_path='original.ass',
                                        subtitle_render=prepared, clip_plan=plan):
        graph = command[command.index('-filter_complex')+1]
        assert graph.index('subtitles=') < graph.index('trim=')
        assert 'trim=start=5.000000:end=6.000000' in graph and 'prepared-fonts' in graph


@pytest.mark.parametrize('change', [dict(subtitle_path=None),dict(subtitle_mode='embed'),
                                    dict(subtitle_path='a.srt'),dict(compat_mode=True),dict(encoder='copy')])
def test_unsupported_font_enhancement_combinations_are_rejected(tmp_path, change):
    video=tmp_path/'a.mp4'; video.write_bytes(b'video')
    ass=tmp_path/'a.ass'; ass.write_text('ass')
    srt=tmp_path/'a.srt'; srt.write_text('srt')
    values=dict(input_path=str(video),output_path=str(tmp_path/'out.mkv'),
                subtitle_path=str(ass),subtitle_fonts=SubtitleFontOptions(True))
    if change.get('subtitle_path') == 'a.srt': change={'subtitle_path':str(srt)}
    values.update(change)
    assert not EncodeParams(**values).validate()[0]


def test_runtime_font_mismatch_prevents_post_transfer(tmp_path,monkeypatch):
    import src.executors.video_executor as ve
    from tests.test_encode_task_result import make_args
    from tests.test_subtitle_render import write_ass
    from tests.fixtures.subtitle_compat.font_factory import make_font
    font=make_font(tmp_path/'font.ttf')
    ass=write_ass(tmp_path/'test.ass')
    args=make_args(tmp_path,subtitle=str(ass),output=str(tmp_path/'out.mp4'),
                   subtitle_fonts=SubtitleFontOptions(True,(str(font),)))
    def run(command,**kwargs):
        Path(args.output).write_bytes(b'partial output')
        kwargs['on_log']('fontselect: (Demo Medium, 400, 0) -> Helvetica, 0, Helvetica')
        return 0
    monkeypatch.setattr(ve,'run_ffmpeg_command',run)
    transfers=[]
    monkeypatch.setattr(ve,'_post_transfer',lambda *a:transfers.append(a) or [])
    result=ve.execute_encode(args)
    assert not result.is_ok and result.details['reason']=='subtitle_fonts'
    assert result.outputs==(args.output,) and not transfers
