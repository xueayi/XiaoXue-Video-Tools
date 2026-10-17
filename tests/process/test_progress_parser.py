# -*- coding: utf-8 -*-
"""src/process/progress.py 的 FFmpegProgressParser 单元测试 (M2.4)。

覆盖: 正常进度块、缺 duration、out_time_us/out_time 兼容、progress=end、
N/A、乱行、未知键、speed=0、percent clamp、reset 等。
"""

import dataclasses

import pytest

from src.process.progress import FFmpegProgressParser, ProgressEvent


def _feed_block(parser, *, frame=100, fps=25.0, out_time_us=5_000_000,
                speed=2.0, bitrate="1234.5kbits/s", total_size=1024,
                progress="continue", include_out_time_ms=True):
    """按真实 ffmpeg -progress 的键顺序喂入一个完整进度块, 返回末行事件。"""
    lines = [
        f"frame={frame}\n",
        f"fps={fps}\n",
        "stream_0_0_q=28.0\n",
        f"bitrate={bitrate}\n",
        f"total_size={total_size}\n",
        f"out_time_us={out_time_us}\n",
    ]
    if include_out_time_ms:
        lines.append(f"out_time_ms={out_time_us}\n")  # ffmpeg 里与 us 等值
    lines.extend([
        "dup_frames=0\n",
        "drop_frames=0\n",
        f"speed={speed}x\n",
        f"progress={progress}\n",
    ])
    event = None
    for line in lines:
        event = parser.feed_line(line)
    return event


# ----------------------------------------------------------------
# 正常进度块
# ----------------------------------------------------------------

def test_full_block_parses_all_fields():
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    event = _feed_block(parser)

    assert isinstance(event, ProgressEvent)
    assert event.frame == 100
    assert event.fps == pytest.approx(25.0)
    assert event.out_time_ms == 5_000_000       # 微秒 (ffmpeg 命名遗留)
    assert event.speed == pytest.approx(2.0)
    assert event.bitrate == "1234.5kbits/s"
    assert event.total_size == 1024
    assert event.progress == "continue"
    assert event.percent == pytest.approx(50.0)
    assert event.eta_seconds == pytest.approx(2.5)  # (10-5)/2
    assert parser.duration == pytest.approx(10.0)


def test_only_progress_line_emits_event():
    """块内其它行不返回事件, 只在 progress= 行产出完整快照。"""
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    assert parser.feed_line("frame=10\n") is None
    assert parser.feed_line("fps=20\n") is None
    assert parser.feed_line("out_time_us=1000000\n") is None
    assert parser.feed_line("speed=1.0x\n") is None
    event = parser.feed_line("progress=continue\n")
    assert event is not None
    assert event.frame == 10
    assert event.percent == pytest.approx(10.0)


def test_progress_end_forces_100_percent():
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    event = _feed_block(parser, progress="end")
    assert event.progress == "end"
    assert event.percent == 100.0
    assert event.eta_seconds == 0.0


def test_progress_end_without_duration_still_100():
    parser = FFmpegProgressParser()
    event = _feed_block(parser, progress="end")
    assert event.percent == 100.0
    assert event.eta_seconds == 0.0


def test_out_time_ms_is_microseconds():
    """out_time_ms 实际单位是微秒 (5_000_000us = 5s, duration 10s -> 50%)。"""
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    event = _feed_block(parser, out_time_us=5_000_000)
    assert event.percent == pytest.approx(50.0)


# ----------------------------------------------------------------
# 时长缺失 / 兼容字段
# ----------------------------------------------------------------

def test_missing_duration_no_percent_or_eta():
    parser = FFmpegProgressParser()
    event = _feed_block(parser)
    assert event.percent is None
    assert event.eta_seconds is None


def test_out_time_us_compatible():
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    event = _feed_block(parser, out_time_us=2_500_000, include_out_time_ms=False)
    assert event.percent == pytest.approx(25.0)
    assert event.out_time_ms == 2_500_000


