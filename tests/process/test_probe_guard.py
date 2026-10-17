# -*- coding: utf-8 -*-
"""ffprobe 调用 (media_probe / qc) 的超时与取消检查测试。"""

import subprocess

import pytest

import src.media_probe as mp
import src.qc as qc
from src.task.context import (
    TaskCancelled,
    TaskContext,
    reset_current_task,
    set_current_task,
)


class FakeResult:
    returncode = 1
    stdout = ""
    stderr = "bad input"


def test_probe_passes_timeout(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return FakeResult()

    monkeypatch.setattr(mp.subprocess, "run", fake_run)
    info = mp.probe_detailed("x.mp4")
    assert captured["timeout"] == mp.PROBE_TIMEOUT_SEC
    assert "ffprobe 无法读取文件" in info.errors[0]


def test_probe_timeout_maps_to_error(monkeypatch):
    def boom(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, mp.PROBE_TIMEOUT_SEC)

    monkeypatch.setattr(mp.subprocess, "run", boom)
    info = mp.probe_detailed("x.mp4")
    assert "超时" in info.errors[0]


def test_probe_cancelled_context_raises_task_cancelled(monkeypatch):
    called = []
    monkeypatch.setattr(mp.subprocess, "run", lambda *a, **k: called.append(1))
    context = TaskContext()
    context.cancel()
    token = set_current_task(context)
    try:
        with pytest.raises(TaskCancelled):
            mp.probe_detailed("x.mp4")
    finally:
        reset_current_task(token)
    assert called == []  # 取消后不再启动 ffprobe


def test_qc_probe_passes_timeout(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return FakeResult()

    monkeypatch.setattr(qc.subprocess, "run", fake_run)
    info = qc.probe_media("x.mp4")
    assert captured["timeout"] == qc.QC_PROBE_TIMEOUT_SEC
    assert info.is_valid is False


def test_qc_probe_timeout_maps_to_error(monkeypatch):
    def boom(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, qc.QC_PROBE_TIMEOUT_SEC)

    monkeypatch.setattr(qc.subprocess, "run", boom)
    info = qc.probe_media("x.mp4")
    assert info.is_valid is False
    assert "超时" in info.errors[0]


def test_qc_probe_cancelled_context_raises_task_cancelled(monkeypatch):
    monkeypatch.setattr(qc.subprocess, "run", lambda *a, **k: FakeResult())
    context = TaskContext()
    context.cancel()
    token = set_current_task(context)
    try:
        with pytest.raises(TaskCancelled):
            qc.probe_media("x.mp4")
    finally:
        reset_current_task(token)
