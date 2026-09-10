# -*- coding: utf-8 -*-
"""progress_dashboard.py 与 ffmpeg_progress.py 测试。"""

import pytest

from src.ui.ffmpeg_progress import FFmpegProgressParser, ProgressInfo
from src.ui.progress_dashboard import ProgressDashboard, _MetricCard


def test_parser_duration_line(qapp):
    parser = FFmpegProgressParser()
    results = []
    parser.progress_updated.connect(results.append)
    parser.feed_line("Input #0, mp4:\n")
    parser.feed_line("  Duration: 00:01:40.00, start: 0.000000\n")
    assert parser._info.total_duration == pytest.approx(100.0)


def test_parser_progress_line(qapp):
    parser = FFmpegProgressParser()
    results = []
    parser.progress_updated.connect(results.append)
    parser.set_duration(200.0)
    parser.feed_line(
        "frame=  100 fps= 50 q=28.0 size=    1024kB "
        "time=00:01:00.00 bitrate= 140.0kbits/s speed=2.00x\n"
    )
    assert results, "应当发出一次进度信号"
    info = results[-1]
    assert info.frame == 100
    assert info.fps == pytest.approx(50.0)
    assert info.size_kb == 1024
    assert info.time_sec == pytest.approx(60.0)
    assert info.bitrate_kbps == pytest.approx(140.0)
    assert info.speed == pytest.approx(2.0)
    assert info.percent == pytest.approx(30.0, abs=0.1)
    assert info.eta_sec == pytest.approx(70.0, abs=0.5)


def test_parser_without_duration_no_percent(qapp):
    parser = FFmpegProgressParser()
    results = []
    parser.progress_updated.connect(results.append)
    parser.feed_line("frame=   10 fps= 5 time=00:00:01.00 speed=1.00x\n")
    assert results[-1].percent == 0.0


def test_parser_reset(qapp):
    parser = FFmpegProgressParser()
    parser.set_duration(100.0)
    parser.reset()
    assert parser._info.total_duration == 0.0
    assert parser._info.frame == 0


def test_parser_ignores_garbage(qapp):
    parser = FFmpegProgressParser()
    results = []
    parser.progress_updated.connect(results.append)
    parser.feed_line("hello world\n")
    assert results == []


def test_hms_to_sec():
    from src.ui.ffmpeg_progress import _hms_to_sec
    assert _hms_to_sec("00", "01", "02", "5") == pytest.approx(62.5)


# ----------------------------------------------------------------
# 仪表盘
# ----------------------------------------------------------------

@pytest.fixture
def dashboard(qapp):
    d = ProgressDashboard()
    d.show_indeterminate()
    return d


def test_dashboard_indeterminate(dashboard):
    assert dashboard.isVisible()
    assert dashboard._progress_bar.maximum() == 0


def test_dashboard_update_metrics(dashboard):
    info = ProgressInfo(frame=12, fps=30, speed=2.5, time_sec=10,
                        percent=50.0, eta_sec=30.0, total_duration=20)
    dashboard.update_metrics(info)
    assert dashboard._card_progress._value_label.text() == "50.0%"
    assert dashboard._card_speed._value_label.text() == "2.50x"
    assert dashboard._card_frame._value_label.text() == "12"
    assert dashboard._card_eta._value_label.text() == "00:30"
    assert dashboard._progress_bar.value() == 500


def test_dashboard_update_metrics_zero_speed_and_negative_eta(dashboard):
    info = ProgressInfo(frame=0, speed=0, percent=0.0, eta_sec=-1)
    dashboard.update_metrics(info)
    assert dashboard._card_speed._value_label.text() == "--"
    assert dashboard._card_eta._value_label.text() == "--"


def test_dashboard_finish_success(dashboard):
    dashboard.finish(True)
    assert dashboard._card_progress._value_label.text() == "100%"
    assert dashboard._card_eta._value_label.text() == "完成"
    assert dashboard._progress_bar.value() == 1000


def test_dashboard_finish_failure(dashboard):
    dashboard.finish(False)
    assert dashboard._card_progress._value_label.text() == "失败"


def test_dashboard_reset(dashboard):
    dashboard.reset()
    assert not dashboard.isVisible()
    assert dashboard._card_progress._value_label.text() == "--"
    assert dashboard._progress_bar.value() == 0
    assert dashboard._progress_bar.maximum() == 1000


def test_metric_card_dedupes_value(qapp, monkeypatch):
    card = _MetricCard("速度")
    label = card._value_label
    state = {"v": "--"}
    calls = []
    monkeypatch.setattr(label, "text", lambda: state["v"])
    monkeypatch.setattr(
        label, "setText",
        lambda t: (state.__setitem__("v", t), calls.append(t)))
    card.set_value("1.0x")
    card.set_value("1.0x")  # 同值不再刷新
    assert calls == ["1.0x"]
    card.set_value("2.0x")
    assert calls == ["1.0x", "2.0x"]


def test_fmt_eta():
    assert ProgressDashboard._fmt_eta(-5) == "--"
    assert ProgressDashboard._fmt_eta(45) == "00:45"
    assert ProgressDashboard._fmt_eta(3700) == "1:01:40"
