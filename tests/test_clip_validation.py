"""审查发现的非零时间轴与空片段回归。"""
import subprocess
import pytest
from src.clip_plan import ClipPlan, ClipSpec


@pytest.mark.parametrize("format_name,start,duration,stream,want", [
    ("matroska,webm", "10", "13", {"start_time": "10", "tags": {"DURATION": "00:00:13.000000000"}}, 3.0),
    ("mov,mp4,m4a,3gp,3g2,mj2", "10", "13", {"start_time": "10", "duration": "3"}, 3.0),
    ("mpegts", "1.4", "3", {"start_time": "1.4", "duration": "3"}, 3.0),
])
def test_clip_boundary_uses_video_timeline_not_container_end(format_name, start, duration, stream, want):
    from src.media_probe import _parse_detailed_output
    info = _parse_detailed_output("source", {"format": {"format_name": format_name,
        "start_time": start, "duration": duration}, "streams": [{"codec_type": "video", **stream}]})
    assert info.clip_duration_sec == want


@pytest.mark.parametrize("mixed", [False, True])
def test_every_segment_must_contain_a_video_frame(tmp_path, media_binaries, base_args, monkeypatch, mixed):
    from src.executors.video_executor import execute_encode
    ffmpeg, ffprobe = media_binaries
    monkeypatch.setenv("XIAOXUE_FFMPEG", ffmpeg)
    monkeypatch.setenv("XIAOXUE_FFPROBE", ffprobe)
    source = tmp_path / "source.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=s=160x90:r=24:d=3", "-c:v", "libx264", str(source)], check=True)
    clips = (ClipSpec(1_000, 2_000),) + ((ClipSpec(1_000_000, 2_000_000),) if mixed else ())
    base_args.input = str(source)
    base_args.output = str(tmp_path / "output.mp4")
    base_args.debug_mode = False
    base_args.clip_plan = ClipPlan(str(source), clips)
    result = execute_encode(base_args)
    assert not result.is_ok
    assert "片段 1" in result.message
    assert not (tmp_path / "output.mp4").exists()


def test_source_timestamp_offset_rejects_phantom_tail(tmp_path, media_binaries, base_args, monkeypatch):
    from src.executors.video_executor import execute_encode
    ffmpeg, ffprobe = media_binaries
    monkeypatch.setenv("XIAOXUE_FFMPEG", ffmpeg)
    monkeypatch.setenv("XIAOXUE_FFPROBE", ffprobe)
    source = tmp_path / "offset.mkv"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=s=160x90:r=24:d=3", "-c:v", "libx264",
                    "-output_ts_offset", "10", str(source)], check=True)
    base_args.input = str(source)
    base_args.output = str(tmp_path / "output.mp4")
    base_args.clip_plan = ClipPlan(str(source), (ClipSpec(11_000_000, 12_000_000),))
    result = execute_encode(base_args)
    assert not result.is_ok
    assert "片段 1" in result.message


def test_valid_segment_on_offset_source_exports(tmp_path, media_binaries, base_args, monkeypatch):
    from src.executors.video_executor import execute_encode
    ffmpeg, ffprobe = media_binaries
    monkeypatch.setenv("XIAOXUE_FFMPEG", ffmpeg)
    monkeypatch.setenv("XIAOXUE_FFPROBE", ffprobe)
    source = tmp_path / "offset.mkv"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=s=160x90:r=24:d=3", "-c:v", "libx264",
                    "-output_ts_offset", "10", str(source)], check=True)
    base_args.input = str(source)
    base_args.output = str(tmp_path / "output.mp4")
    base_args.debug_mode = False
    base_args.clip_plan = ClipPlan(str(source), (ClipSpec(1_000_000, 2_000_000),))
    result = execute_encode(base_args)
    assert result.is_ok, result.message
