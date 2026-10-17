# -*- coding: utf-8 -*-
"""formatting.py 纯函数测试: 时长 / 剩余时间 / 文件大小 / 速度 / 百分比。"""

import pytest

from src.ui.formatting import fmt_duration, fmt_eta, fmt_percent, fmt_size, fmt_speed


def test_fmt_duration_basic():
    assert fmt_duration(0) == "00:00:00"
    assert fmt_duration(75) == "00:01:15"
    assert fmt_duration(3725) == "01:02:05"
    assert fmt_duration(360000) == "100:00:00"


@pytest.mark.parametrize("value", [None, -1, float("nan"), "abc"])
def test_fmt_duration_invalid(value):
    assert fmt_duration(value) == "--:--:--"


def test_fmt_eta_basic():
    assert fmt_eta(0) == "00:00"
    assert fmt_eta(65) == "01:05"
    assert fmt_eta(3599) == "59:59"
    assert fmt_eta(3665) == "1:01:05"


@pytest.mark.parametrize("value", [None, -1, float("nan")])
def test_fmt_eta_invalid(value):
    assert fmt_eta(value) == "--"


def test_fmt_size_units():
    assert fmt_size(0) == "0 B"
    assert fmt_size(512) == "512 B"
    assert fmt_size(1024) == "1.0 KB"
    assert fmt_size(1536) == "1.5 KB"
    assert fmt_size(1024 ** 2) == "1.0 MB"
    assert fmt_size(1024 ** 3) == "1.0 GB"
    assert fmt_size(1024 ** 4) == "1.0 TB"


@pytest.mark.parametrize("value", [None, -5, float("nan"), "abc"])
def test_fmt_size_invalid(value):
    assert fmt_size(value) == "--"


def test_fmt_speed():
    assert fmt_speed(1.856) == "1.86x"
    assert fmt_speed(2) == "2.00x"
    assert fmt_speed(0) == "--"
    assert fmt_speed(None) == "--"
    assert fmt_speed(-1) == "--"


def test_fmt_percent():
    assert fmt_percent(0) == "0.0%"
    assert fmt_percent(42.46) == "42.5%"
    assert fmt_percent(100) == "100.0%"
    assert fmt_percent(None) == "--"
    assert fmt_percent(float("nan")) == "--"