def test_out_time_hms_compatible():
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    parser.feed_line("frame=1\n")
    parser.feed_line("out_time=00:00:02.500000\n")
    parser.feed_line("speed=1.0x\n")
    event = parser.feed_line("progress=continue\n")
    assert event.out_time_ms == 2_500_000
    assert event.percent == pytest.approx(25.0)


def test_set_duration_accepts_numeric_string():
    parser = FFmpegProgressParser()
    parser.set_duration("20")
    assert parser.duration == pytest.approx(20.0)
    event = _feed_block(parser, out_time_us=5_000_000)
    assert event.percent == pytest.approx(25.0)


@pytest.mark.parametrize("invalid", [None, 0, -3, "abc", float("nan")])
def test_set_duration_invalid_means_unknown(invalid):
    parser = FFmpegProgressParser()
    parser.set_duration(invalid)
    assert parser.duration is None


# ----------------------------------------------------------------
# 异常输入 / 边界
# ----------------------------------------------------------------

def test_na_values_are_ignored():
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    parser.feed_line("frame=10\n")
    parser.feed_line("fps=N/A\n")
    parser.feed_line("bitrate=N/A\n")
    parser.feed_line("speed=N/A\n")
    parser.feed_line("out_time_us=1000000\n")
    event = parser.feed_line("progress=continue\n")
    assert event.frame == 10
    assert event.fps == 0.0
    assert event.bitrate == ""
    assert event.speed == 0.0
    assert event.percent == pytest.approx(10.0)
    assert event.eta_seconds is None  # speed<=0 -> 无 ETA


def test_garbage_lines_return_none():
    parser = FFmpegProgressParser()
    for line in ("", "\n", "hello world\n", "Input #0, mp4:\n",
                 "  Duration: 00:01:40.00, start: 0.0\n"):
        assert parser.feed_line(line) is None


def test_unknown_keys_ignored():
    parser = FFmpegProgressParser()
    assert parser.feed_line("stream_1_0_q=3\n") is None
    assert parser.feed_line("some_unknown_key=123\n") is None
    assert parser.feed_line("progress=continue\n") is not None  # 块结束仍产出


def test_malformed_numeric_values_ignored():
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    parser.feed_line("frame=abc\n")
    parser.feed_line("fps=1.2.3\n")
    parser.feed_line("out_time_us=not-a-number\n")
    parser.feed_line("total_size=1e5x\n")
    event = parser.feed_line("progress=continue\n")
    assert event.frame == 0
    assert event.fps == 0.0
    assert event.out_time_ms == 0
    assert event.total_size == 0
    assert event.percent == pytest.approx(0.0)


def test_speed_zero_no_eta():
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    event = _feed_block(parser, speed=0)
    assert event.speed == 0.0
    assert event.eta_seconds is None
    assert event.percent == pytest.approx(50.0)


def test_percent_clamped_to_100():
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    event = _feed_block(parser, out_time_us=20_000_000)
    assert event.percent == pytest.approx(100.0)
    assert event.eta_seconds == pytest.approx(0.0)


def test_percent_never_negative_for_zero_duration():
    parser = FFmpegProgressParser()
    # duration 未设置 -> percent None (不是 0)
    event = _feed_block(parser, out_time_us=0)
    assert event.percent is None


def test_reset_clears_duration_and_state():
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    _feed_block(parser, frame=42)
    parser.reset()
    assert parser.duration is None
    event = parser.feed_line("progress=continue\n")
    assert event.frame == 0
    assert event.percent is None


def test_multiple_blocks_update_state():
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    first = _feed_block(parser, frame=10, out_time_us=1_000_000, speed=1.0)
    second = _feed_block(parser, frame=50, out_time_us=5_000_000, speed=2.0)
    assert first.percent == pytest.approx(10.0)
    assert second.frame == 50
    assert second.percent == pytest.approx(50.0)


def test_progress_event_is_frozen():
    event = ProgressEvent()
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.percent = 10.0  # type: ignore[misc]


def test_feed_non_string_returns_none():
    parser = FFmpegProgressParser()
    assert parser.feed_line(None) is None
