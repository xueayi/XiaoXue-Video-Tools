# -*- coding: utf-8 -*-
"""src/capabilities/worker.py 单元测试 (M3.1)。

不启动真实 QThread / 不跑真实 FFmpeg:
* worker.run() 直接同步执行 (等价一次后台探测周期);
* get_capabilities 用 fake 替换, 验证信号、单例回写与异常兜底;
* start_capability_probe 用 monkeypatch 的 start 验证「创建即启动」。
"""

import pytest

from src.capabilities import ffmpeg_probe
from src.capabilities import worker as worker_mod
from src.capabilities.ffmpeg_probe import FfmpegCaps


@pytest.fixture(autouse=True)
def _reset_caps_singleton():
    ffmpeg_probe.set_capabilities(None)
    yield
    ffmpeg_probe.set_capabilities(None)


def _caps(**overrides):
    data = dict(
        ffmpeg_path="/fake/ffmpeg",
        version="7.1",
        encoders=frozenset({"libx264", "h264_nvenc"}),
        filters=frozenset({"scale"}),
        hwaccels=frozenset({"cuda"}),
        probe_error=None,
        probed_at=1.0,
    )
    data.update(overrides)
    return FfmpegCaps(**data)


def test_worker_emits_caps_and_writes_singleton(monkeypatch):
    caps = _caps()
    calls = []

    def fake_get(refresh=False, timeout=15.0):
        calls.append((refresh, timeout))
        return caps

    monkeypatch.setattr(worker_mod, "get_capabilities", fake_get)
    worker = worker_mod.CapabilityProbeWorker(timeout=3.0, refresh=True)
    got = []
    worker.finished_caps.connect(got.append)

    worker.run()  # 同步执行, 等价后台线程跑完一次

    assert got == [caps]
    assert calls == [(True, 3.0)]
    # 结果已回写进程级单例, 后续 UI 读取不再重复探测
    assert ffmpeg_probe.caps_ready() is True
    cached = ffmpeg_probe.get_capabilities()
    assert cached is caps


def test_worker_refresh_false_propagates(monkeypatch):
    caps = _caps()
    calls = []
    monkeypatch.setattr(
        worker_mod, "get_capabilities",
        lambda refresh=False, timeout=15.0: calls.append(refresh) or caps)
    worker = worker_mod.CapabilityProbeWorker(timeout=1.5, refresh=False)
    worker.run()
    assert calls == [False]


def test_worker_catches_unexpected_exception(monkeypatch):
    def boom(refresh=False, timeout=15.0):
        raise RuntimeError("探测器爆炸")

    monkeypatch.setattr(worker_mod, "get_capabilities", boom)
    worker = worker_mod.CapabilityProbeWorker()
    got = []
    worker.finished_caps.connect(got.append)

    worker.run()  # 不允许抛异常

    assert len(got) == 1
    caps = got[0]
    assert isinstance(caps, FfmpegCaps)
    assert caps.probe_error is not None
    assert "能力探测异常" in caps.probe_error
    assert "RuntimeError" in caps.probe_error
    # 失败结果也会写入单例, UI 不会永远停在「正在检测…」
    assert ffmpeg_probe.caps_ready() is True
    assert ffmpeg_probe.get_capabilities().probe_error


def test_worker_treats_invalid_probe_result_as_failure(monkeypatch):
    monkeypatch.setattr(worker_mod, "get_capabilities",
                        lambda refresh=False, timeout=15.0: None)
    worker = worker_mod.CapabilityProbeWorker()
    got = []
    worker.finished_caps.connect(got.append)
    worker.run()
    assert got and got[0].probe_error


def test_start_capability_probe_creates_and_starts(monkeypatch):
    caps = _caps()
    calls = []
    monkeypatch.setattr(
        worker_mod, "get_capabilities",
        lambda refresh=False, timeout=15.0: calls.append((refresh, timeout)) or caps)

    started = []

    def fake_start(self):
        started.append(self)

    monkeypatch.setattr(
        worker_mod.CapabilityProbeWorker, "start", fake_start)

    worker = worker_mod.start_capability_probe(timeout=2.0, refresh=False)

    assert isinstance(worker, worker_mod.CapabilityProbeWorker)
    assert started == [worker]  # 帮助函数负责 start

    got = []
    worker.finished_caps.connect(got.append)
    worker.run()
    assert got == [caps]
    assert calls == [(False, 2.0)]


def test_start_capability_probe_defaults_to_refresh(monkeypatch):
    caps = _caps()
    calls = []
    monkeypatch.setattr(
        worker_mod, "get_capabilities",
        lambda refresh=False, timeout=15.0: calls.append(refresh) or caps)
    monkeypatch.setattr(
        worker_mod.CapabilityProbeWorker, "start", lambda self: None)

    worker = worker_mod.start_capability_probe()
    worker.run()
    assert calls == [True]
