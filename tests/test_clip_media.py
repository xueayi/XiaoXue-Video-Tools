"""真实FFmpeg验证：顺序、音轨、字幕和两遍。"""
import json
import subprocess

import pytest
from src.clip_plan import ClipPlan, ClipSpec
from src.core import build_encode_command, build_2pass_commands, run_2pass_encode


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stderr.decode(errors="replace")[-4000:]
    return result.stdout


@pytest.fixture
def media(tmp_path, media_binaries, monkeypatch):
    ffmpeg, ffprobe = media_binaries
    monkeypatch.setattr("src.core.get_ffmpeg_path", lambda: ffmpeg)
    source = tmp_path / "原片 空格.mkv"
    run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=320x180:r=24:d=1",
         "-f", "lavfi", "-i", "color=blue:s=320x180:r=24:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
         "-f", "lavfi", "-i", "sine=frequency=880:duration=2",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-map", "2:a", "-map", "3:a",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "pcm_s16le",
         "-metadata:s:a:0", "language=chi", "-metadata:s:a:1", "language=jpn", str(source)])
    return source, ffmpeg, ffprobe


def probe(path, ffprobe):
    return json.loads(run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]))


def frame(path, ffmpeg, seconds):
    return run([ffmpeg, "-v", "error", "-ss", str(seconds), "-i", str(path),
                "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])


def test_reordered_repeated_clips_preserve_multitrack_and_source(media, tmp_path):
    source, ffmpeg, ffprobe = media
    original = source.read_bytes()
    output = tmp_path / "重排.mkv"
    plan = ClipPlan(str(source), (ClipSpec(1_000_000, 1_500_000), ClipSpec(0, 500_000), ClipSpec(0, 500_000)))
    run(build_encode_command(str(source), str(output), clip_plan=plan, clip_audio_indices=(0, 1),
                             audio_encoder="copy", speed_preset="ultrafast"))
    info = probe(output, ffprobe)
    assert abs(float(info["format"]["duration"]) - 1.5) < 0.06
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    assert [s["tags"]["language"] for s in audio] == ["chi", "jpn"]
    assert all(s["codec_name"] == "aac" for s in audio)
    first, last = frame(output, ffmpeg, 0.1), frame(output, ffmpeg, 1.1)
    assert sum(first[2::3]) > sum(first[0::3]) * 5
    assert sum(last[0::3]) > sum(last[2::3]) * 5
    assert source.read_bytes() == original


def test_no_audio_and_two_pass_have_expected_frames(media, tmp_path):
    source, ffmpeg, ffprobe = media
    output = tmp_path / "两遍.mp4"
    plan = ClipPlan(str(source), (ClipSpec(250_000, 750_000), ClipSpec(1_000_000, 1_500_000)))
    first, second = build_2pass_commands(str(source), str(output), clip_plan=plan,
                                         clip_audio_indices=(), bitrate="300k", speed_preset="ultrafast")
    assert run_2pass_encode(first, second) == 0
    streams = probe(output, ffprobe)["streams"]
    assert len(streams) == 1
    assert int(streams[0]["nb_frames"]) == 24
    assert abs(float(streams[0]["duration"]) - 1) < 0.01


def test_hard_subtitle_follows_source_time(media, tmp_path):
    source, ffmpeg, _ = media
    subtitle = tmp_path / "字幕.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,500\nHELLO\n", encoding="utf-8")
    output = tmp_path / "字幕.mp4"
    plan = ClipPlan(str(source), (ClipSpec(1_000_000, 1_500_000), ClipSpec(0, 500_000)))
    run(build_encode_command(str(source), str(output), clip_plan=plan, clip_audio_indices=(),
                             subtitle_path=str(subtitle), speed_preset="ultrafast"))
    def whites(data):
        return sum(min(data[i:i + 3]) > 180 for i in range(0, len(data), 3))
    assert whites(frame(output, ffmpeg, 0.25)) == 0
    assert whites(frame(output, ffmpeg, 0.75)) > 20


def test_many_non_frame_aligned_clips_do_not_accumulate_audio_drift(media, tmp_path):
    source, ffmpeg, ffprobe = media
    output = tmp_path / "边界.mp4"
    plan = ClipPlan(str(source), (ClipSpec(10_000, 90_000),) * 24)
    run(build_encode_command(str(source), str(output), clip_plan=plan, clip_audio_indices=(1,),
                             speed_preset="ultrafast"))
    streams = probe(output, ffprobe)["streams"]
    durations = [float(s["duration"]) for s in streams]
    assert abs(durations[0] - durations[1]) <= 1 / 24 + 0.005


def test_non_aligned_two_pass_uses_identical_video_timeline(media, tmp_path):
    source, ffmpeg, ffprobe = media
    output = tmp_path / "边界两遍.mp4"
    plan = ClipPlan(str(source), (ClipSpec(10_000, 110_000),) * 12)
    first, second = build_2pass_commands(str(source), str(output), clip_plan=plan,
                                         clip_audio_indices=(1,), bitrate="300k", speed_preset="ultrafast")
    assert run_2pass_encode(first, second) == 0
    streams = probe(output, ffprobe)["streams"]
    assert abs(float(streams[0]["duration"]) - float(streams[1]["duration"])) < 0.05
