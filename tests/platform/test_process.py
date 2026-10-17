# -*- coding: utf-8 -*-
"""src/platform/process.py 单元测试 (M4.1)。"""

import os
import subprocess

from src.platform import process


def test_constant_matches_platform():
    if os.name == "nt":
        assert process.CREATE_NO_WINDOW == subprocess.CREATE_NO_WINDOW
        assert process.CREATE_NO_WINDOW != 0
    else:
        assert process.CREATE_NO_WINDOW == 0


def test_no_window_kwargs_matches_current_platform():
    kwargs = process.no_window_kwargs()
    assert isinstance(kwargs, dict)
    if os.name == "nt":
        assert kwargs == {"creationflags": process.CREATE_NO_WINDOW}
    else:
        assert kwargs == {}


def test_simulated_posix_returns_empty(monkeypatch):
    monkeypatch.setattr(process.os, "name", "posix")
    assert process.no_window_kwargs() == {}


def test_windows_without_flag_returns_empty(monkeypatch):
    monkeypatch.setattr(process.os, "name", "nt")
    monkeypatch.setattr(process, "CREATE_NO_WINDOW", 0)
    assert process.no_window_kwargs() == {}


def test_kwargs_can_be_expanded():
    kwargs = process.no_window_kwargs()
    # 可直接用于 subprocess.run(...) / Popen(...) 的 ** 展开
    copied = {}
    copied.update(**kwargs)
    assert copied == kwargs
