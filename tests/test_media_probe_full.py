# -*- coding: utf-8 -*-
"""media_probe.py 覆盖测试 (mock ffprobe subprocess)。"""

import json

import pytest

import src.media_probe as mp
from src.media_probe import (
    DetailedMediaInfo, StreamInfo, _format_duration, _format_file_size,
    _get_language_display, format_media_report, generate_media_report,
    probe_detailed,
)


FFPROBE_JSON = {
    "format": {
        "format_name": "mov,mp4,m4a",
        "format_long_name": "QuickTime/MPEG-4",
        "duration": "61.5",
        "bit_rate": "2000000",
    },
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264",
         "codec_long_name": "H.264", "profile": "High", "level": 41,
         "width": 1920, "height": 1080, "pix_fmt": "yuv420p",
         "r_frame_rate": "30000/1001", "bit_rate": "1800000",
         "tags": {"language": "und"}},
        {"index": 1, "codec_type": "audio", "codec_name": "aac",
         "sample_rate": "48000", "channels": 2,
         "channel_layout": "stereo", "bit_rate": "192000",
         "tags": {"language": "jpn", "title": "主音轨"}},
        {"index": 2, "codec_type": "subtitle", "codec_name": "ass",
         "tags": {"language": "chi", "title": "字幕"}},
        {"index": 3, "codec_type": "attachment", "codec_name": "ttf"},
    ],
    "chapters": [{"id": 0, "start_time": 0.0, "end_time": 30.0,
                  "tags": {"title": "开头"}}],
}


@pytest.fixture
def ffprobe_ok(monkeypatch):
    class R:
        returncode = 0
        stdout = json.dumps(FFPROBE_JSON)
        stderr = ""
    monkeypatch.setattr(mp.subprocess, "run", lambda *a, **k: R())


def test_probe_detailed_success(ffprobe_ok, tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x" * 2048)
    info = probe_detailed(str(f))
    assert info.errors == []
    assert info.format_name == "mov,mp4,m4a"
    assert info.duration_sec == 61.5
    assert info.total_bitrate_kbps == 2000
    assert len(info.video_streams) == 1
    vs = info.video_streams[0]
    assert vs.width == 1920 and vs.height == 1080
    assert vs.fps == pytest.approx(29.97, abs=0.001)
    assert vs.profile == "High" and vs.level == "41"
    assert len(info.audio_streams) == 1
    au = info.audio_streams[0]
    assert au.sample_rate == 48000 and au.channels == 2
    assert au.bitrate_kbps == 192
    assert au.title == "主音轨"
    assert len(info.subtitle_streams) == 1
    assert info.chapters and info.chapters[0]["title"] == "开头"


def test_probe_detailed_bad_values(monkeypatch, tmp_path):
    bad = {
        "format": {},
        "streams": [
            {"codec_type": "video", "codec_name": "h264",
             "profile": "High", "r_frame_rate": "a/b",
             "bit_rate": "abc", "level": "abc"},
            {"codec_type": "audio", "codec_name": "aac",
             "bit_rate": None, "profile": "LC"},
        ],
    }

    class R:
        returncode = 0
        stdout = json.dumps(bad)
        stderr = ""
    monkeypatch.setattr(mp.subprocess, "run", lambda *a, **k: R())
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    info = probe_detailed(str(f))
    assert info.errors == []
    assert info.video_streams[0].fps == 0  # 0/0 -> 0
    assert info.video_streams[0].bitrate_kbps == 0
    assert info.audio_streams[0].bitrate_kbps == 0
    # 非数字 level 在报告中走 ValueError 容错分支
    report = format_media_report(info)
    assert "h264" in report


def test_probe_detailed_fatal_bad_sample_rate(monkeypatch, tmp_path):
    # sample_rate 非数字会抛 ValueError, 被 probe_detailed 兜底捕获
    bad = {"streams": [{"codec_type": "audio", "codec_name": "aac",
                        "sample_rate": "abc"}]}

    class R:
        returncode = 0
        stdout = json.dumps(bad)
        stderr = ""
    monkeypatch.setattr(mp.subprocess, "run", lambda *a, **k: R())
    info = probe_detailed(str(tmp_path / "v.mp4"))
    assert "探测失败" in info.errors[0]


def test_probe_detailed_nonzero_returncode(monkeypatch, tmp_path):
    class R:
        returncode = 1
        stdout = ""
        stderr = "Invalid data"
    monkeypatch.setattr(mp.subprocess, "run", lambda *a, **k: R())
    info = probe_detailed(str(tmp_path / "x.mp4"))
    assert "ffprobe 无法读取文件" in info.errors[0]


def test_probe_detailed_exception(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise OSError("ffprobe missing")
    monkeypatch.setattr(mp.subprocess, "run", boom)
    info = probe_detailed(str(tmp_path / "x.mp4"))
    assert "探测失败" in info.errors[0]


# ----------------------------------------------------------------
# 解析/格式化辅助
# ----------------------------------------------------------------

def test_format_file_size():
    assert _format_file_size(-1) == "未知"
    assert _format_file_size(512) == "512 B"
    assert _format_file_size(2048) == "2.0 KB"
    assert _format_file_size(5 * 1024 * 1024) == "5.00 MB"
    assert _format_file_size(3 * 1024 * 1024 * 1024) == "3.00 GB"


def test_format_duration():
    assert _format_duration(0) == "00:00:00"
    assert _format_duration(-5) == "00:00:00"
    assert _format_duration(3661.5) == "01:01:01.50"


def test_get_language_display():
    assert _get_language_display("") == ""
    known = _get_language_display("chi")
    assert known.startswith("[chi]")
    assert _get_language_display("xx").startswith("[xx]")


def test_format_media_report_with_errors():
    info = DetailedMediaInfo(path="C:/a.mp4")
    info.errors.append("boom")
    report = format_media_report(info)
    assert "[错误] boom" in report


def test_format_media_report_full(ffprobe_ok, tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x" * 2048)
    info = probe_detailed(str(f))
    report = format_media_report(info)
    assert "视频流 #0" in report
    assert "High" in report
    assert "音频流" in report or "音轨" in report


def test_format_media_report_multi_track_hints():
    info = DetailedMediaInfo(path="C:/a.mp4")
    info.audio_streams = [
        StreamInfo(index=0, stream_index=1, codec_type="audio",
                   codec_name="aac", language="jpn"),
        StreamInfo(index=1, stream_index=2, codec_type="audio",
                   codec_name="aac", language="eng"),
    ]
    info.subtitle_streams = [
        StreamInfo(index=0, stream_index=3, codec_type="subtitle",
                   codec_name="ass", language="chi"),
        StreamInfo(index=1, stream_index=4, codec_type="subtitle",
                   codec_name="srt", language="eng"),
    ]
    report = format_media_report(info)
    assert "保留前两条音轨" in report
    assert "仅保留第一条字幕" in report


def test_generate_media_report(tmp_path):
    info = DetailedMediaInfo(path="C:/a.mp4")
    out = tmp_path / "report.txt"
    content = generate_media_report([info], str(out))
    assert out.exists()
    assert "媒体元数据检测报告" in content
