"""片段区间、编码映射与任务契约。"""
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest


def plan(path="source.mp4"):
    from src.clip_plan import ClipPlan, ClipSpec
    return ClipPlan(path, (ClipSpec(1_000_000, 1_500_000), ClipSpec(0, 500_000)))


def test_plan_preserves_order_and_is_immutable():
    p = plan()
    assert p.total_duration_us == 1_000_000
    assert p.clips[0].in_us == 1_000_000
    with pytest.raises(FrozenInstanceError):
        p.clips = ()


@pytest.mark.parametrize("bounds", [(-1, 50), (50, 50), (60, 50), (0, 101)])
def test_invalid_interval_is_rejected(bounds):
    from src.clip_plan import ClipPlan, ClipSpec
    with pytest.raises(ValueError):
        ClipPlan("source.mp4", (ClipSpec(*bounds),)).validate(100)


def test_enabled_empty_list_is_rejected():
    from src.clip_plan import ClipPlan
    with pytest.raises(ValueError, match="片段"):
        ClipPlan("source.mp4", ()).validate(100)


def test_clip_filter_maps_selected_audio_and_reencodes_copy():
    from src.core import build_encode_command
    cmd = build_encode_command("source.mp4", "out.mkv", clip_plan=plan(),
                               clip_audio_indices=(0, 2), audio_encoder="copy")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.index("trim=start=1.000000:end=1.500000") < graph.index("trim=start=0.000000:end=0.500000")
    assert "[0:a:2]" in graph and "apad" in graph
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert "0:a?" not in cmd and "-vf" not in cmd
    assert "[clip_v]" in cmd and "[clip_a1]" in cmd


def test_no_audio_does_not_generate_unconnected_audio_filters():
    from src.core import build_encode_command
    cmd = build_encode_command("source.mp4", "out.mp4", clip_plan=plan(), clip_audio_indices=())
    assert "-an" in cmd
    assert "atrim" not in cmd[cmd.index("-filter_complex") + 1]


def test_hard_subtitles_are_rendered_before_segment_reordering():
    from src.core import build_encode_command
    cmd = build_encode_command("source.mp4", "out.mp4", clip_plan=plan(),
                               clip_audio_indices=(), subtitle_path="字幕.srt", resolution="320x180")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.index("subtitles=") < graph.index("trim=")
    assert "scale=320:180" in graph


def test_two_pass_first_pass_has_video_only_but_same_video_intervals():
    from src.core import build_2pass_commands
    first, second = build_2pass_commands("source.mp4", "out.mp4", clip_plan=plan(),
                                        clip_audio_indices=(0,), bitrate="300k")
    g1, g2 = (cmd[cmd.index("-filter_complex") + 1] for cmd in (first, second))
    assert "atrim" not in g1 and "atrim" in g2
    assert "trim=start=1.000000:end=1.500000" in g1
    assert "trim=start=1.000000:end=1.500000" in g2
    assert first[first.index("-pass") + 1] == "1"
    assert second[second.index("-pass") + 1] == "2"


@pytest.mark.parametrize("extra", ["-ss 1", "-to 2", "-t 2", "-vf hflip", "-filter:v:0 hflip", "-map 0", "-af volume=2", "-c:a copy", "-i other.mp4", "-copyts", "-r 60"])
def test_conflicting_extra_arguments_rejected(extra):
    from src.encode_params import EncodeParams
    p = EncodeParams(__file__, "out.mp4", clip_plan=plan(__file__), extra_args=extra)
    ok, message = p.validate()
    assert not ok and "参数" in message


@pytest.mark.parametrize("kwargs", [{"subtitle_tracks": "all"}, {"compat_mode": True}])
def test_unsupported_combinations_are_explained(kwargs):
    from src.encode_params import EncodeParams
    ok, message = EncodeParams(__file__, "out.mkv", clip_plan=plan(__file__), **kwargs).validate()
    assert not ok and "片段" in message


def test_resolver_converts_copy_and_keeps_snapshot(base_args):
    from src.encode_params import resolve_encoder_params
    from src.presets import ALL_QUALITY_PRESETS, ENCODERS, AUDIO_ENCODERS, RATE_CONTROL_MODES
    from src.utils import generate_output_path
    base_args.clip_plan = plan(base_args.input)
    params = resolve_encoder_params(base_args, ALL_QUALITY_PRESETS, ENCODERS, AUDIO_ENCODERS,
                                    RATE_CONTROL_MODES, generate_output_path)
    assert params.clip_plan is base_args.clip_plan
    assert params.audio_encoder == "aac"


def test_progress_uses_selected_duration_without_full_source_probe():
    from src.ui.task_runner import TaskRunner
    runner = TaskRunner(lambda _: 0, SimpleNamespace(input=__file__, clip_plan=plan(__file__)),
                        "视频压制", duration_probe=lambda _: 300)
    assert runner._probe_duration() == 1.0


def test_executor_rejects_out_of_bounds_before_running(base_args, monkeypatch):
    from src.executors import video_executor as ve
    from src.media_probe import DetailedMediaInfo, StreamInfo
    base_args.clip_plan = plan(base_args.input)
    monkeypatch.setattr(ve, "probe_detailed", lambda _: DetailedMediaInfo(
        base_args.input, duration_sec=1, video_streams=[StreamInfo(0, 0, "video", fps=24)]))
    monkeypatch.setattr(ve, "run_ffmpeg_command", lambda *a, **k: pytest.fail("越界不应执行"))
    result = ve.execute_encode(base_args)
    assert not result.is_ok
    assert "片段" in result.message
